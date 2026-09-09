use std::{
    ffi::{CStr, CString},
    os::raw::{c_char, c_int, c_uchar},
    path::Path,
};

const SQLITE_OK: c_int = 0;
const SQLITE_ROW: c_int = 100;
const SQLITE_DONE: c_int = 101;
const SQLITE_OPEN_READONLY: c_int = 1;

#[repr(C)]
struct Connection {
    _private: [u8; 0],
}

#[repr(C)]
struct Statement {
    _private: [u8; 0],
}

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
    fn sqlite3_step(stmt: *mut Statement) -> c_int;
    fn sqlite3_column_text(stmt: *mut Statement, index: c_int) -> *const c_uchar;
    fn sqlite3_finalize(stmt: *mut Statement) -> c_int;
}

pub struct User {
    pub username: String,
    pub email: String,
    pub created_at: String,
}

pub fn list_users(path: &Path) -> Result<Vec<User>, String> {
    let path = CString::new(path.to_string_lossy().as_bytes())
        .map_err(|_| "database path contains a NUL byte".to_string())?;
    let mut db = std::ptr::null_mut();
    let open = unsafe {
        sqlite3_open_v2(
            path.as_ptr(),
            &mut db,
            SQLITE_OPEN_READONLY,
            std::ptr::null(),
        )
    };
    if open != SQLITE_OK {
        let error = error(db, "opening database read-only", open);
        if !db.is_null() {
            let _ = unsafe { sqlite3_close(db) };
        }
        return Err(error);
    }

    let result = list_on_connection(db);
    let close = unsafe { sqlite3_close(db) };
    match (result, close) {
        (Err(error), _) => Err(error),
        (Ok(users), SQLITE_OK) => Ok(users),
        (Ok(_), status) => Err(format!(
            "SQLite error while closing database (status {status})"
        )),
    }
}

fn list_on_connection(db: *mut Connection) -> Result<Vec<User>, String> {
    let mut stmt = std::ptr::null_mut();
    let status = unsafe {
        sqlite3_prepare_v2(
            db,
            c"SELECT username, email, strftime('%Y-%m-%dT%H:%M:%SZ', created_at, 'unixepoch') FROM \"user\" ORDER BY username ASC".as_ptr(),
            -1,
            &mut stmt,
            std::ptr::null_mut(),
        )
    };
    if status != SQLITE_OK {
        return Err(error(db, "preparing user list", status));
    }

    let result = (|| {
        let mut users = Vec::new();
        loop {
            match unsafe { sqlite3_step(stmt) } {
                SQLITE_ROW => users.push(User {
                    username: column_text(stmt, 0, "username")?,
                    email: column_text(stmt, 1, "email")?,
                    created_at: column_text(stmt, 2, "created_at")?,
                }),
                SQLITE_DONE => return Ok(users),
                status => return Err(error(db, "reading user list", status)),
            }
        }
    })();
    let finalize = unsafe { sqlite3_finalize(stmt) };
    match (result, finalize) {
        (Err(error), _) => Err(error),
        (Ok(users), SQLITE_OK) => Ok(users),
        (Ok(_), status) => Err(format!(
            "SQLite error while finalizing user list (status {status})"
        )),
    }
}

fn column_text(stmt: *mut Statement, index: c_int, column: &str) -> Result<String, String> {
    let value = unsafe { sqlite3_column_text(stmt, index) };
    if value.is_null() {
        return Err(format!("SQLite query returned NULL {column}"));
    }
    Ok(unsafe { CStr::from_ptr(value.cast()) }
        .to_string_lossy()
        .into_owned())
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
pub mod test_support {
    use super::*;
    use std::fs::File;

    const SQLITE_OPEN_READWRITE: c_int = 2;

    unsafe extern "C" {
        fn sqlite3_bind_text(
            stmt: *mut Statement,
            index: c_int,
            value: *const c_char,
            length: c_int,
            destructor: Option<unsafe extern "C" fn(*mut std::ffi::c_void)>,
        ) -> c_int;
        fn sqlite3_bind_int64(stmt: *mut Statement, index: c_int, value: i64) -> c_int;
    }

    pub fn create_empty_database(path: &Path) {
        File::create(path).unwrap();
    }

    pub fn create_database(path: &Path, users: &[(&str, &str, &str, i64)]) {
        create_database_with_sql(
            path,
            "CREATE TABLE \"user\" (username TEXT, password TEXT, email TEXT, created_at INTEGER);",
        );
        let db = open_readwrite(path);
        for (username, password, email, created_at) in users {
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
            bind_text(stmt, 1, username);
            bind_text(stmt, 2, password);
            bind_text(stmt, 3, email);
            assert_eq!(
                unsafe { sqlite3_bind_int64(stmt, 4, *created_at) },
                SQLITE_OK
            );
            assert_eq!(unsafe { sqlite3_step(stmt) }, SQLITE_DONE);
            assert_eq!(unsafe { sqlite3_finalize(stmt) }, SQLITE_OK);
        }
        assert_eq!(unsafe { sqlite3_close(db) }, SQLITE_OK);
    }

    pub fn create_database_with_sql(path: &Path, sql: &str) {
        File::create(path).unwrap();
        let db = open_readwrite(path);
        for statement in sql
            .split(';')
            .filter(|statement| !statement.trim().is_empty())
        {
            execute(db, statement);
        }
        assert_eq!(unsafe { sqlite3_close(db) }, SQLITE_OK);
    }

    fn open_readwrite(path: &Path) -> *mut Connection {
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

    fn execute(db: *mut Connection, sql: &str) {
        let sql = CString::new(sql).unwrap();
        let mut stmt = std::ptr::null_mut();
        assert_eq!(
            unsafe { sqlite3_prepare_v2(db, sql.as_ptr(), -1, &mut stmt, std::ptr::null_mut()) },
            SQLITE_OK
        );
        assert_eq!(unsafe { sqlite3_step(stmt) }, SQLITE_DONE);
        assert_eq!(unsafe { sqlite3_finalize(stmt) }, SQLITE_OK);
    }

    fn bind_text(stmt: *mut Statement, index: c_int, value: &str) {
        let value = CString::new(value).unwrap();
        let transient = unsafe {
            std::mem::transmute::<isize, Option<unsafe extern "C" fn(*mut std::ffi::c_void)>>(-1)
        };
        assert_eq!(
            unsafe {
                sqlite3_bind_text(
                    stmt,
                    index,
                    value.as_ptr(),
                    value.as_bytes().len() as c_int,
                    transient,
                )
            },
            SQLITE_OK
        );
    }
}
