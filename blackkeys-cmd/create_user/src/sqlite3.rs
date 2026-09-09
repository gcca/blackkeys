use std::{
    ffi::{CStr, CString},
    os::raw::{c_char, c_int, c_uchar, c_void},
    path::Path,
};

const SQLITE_OK: c_int = 0;
const SQLITE_DONE: c_int = 101;
const SQLITE_OPEN_READWRITE: c_int = 2;
const SQLITE_UTF8: c_uchar = 1;

#[repr(C)]
struct Connection {
    _private: [u8; 0],
}
#[repr(C)]
struct Statement {
    _private: [u8; 0],
}
type Destructor = Option<unsafe extern "C" fn(*mut c_void)>;

#[link(name = "sqlite3")]
unsafe extern "C" {
    fn sqlite3_open_v2(
        filename: *const c_char,
        db: *mut *mut Connection,
        flags: c_int,
        vfs: *const c_char,
    ) -> c_int;
    fn sqlite3_close(db: *mut Connection) -> c_int;
    fn sqlite3_errmsg(db: *mut Connection) -> *const c_char;
    fn sqlite3_prepare_v2(
        db: *mut Connection,
        sql: *const c_char,
        length: c_int,
        stmt: *mut *mut Statement,
        tail: *mut *const c_char,
    ) -> c_int;
    fn sqlite3_bind_text64(
        stmt: *mut Statement,
        index: c_int,
        value: *const c_char,
        length: u64,
        destructor: Destructor,
        encoding: c_uchar,
    ) -> c_int;
    fn sqlite3_step(stmt: *mut Statement) -> c_int;
    fn sqlite3_finalize(stmt: *mut Statement) -> c_int;
    #[cfg(test)]
    fn sqlite3_column_text(stmt: *mut Statement, index: c_int) -> *const c_uchar;
}

pub fn insert_user(
    path: &Path,
    username: &str,
    password_hash: &str,
    email: &str,
) -> Result<(), String> {
    let path = CString::new(path.to_string_lossy().as_bytes())
        .map_err(|_| "database path contains a NUL byte".to_string())?;
    let mut db = std::ptr::null_mut();
    let open = unsafe {
        sqlite3_open_v2(
            path.as_ptr(),
            &mut db,
            SQLITE_OPEN_READWRITE,
            std::ptr::null(),
        )
    };
    if open != SQLITE_OK {
        let error = error(db, "opening database", open);
        if !db.is_null() {
            let _ = unsafe { sqlite3_close(db) };
        }
        return Err(error);
    }
    let result = insert_on_connection(db, username, password_hash, email);
    let close = unsafe { sqlite3_close(db) };
    match (result, close) {
        (Err(error), _) => Err(error),
        (Ok(()), SQLITE_OK) => Ok(()),
        (Ok(()), status) => Err(format!(
            "SQLite error while closing database (status {status})"
        )),
    }
}

fn insert_on_connection(
    db: *mut Connection,
    username: &str,
    password_hash: &str,
    email: &str,
) -> Result<(), String> {
    let mut stmt = std::ptr::null_mut();
    let status = unsafe {
        sqlite3_prepare_v2(
            db,
            c"INSERT INTO \"user\" (username, password, email) VALUES (?, ?, ?)".as_ptr(),
            -1,
            &mut stmt,
            std::ptr::null_mut(),
        )
    };
    if status != SQLITE_OK {
        return Err(error(db, "preparing user insert", status));
    }
    let username = text_value(username, "username")?;
    let password_hash = text_value(password_hash, "password hash")?;
    let email = text_value(email, "email")?;
    let result = (|| {
        bind_text(db, stmt, 1, &username, "username")?;
        bind_text(db, stmt, 2, &password_hash, "password hash")?;
        bind_text(db, stmt, 3, &email, "email")?;
        let status = unsafe { sqlite3_step(stmt) };
        if status == SQLITE_DONE {
            Ok(())
        } else {
            Err(error(db, "inserting user", status))
        }
    })();
    let finalize = unsafe { sqlite3_finalize(stmt) };
    match (result, finalize) {
        (Err(error), _) => Err(error),
        (Ok(()), SQLITE_OK) => Ok(()),
        (Ok(()), status) => Err(format!(
            "SQLite error while finalizing user insert (status {status})"
        )),
    }
}

fn text_value(value: &str, field: &str) -> Result<CString, String> {
    CString::new(value).map_err(|_| format!("{field} contains a NUL byte"))
}
fn bind_text(
    db: *mut Connection,
    stmt: *mut Statement,
    index: c_int,
    value: &CString,
    field: &str,
) -> Result<(), String> {
    let transient: Destructor = unsafe { std::mem::transmute::<isize, Destructor>(-1) };
    let status = unsafe {
        sqlite3_bind_text64(
            stmt,
            index,
            value.as_ptr(),
            value.as_bytes().len() as u64,
            transient,
            SQLITE_UTF8,
        )
    };
    if status == SQLITE_OK {
        Ok(())
    } else {
        Err(error(db, &format!("binding {field}"), status))
    }
}
fn error(db: *mut Connection, action: &str, status: c_int) -> String {
    let detail = if db.is_null() {
        None
    } else {
        let message = unsafe { sqlite3_errmsg(db) };
        (!message.is_null()).then(|| {
            unsafe { CStr::from_ptr(message) }
                .to_string_lossy()
                .into_owned()
        })
    };
    match detail {
        Some(detail) => format!("SQLite error while {action} (status {status}): {detail}"),
        None => format!("SQLite error while {action} (status {status})"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs::File,
        time::{SystemTime, UNIX_EPOCH},
    };

    const SQLITE_ROW: c_int = 100;

    fn scratch_database(schema: bool) -> std::path::PathBuf {
        let path = std::env::temp_dir().join(format!(
            "blackkeys-sqlite3-{}-{}.db",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        File::create(&path).unwrap();
        if schema {
            execute(
                &path,
                "CREATE TABLE \"user\" (username TEXT PRIMARY KEY, password TEXT NOT NULL, email TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
            );
        }
        path
    }
    fn execute(path: &Path, sql: &str) {
        let path = CString::new(path.to_string_lossy().as_bytes()).unwrap();
        let sql = CString::new(sql).unwrap();
        let mut db = std::ptr::null_mut();
        assert_eq!(
            unsafe {
                sqlite3_open_v2(
                    path.as_ptr(),
                    &mut db,
                    SQLITE_OPEN_READWRITE,
                    std::ptr::null(),
                )
            },
            SQLITE_OK
        );
        let mut stmt = std::ptr::null_mut();
        assert_eq!(
            unsafe { sqlite3_prepare_v2(db, sql.as_ptr(), -1, &mut stmt, std::ptr::null_mut()) },
            SQLITE_OK
        );
        assert_eq!(unsafe { sqlite3_step(stmt) }, SQLITE_DONE);
        assert_eq!(unsafe { sqlite3_finalize(stmt) }, SQLITE_OK);
        assert_eq!(unsafe { sqlite3_close(db) }, SQLITE_OK);
    }
    fn stored_password(path: &Path) -> String {
        let path = CString::new(path.to_string_lossy().as_bytes()).unwrap();
        let mut db = std::ptr::null_mut();
        assert_eq!(
            unsafe {
                sqlite3_open_v2(
                    path.as_ptr(),
                    &mut db,
                    SQLITE_OPEN_READWRITE,
                    std::ptr::null(),
                )
            },
            SQLITE_OK
        );
        let mut stmt = std::ptr::null_mut();
        assert_eq!(
            unsafe {
                sqlite3_prepare_v2(
                    db,
                    c"SELECT password FROM \"user\" WHERE username = 'alice'".as_ptr(),
                    -1,
                    &mut stmt,
                    std::ptr::null_mut(),
                )
            },
            SQLITE_OK
        );
        assert_eq!(unsafe { sqlite3_step(stmt) }, SQLITE_ROW);
        let value = unsafe { CStr::from_ptr(sqlite3_column_text(stmt, 0).cast()) }
            .to_str()
            .unwrap()
            .to_owned();
        assert_eq!(unsafe { sqlite3_finalize(stmt) }, SQLITE_OK);
        assert_eq!(unsafe { sqlite3_close(db) }, SQLITE_OK);
        value
    }

    #[test]
    fn inserts_user_and_does_not_replace_duplicate() {
        let path = scratch_database(true);
        let password = "correct horse battery staple";
        let hash = crate::argon2id::hash_password(password).unwrap();
        insert_user(&path, "alice", &hash, "alice@example.test").unwrap();
        let original = stored_password(&path);
        assert!(original.starts_with("$argon2id$"));
        assert!(crate::argon2id::verify(&original, password));
        assert!(
            insert_user(
                &path,
                "alice",
                "$argon2id$replacement",
                "changed@example.test"
            )
            .is_err()
        );
        assert_eq!(stored_password(&path), original);
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn fails_without_user_table() {
        let path = scratch_database(false);
        assert!(insert_user(&path, "alice", "$argon2id$hash", "alice@example.test").is_err());
        std::fs::remove_file(path).unwrap();
    }
}
