use std::{
    env,
    future::Future,
    path::Path,
    sync::Arc,
    task::{Context, Poll, Wake, Waker},
};

use turso::Builder;
use turso::sync::Builder as SyncBuilder;

const DELETE_SQL: &str = "DELETE FROM \"user\" WHERE username = ?";
const TURSO_DATABASE_URL_VAR: &str = "TURSO_DATABASE_URL";
const TURSO_AUTH_TOKEN_VAR: &str = "TURSO_AUTH_TOKEN";

/// Where a write should be routed, decided purely from the presence of the
/// `-info` sync sidecar and the two Turso Cloud sync environment variables.
/// Kept free of environment I/O so the branching decision itself is
/// unit-testable without a reachable Turso remote.
enum WriteTarget {
    Local,
    Synced {
        database_url: String,
        auth_token: String,
    },
}

// No `#[derive(Debug)]`: `auth_token` must never be printable via `{:?}`,
// including in a failed `assert_eq!`/panic message from a test.
impl std::fmt::Debug for WriteTarget {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            WriteTarget::Local => f.write_str("Local"),
            WriteTarget::Synced { database_url, .. } => {
                write!(
                    f,
                    "Synced {{ database_url: {database_url:?}, auth_token: \"<redacted>\" }}"
                )
            }
        }
    }
}

/// Turso records a mutation for replication only on a connection that enabled
/// change capture. A plain local connection stores the row but leaves no change
/// record, so the write would never reach the remote and would be dropped by the
/// next pull. When the sidecar marks the database as a synced replica, only
/// proceed if both Turso Cloud sync credentials were supplied via the
/// environment; otherwise refuse the write rather than silently lose it.
fn write_target(
    path: &Path,
    database_url: Option<String>,
    auth_token: Option<String>,
) -> Result<WriteTarget, String> {
    if !sidecar(path, "-info").exists() {
        return Ok(WriteTarget::Local);
    }
    match (database_url, auth_token) {
        (Some(database_url), Some(auth_token)) => Ok(WriteTarget::Synced {
            database_url,
            auth_token,
        }),
        _ => Err(format!(
            "{} is a Turso synced replica; refusing to write without TURSO_DATABASE_URL",
            path.display()
        )),
    }
}

fn write_target_from_env(path: &Path) -> Result<WriteTarget, String> {
    write_target(
        path,
        env::var(TURSO_DATABASE_URL_VAR).ok(),
        env::var(TURSO_AUTH_TOKEN_VAR).ok(),
    )
}

/// Strips the auth token out of an error message before it is returned, in
/// case a Turso Cloud error response or a nested `Display` impl ever echoes
/// it back.
fn scrub(auth_token: &str, message: String) -> String {
    if auth_token.is_empty() {
        return message;
    }
    message.replace(auth_token, "<redacted>")
}

pub fn delete_user(path: &Path, username: &str) -> Result<(), String> {
    require_existing_database(path)?;
    let target = write_target_from_env(path)?;
    check_no_nul(username, "username")?;
    let db_path = database_path(path)?;
    match target {
        WriteTarget::Local => block_on(async move {
            let database = Builder::new_local(db_path)
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
        }),
        WriteTarget::Synced {
            database_url,
            auth_token,
        } => {
            block_on(async move {
                let database = SyncBuilder::new_remote(db_path)
                    .with_remote_url(&database_url)
                    .with_auth_token(auth_token.clone())
                    .build()
                    .await
                    .map_err(|failure| {
                        scrub(&auth_token, error("opening synced database", &failure))
                    })?;
                database.pull().await.map_err(|failure| {
                    scrub(&auth_token, error("pulling remote changes", &failure))
                })?;
                let connection = database
                    .connect()
                    .await
                    .map_err(|failure| scrub(&auth_token, error("opening database", &failure)))?;
                let mut statement = connection.prepare(DELETE_SQL).await.map_err(|failure| {
                    scrub(&auth_token, error("preparing user delete", &failure))
                })?;
                let changed = statement
                    .execute((username,))
                    .await
                    .map_err(|failure| scrub(&auth_token, error("deleting user", &failure)))?;
                if changed == 0 {
                    return Err(format!("user not found: {username}"));
                }
                connection
                    .cacheflush()
                    .map_err(|failure| scrub(&auth_token, error("closing database", &failure)))?;
                database.push().await.map_err(|failure| {
                    scrub(&auth_token, error("pushing local changes", &failure))
                })?;
                Ok(())
            })
        }
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

    #[test]
    fn write_target_is_local_without_sidecar() {
        let path = scratch_database(true);
        assert!(matches!(
            write_target(&path, None, None),
            Ok(WriteTarget::Local)
        ));
        remove_database(&path);
    }

    #[test]
    fn write_target_refuses_sidecar_without_credentials() {
        let path = scratch_database(true);
        File::create(sidecar(&path, "-info")).unwrap();
        for (url, token) in [
            (None, None),
            (Some("https://example-remote.test".to_string()), None),
            (None, Some("test-token".to_string())),
        ] {
            let error = write_target(&path, url, token).unwrap_err();
            assert!(error.contains("Turso synced replica"));
        }
        std::fs::remove_file(sidecar(&path, "-info")).unwrap();
        remove_database(&path);
    }

    #[test]
    fn write_target_chooses_synced_when_sidecar_and_both_credentials_present() {
        let path = scratch_database(true);
        File::create(sidecar(&path, "-info")).unwrap();
        let target = write_target(
            &path,
            Some("https://example-remote.test".to_string()),
            Some("test-token".to_string()),
        )
        .unwrap();
        assert!(matches!(target, WriteTarget::Synced { .. }));
        std::fs::remove_file(sidecar(&path, "-info")).unwrap();
        remove_database(&path);
    }
}
