use std::{
    future::Future,
    path::Path,
    sync::Arc,
    task::{Context, Poll, Wake, Waker},
};

use turso::Builder;

const DELETE_SQL: &str = "DELETE FROM \"user\" WHERE username = ?";

pub fn delete_user(path: &Path, username: &str) -> Result<(), String> {
    require_existing_database(path)?;
    refuse_synced_replica(path)?;
    check_no_nul(username, "username")?;
    let path = database_path(path)?;
    block_on(async move {
        let database = Builder::new_local(path)
            .build()
            .await
            .map_err(|failure| error("opening database", &failure))?;
        let connection = database
            .connect()
            .map_err(|failure| error("opening database", &failure))?;
        let mut statement = connection
            .prepare(DELETE_SQL)
            .await
            .map_err(|failure| error("preparing user delete", &failure))?;
        let changed = statement
            .execute((username,))
            .await
            .map_err(|failure| error("deleting user", &failure))?;
        if changed == 0 {
            return Err(format!("user not found: {username}"));
        }
        connection
            .cacheflush()
            .map_err(|failure| error("closing database", &failure))?;
        Ok(())
    })
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

/// Turso records a mutation for replication only on a connection that enabled
/// change capture. A plain local connection stores the row but leaves no change
/// record, so the write would never reach the remote and would be dropped by the
/// next pull. Refuse the write rather than lose it.
fn refuse_synced_replica(path: &Path) -> Result<(), String> {
    if sidecar(path, "-info").exists() {
        return Err(format!(
            "{} is a Turso synced replica; refusing to write without TURSO_DATABASE_URL",
            path.display()
        ));
    }
    Ok(())
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

fn check_no_nul(value: &str, field: &str) -> Result<(), String> {
    if value.contains('\0') {
        return Err(format!("{field} contains a NUL byte"));
    }
    Ok(())
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
mod tests {
    use super::*;
    use std::{
        fs::File,
        path::PathBuf,
        sync::atomic::{AtomicU64, Ordering},
        time::{SystemTime, UNIX_EPOCH},
    };

    fn scratch_database(schema: bool) -> PathBuf {
        // The clock alone is not unique: tests run in parallel and can start within
        // the same tick, which Turso reports as a locked database rather than
        // silently sharing the file the way the previous SQLite fixtures did.
        static COUNTER: AtomicU64 = AtomicU64::new(0);
        let path = std::env::temp_dir().join(format!(
            "blackkeys-remove-user-{}-{}-{}.db",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            COUNTER.fetch_add(1, Ordering::Relaxed)
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
        let path = path.to_str().unwrap().to_owned();
        let sql = sql.to_owned();
        block_on(async move {
            let database = Builder::new_local(&path).build().await.unwrap();
            let connection = database.connect().unwrap();
            connection.execute_batch(&sql).await.unwrap();
            connection.cacheflush().unwrap();
        });
    }

    fn insert_user(path: &Path, username: &str, password: &str, email: &str) {
        let path = path.to_str().unwrap().to_owned();
        let (username, password, email) =
            (username.to_owned(), password.to_owned(), email.to_owned());
        block_on(async move {
            let database = Builder::new_local(&path).build().await.unwrap();
            let connection = database.connect().unwrap();
            connection
                .execute(
                    "INSERT INTO \"user\" (username, password, email) VALUES (?, ?, ?)",
                    (username, password, email),
                )
                .await
                .unwrap();
            connection.cacheflush().unwrap();
        });
    }

    fn usernames(path: &Path) -> Vec<String> {
        let path = path.to_str().unwrap().to_owned();
        block_on(async move {
            let database = Builder::new_local(&path).build().await.unwrap();
            let connection = database.connect().unwrap();
            let mut rows = connection
                .query("SELECT username FROM \"user\" ORDER BY username ASC", ())
                .await
                .unwrap();
            let mut names = Vec::new();
            while let Some(row) = rows.next().await.unwrap() {
                match row.get_value(0).unwrap() {
                    turso::Value::Text(username) => names.push(username),
                    value => panic!("unexpected username value {value:?}"),
                }
            }
            names
        })
    }

    /// Turso keeps a write-ahead log beside the database, so removing only the
    /// database file would leak sidecars into the temporary directory.
    fn remove_database(path: &Path) {
        std::fs::remove_file(path).unwrap();
        for suffix in ["-wal", "-shm"] {
            let _ = std::fs::remove_file(sidecar(path, suffix));
        }
    }

    #[test]
    fn deletes_matching_user_and_leaves_others() {
        let path = scratch_database(true);
        insert_user(&path, "alice", "hash-alice", "alice@example.test");
        insert_user(&path, "bob", "hash-bob", "bob@example.test");
        delete_user(&path, "alice").unwrap();
        assert_eq!(usernames(&path), ["bob"]);
        remove_database(&path);
    }

    #[test]
    fn fails_when_user_is_missing_and_leaves_existing_rows() {
        let path = scratch_database(true);
        insert_user(&path, "bob", "hash-bob", "bob@example.test");
        let error = delete_user(&path, "alice").unwrap_err();
        assert!(error.contains("user not found: alice"));
        assert_eq!(usernames(&path), ["bob"]);
        remove_database(&path);
    }

    #[test]
    fn fails_without_user_table() {
        let path = scratch_database(false);
        assert!(delete_user(&path, "alice").is_err());
        remove_database(&path);
    }

    #[test]
    fn refuses_to_write_to_a_synced_replica() {
        let path = scratch_database(true);
        insert_user(&path, "bob", "hash-bob", "bob@example.test");
        File::create(sidecar(&path, "-info")).unwrap();
        let error = delete_user(&path, "bob").unwrap_err();
        assert!(error.contains("Turso synced replica"));
        assert_eq!(usernames(&path), ["bob"]);
        std::fs::remove_file(sidecar(&path, "-info")).unwrap();
        remove_database(&path);
    }
}
