use std::{
    future::Future,
    path::Path,
    sync::Arc,
    task::{Context, Poll, Wake, Waker},
};

use turso::{Builder, Value};

const LIST_SQL: &str = "SELECT username, email, strftime('%Y-%m-%dT%H:%M:%SZ', created_at, 'unixepoch') FROM \"user\" ORDER BY username ASC";

pub struct User {
    pub username: String,
    pub email: String,
    pub created_at: String,
}

pub fn list_users(path: &Path) -> Result<Vec<User>, String> {
    require_existing_database(path)?;
    let path = database_path(path)?;
    block_on(async move {
        // Everything up to and including the first row fetch is attributed to
        // preparing the list. Turso reports a missing table or column at prepare
        // time, but folding the fetch in keeps the reported stage honest even if a
        // later release defers the failure to execution.
        let preparing = |failure: turso::Error| error("preparing user list", &failure);
        let database = Builder::new_local(path).build().await.map_err(preparing)?;
        let connection = database.connect().map_err(preparing)?;
        // The previous implementation opened with SQLITE_OPEN_READONLY. Turso 0.7.2
        // has no read-only builder flag, so the guarantee is reasserted on the
        // connection instead.
        connection
            .pragma_update("query_only", "true")
            .await
            .map_err(preparing)?;
        let mut statement = connection.prepare(LIST_SQL).await.map_err(preparing)?;
        let mut rows = statement.query(()).await.map_err(preparing)?;
        let mut pending = rows.next().await.map_err(preparing)?;

        let mut users = Vec::new();
        while let Some(row) = pending {
            users.push(User {
                username: column_text(&row, 0, "username")?,
                email: column_text(&row, 1, "email")?,
                created_at: column_text(&row, 2, "created_at")?,
            });
            pending = rows
                .next()
                .await
                .map_err(|failure| error("reading user list", &failure))?;
        }
        Ok(users)
    })
}

fn column_text(row: &turso::Row, index: usize, column: &str) -> Result<String, String> {
    match row
        .get_value(index)
        .map_err(|failure| error("reading user list", &failure))?
    {
        Value::Null => Err(format!("SQLite query returned NULL {column}")),
        Value::Text(text) => Ok(text),
        // libsqlite3 coerced non-text columns through sqlite3_column_text; keep that
        // behaviour rather than narrowing it.
        Value::Integer(number) => Ok(number.to_string()),
        Value::Real(number) => Ok(number.to_string()),
        Value::Blob(bytes) => Ok(String::from_utf8_lossy(&bytes).into_owned()),
    }
}

/// Drives a Turso future to completion on the calling thread.
///
/// The SDK is async, but these tools are single-shot synchronous commands. Keeping
/// the executor here confines the async surface to this module, so `main` and every
/// public signature stay synchronous.
fn block_on<F: Future>(future: F) -> F::Output {
    struct Unparker(std::thread::Thread);
    impl Wake for Unparker {
        fn wake(self: Arc<Self>) {
            self.0.unpark();
        }
        fn wake_by_ref(self: &Arc<Self>) {
            self.0.unpark();
        }
    }
    let waker = Waker::from(Arc::new(Unparker(std::thread::current())));
    let mut context = Context::from_waker(&waker);
    let mut future = std::pin::pin!(future);
    loop {
        match future.as_mut().poll(&mut context) {
            Poll::Ready(value) => return value,
            Poll::Pending => std::thread::park(),
        }
    }
}

/// `Builder::new_local` creates the database when it is missing, unlike the
/// `sqlite3_open_v2` call this replaced. These tools must never bring one into
/// existence, so the absence is rejected before Turso is reached.
fn require_existing_database(path: &Path) -> Result<(), String> {
    match std::fs::metadata(path) {
        Ok(metadata) if metadata.is_file() => Ok(()),
        Ok(_) => Err(format!("database path is not a file: {}", path.display())),
        Err(failure) => Err(format!("cannot open database: {failure}")),
    }
}

fn sidecar(path: &Path, suffix: &str) -> std::path::PathBuf {
    let mut sidecar = path.as_os_str().to_owned();
    sidecar.push(suffix);
    sidecar.into()
}

fn database_path(path: &Path) -> Result<&str, String> {
    path.to_str()
        .ok_or_else(|| "database path is not valid UTF-8".to_string())
}

fn error(action: &str, failure: &turso::Error) -> String {
    format!(
        "SQLite error while {action} (turso {}): {failure}",
        kind(failure)
    )
}

fn kind(failure: &turso::Error) -> &'static str {
    match failure {
        turso::Error::ToSqlConversionFailure(_) => "to-sql-conversion-failure",
        turso::Error::QueryReturnedNoRows => "query-returned-no-rows",
        turso::Error::ConversionFailure(_) => "conversion-failure",
        turso::Error::Busy(_) => "busy",
        turso::Error::BusySnapshot(_) => "busy-snapshot",
        turso::Error::Interrupt(_) => "interrupt",
        turso::Error::Error(_) => "error",
        turso::Error::Misuse(_) => "misuse",
        turso::Error::Constraint(_) => "constraint",
        turso::Error::Readonly(_) => "readonly",
        turso::Error::DatabaseFull(_) => "database-full",
        turso::Error::NotAdb(_) => "not-a-db",
        turso::Error::Corrupt(_) => "corrupt",
        turso::Error::IoError(..) => "io-error",
    }
}

#[cfg(test)]
pub mod test_support {
    use super::*;
    use std::fs::File;

    pub fn create_empty_database(path: &Path) {
        File::create(path).unwrap();
    }

    pub fn create_database(path: &Path, users: &[(&str, &str, &str, i64)]) {
        create_database_with_sql(
            path,
            "CREATE TABLE \"user\" (username TEXT, password TEXT, email TEXT, created_at INTEGER);",
        );
        let owned: Vec<(String, String, String, i64)> = users
            .iter()
            .map(|(username, password, email, created_at)| {
                (
                    (*username).to_owned(),
                    (*password).to_owned(),
                    (*email).to_owned(),
                    *created_at,
                )
            })
            .collect();
        let path = path.to_str().unwrap().to_owned();
        block_on(async move {
            let database = Builder::new_local(&path).build().await.unwrap();
            let connection = database.connect().unwrap();
            for user in owned {
                connection
                    .execute(
                        "INSERT INTO \"user\" (username, password, email, created_at) VALUES (?, ?, ?, ?)",
                        user,
                    )
                    .await
                    .unwrap();
            }
            connection.cacheflush().unwrap();
        });
    }

    pub fn create_database_with_sql(path: &Path, sql: &str) {
        File::create(path).unwrap();
        let path = path.to_str().unwrap().to_owned();
        let sql = sql.to_owned();
        block_on(async move {
            let database = Builder::new_local(&path).build().await.unwrap();
            let connection = database.connect().unwrap();
            connection.execute_batch(&sql).await.unwrap();
            connection.cacheflush().unwrap();
        });
    }

    /// Turso keeps a write-ahead log beside the database, so removing only the
    /// database file would leak sidecars into the temporary directory.
    pub fn remove_database(path: &Path) {
        std::fs::remove_file(path).unwrap();
        for suffix in ["-wal", "-shm"] {
            let _ = std::fs::remove_file(sidecar(path, suffix));
        }
    }
}
