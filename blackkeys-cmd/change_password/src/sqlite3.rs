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
    fn sqlite3_changes(db: *mut Connection) -> c_int;
    fn sqlite3_finalize(stmt: *mut Statement) -> c_int;
    #[cfg(test)]
    fn sqlite3_column_text(stmt: *mut Statement, index: c_int) -> *const c_uchar;
    #[cfg(test)]
    fn sqlite3_column_int64(stmt: *mut Statement, index: c_int) -> i64;
    #[cfg(test)]
    fn sqlite3_bind_int64(stmt: *mut Statement, index: c_int, value: i64) -> c_int;
}

pub fn update_password(path: &Path, username: &str, password_hash: &str) -> Result<(), String> {
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
    let result = update_on_connection(db, username, password_hash);
    let close = unsafe { sqlite3_close(db) };
    match (result, close) {
        (Err(error), _) => Err(error),
        (Ok(()), SQLITE_OK) => Ok(()),
        (Ok(()), status) => Err(format!(
            "SQLite error while closing database (status {status})"
        )),
    }
}

fn update_on_connection(
    db: *mut Connection,
    username: &str,
    password_hash: &str,
) -> Result<(), String> {
    let mut stmt = std::ptr::null_mut();
    let status = unsafe {
        sqlite3_prepare_v2(
            db,
            c"UPDATE \"user\" SET password = ? WHERE username = ?".as_ptr(),
            -1,
            &mut stmt,
            std::ptr::null_mut(),
        )
    };
    if status != SQLITE_OK {
        return Err(error(db, "preparing password update", status));
    }
    let password_hash = text_value(password_hash, "password hash")?;
    let username_value = text_value(username, "username")?;
    let result = (|| {
        bind_text(db, stmt, 1, &password_hash, "password hash")?;
        bind_text(db, stmt, 2, &username_value, "username")?;
        let status = unsafe { sqlite3_step(stmt) };
        if status != SQLITE_DONE {
            return Err(error(db, "updating password", status));
        }
        if unsafe { sqlite3_changes(db) } == 0 {
            return Err(format!("user not found: {username}"));
        }
        Ok(())
    })();
    let finalize = unsafe { sqlite3_finalize(stmt) };
    match (result, finalize) {
        (Err(error), _) => Err(error),
        (Ok(()), SQLITE_OK) => Ok(()),
        (Ok(()), status) => Err(format!(
            "SQLite error while finalizing password update (status {status})"
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
            "blackkeys-change-password-{}-{}.db",
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
                "CREATE TABLE \"user\" (username TEXT PRIMARY KEY NOT NULL, password TEXT NOT NULL, email TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT (unixepoch()))",
            );
        }
        path
    }
    fn execute(path: &Path, sql: &str) {
        let db = open(path);
        let sql = CString::new(sql).unwrap();
        let mut stmt = std::ptr::null_mut();
        assert_eq!(
            unsafe { sqlite3_prepare_v2(db, sql.as_ptr(), -1, &mut stmt, std::ptr::null_mut()) },
            SQLITE_OK
        );
        assert_eq!(unsafe { sqlite3_step(stmt) }, SQLITE_DONE);
        assert_eq!(unsafe { sqlite3_finalize(stmt) }, SQLITE_OK);
        assert_eq!(unsafe { sqlite3_close(db) }, SQLITE_OK);
    }
    fn open(path: &Path) -> *mut Connection {
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
        db
    }
    fn bind_text_for_test(stmt: *mut Statement, index: c_int, value: &str) {
        let value = CString::new(value).unwrap();
        let transient: Destructor = unsafe { std::mem::transmute::<isize, Destructor>(-1) };
        assert_eq!(
            unsafe {
                sqlite3_bind_text64(
                    stmt,
                    index,
                    value.as_ptr(),
                    value.as_bytes().len() as u64,
                    transient,
                    SQLITE_UTF8,
                )
            },
            SQLITE_OK
        );
    }
    fn insert_user(path: &Path, username: &str, password: &str, email: &str, created_at: i64) {
        let db = open(path);
        let mut stmt = std::ptr::null_mut();
        assert_eq!(
            unsafe {
                sqlite3_prepare_v2(
                    db,
                    c"INSERT INTO \"user\" (username, password, email, created_at) VALUES (?, ?, ?, ?)".as_ptr(),
                    -1,
                    &mut stmt,
                    std::ptr::null_mut(),
                )
            },
            SQLITE_OK
        );
        bind_text_for_test(stmt, 1, username);
        bind_text_for_test(stmt, 2, password);
        bind_text_for_test(stmt, 3, email);
        assert_eq!(
            unsafe { sqlite3_bind_int64(stmt, 4, created_at) },
            SQLITE_OK
        );
        assert_eq!(unsafe { sqlite3_step(stmt) }, SQLITE_DONE);
        assert_eq!(unsafe { sqlite3_finalize(stmt) }, SQLITE_OK);
        assert_eq!(unsafe { sqlite3_close(db) }, SQLITE_OK);
    }
    fn row(path: &Path, username: &str) -> (String, String, i64) {
        let db = open(path);
        let mut stmt = std::ptr::null_mut();
        assert_eq!(
            unsafe {
                sqlite3_prepare_v2(
                    db,
                    c"SELECT password, email, created_at FROM \"user\" WHERE username = ?".as_ptr(),
                    -1,
                    &mut stmt,
                    std::ptr::null_mut(),
                )
            },
            SQLITE_OK
        );
        bind_text_for_test(stmt, 1, username);
        assert_eq!(unsafe { sqlite3_step(stmt) }, SQLITE_ROW);
        let password = unsafe { CStr::from_ptr(sqlite3_column_text(stmt, 0).cast()) }
            .to_str()
            .unwrap()
            .to_owned();
        let email = unsafe { CStr::from_ptr(sqlite3_column_text(stmt, 1).cast()) }
            .to_str()
            .unwrap()
            .to_owned();
        let created_at = unsafe { sqlite3_column_int64(stmt, 2) };
        assert_eq!(unsafe { sqlite3_finalize(stmt) }, SQLITE_OK);
        assert_eq!(unsafe { sqlite3_close(db) }, SQLITE_OK);
        (password, email, created_at)
    }

    #[test]
    fn updates_password_hash_and_leaves_other_columns() {
        let path = scratch_database(true);
        let original = "original-password";
        let replacement = "replacement-password";
        let original_hash = crate::argon2id::hash_password(original).unwrap();
        insert_user(
            &path,
            "alice",
            &original_hash,
            "alice@example.test",
            1_735_689_600,
        );
        insert_user(&path, "bob", "hash-bob", "bob@example.test", 0);
        let new_hash = crate::argon2id::hash_password(replacement).unwrap();
        update_password(&path, "alice", &new_hash).unwrap();
        let (alice_password, alice_email, alice_created_at) = row(&path, "alice");
        let (bob_password, bob_email, bob_created_at) = row(&path, "bob");
        assert!(alice_password.starts_with("$argon2id$"));
        assert_ne!(alice_password, original_hash);
        assert!(crate::argon2id::verify(&alice_password, replacement));
        assert!(!crate::argon2id::verify(&alice_password, original));
        assert_eq!(alice_email, "alice@example.test");
        assert_eq!(alice_created_at, 1_735_689_600);
        assert_eq!(bob_password, "hash-bob");
        assert_eq!(bob_email, "bob@example.test");
        assert_eq!(bob_created_at, 0);
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn fails_when_user_is_missing_and_leaves_existing_rows() {
        let path = scratch_database(true);
        insert_user(&path, "bob", "hash-bob", "bob@example.test", 0);
        let error = update_password(&path, "alice", "$argon2id$replacement").unwrap_err();
        assert!(error.contains("user not found: alice"));
        let (bob_password, bob_email, bob_created_at) = row(&path, "bob");
        assert_eq!(bob_password, "hash-bob");
        assert_eq!(bob_email, "bob@example.test");
        assert_eq!(bob_created_at, 0);
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn fails_without_user_table() {
        let path = scratch_database(false);
        assert!(update_password(&path, "alice", "$argon2id$hash").is_err());
        std::fs::remove_file(path).unwrap();
    }
}
