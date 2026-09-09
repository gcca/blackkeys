mod sqlite3;

use std::{env, process};

#[cfg(test)]
use std::path::PathBuf;

struct Opts {
    dbpath: String,
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if wants_help(&args) {
        println!("{}", usage());
        return;
    }
    let opts = match parse_opts(args.into_iter()) {
        Ok(opts) => opts,
        Err(error) => {
            eprintln!("error: {error}\n{}", usage());
            process::exit(2);
        }
    };
    match list_users(&opts) {
        Ok(output) => print!("{output}"),
        Err(error) => {
            eprintln!("error: {error}");
            process::exit(1);
        }
    }
}

fn list_users(opts: &Opts) -> Result<String, String> {
    let path = std::fs::canonicalize(&opts.dbpath)
        .map_err(|error| format!("cannot resolve database path: {error}"))?;
    let users = sqlite3::list_users(&path)?;
    Ok(format_table(&users))
}

fn wants_help(args: &[String]) -> bool {
    args.iter().any(|arg| arg == "-h" || arg == "--help")
}

fn usage() -> &'static str {
    "Usage: blackkeys-list_users [-d <dbpath>] [-h|--help]"
}

fn parse_opts<I>(mut args: I) -> Result<Opts, String>
where
    I: Iterator<Item = String>,
{
    let mut dbpath = None;
    while let Some(flag) = args.next() {
        let value = match flag.as_str() {
            "-d" | "--dbpath" => match args.next() {
                Some(value) if !value.starts_with('-') => value,
                _ => return Err(format!("missing value for {flag}")),
            },
            _ if flag.starts_with('-') => return Err(format!("unknown option: {flag}")),
            _ => return Err(format!("unexpected argument: {flag}")),
        };
        if dbpath.replace(value).is_some() {
            return Err(format!("duplicate option: {flag}"));
        }
    }
    Ok(Opts {
        dbpath: dbpath.unwrap_or_else(|| "./blackkeys.db".into()),
    })
}

fn format_table(users: &[sqlite3::User]) -> String {
    const USERNAME: &str = "USERNAME";
    const EMAIL: &str = "EMAIL";
    const CREATED_AT: &str = "CREATED AT (UTC)";

    let username_width = users
        .iter()
        .map(|user| user.username.chars().count())
        .fold(USERNAME.len(), usize::max);
    let email_width = users
        .iter()
        .map(|user| user.email.chars().count())
        .fold(EMAIL.len(), usize::max);
    let created_at_width = users
        .iter()
        .map(|user| user.created_at.chars().count())
        .fold(CREATED_AT.len(), usize::max);

    let mut output = format!(
        "{USERNAME:<username_width$}  {EMAIL:<email_width$}  {CREATED_AT:<created_at_width$}\n{}  {}  {}\n",
        "-".repeat(username_width),
        "-".repeat(email_width),
        "-".repeat(created_at_width),
    );
    if users.is_empty() {
        output.push_str("(no users)\n");
    } else {
        for user in users {
            output.push_str(&format!(
                "{:<username_width$}  {:<email_width$}  {:<created_at_width$}\n",
                user.username, user.email, user.created_at,
            ));
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        time::{SystemTime, UNIX_EPOCH},
    };

    fn parse(args: &[&str]) -> Result<Opts, String> {
        parse_opts(args.iter().map(|arg| arg.to_string()))
    }

    fn scratch_path(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "blackkeys-list-users-{label}-{}-{}.db",
            process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn parses_default_and_custom_database_paths() {
        assert_eq!(parse(&[]).unwrap().dbpath, "./blackkeys.db");
        assert_eq!(
            parse(&["--dbpath", "/tmp/blackkeys.db"]).unwrap().dbpath,
            "/tmp/blackkeys.db"
        );
        assert_eq!(parse(&["-d", "custom.db"]).unwrap().dbpath, "custom.db");
    }

    #[test]
    fn recognizes_help_aliases() {
        assert!(wants_help(&["-h".into()]));
        assert!(wants_help(&["--help".into()]));
        assert!(!wants_help(&["-d".into(), "users.db".into()]));
    }

    #[test]
    fn rejects_duplicate_unknown_missing_and_positional_options() {
        assert!(parse(&["-d", "one.db", "--dbpath", "two.db"]).is_err());
        assert!(parse(&["--unknown"]).is_err());
        assert!(parse(&["-d"]).is_err());
        assert!(parse(&["users.db"]).is_err());
    }

    #[test]
    fn lists_safe_fields_in_username_order_with_utc_timestamps() {
        let path = scratch_path("ordered");
        sqlite3::test_support::create_database(
            &path,
            &[
                (
                    "zoe",
                    "super-secret-hash",
                    "zoe@example.test",
                    1_735_689_600,
                ),
                ("alice", "do-not-print", "alice@example.test", 0),
            ],
        );

        let output = list_users(&Opts {
            dbpath: path.to_string_lossy().into_owned(),
        })
        .unwrap();

        assert!(output.starts_with("USERNAME  EMAIL"));
        assert!(output.contains("alice     alice@example.test  1970-01-01T00:00:00Z"));
        assert!(output.contains("zoe       zoe@example.test    2025-01-01T00:00:00Z"));
        assert!(output.find("alice").unwrap() < output.find("zoe").unwrap());
        assert!(!output.contains("super-secret-hash"));
        assert!(!output.contains("do-not-print"));
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn prints_headers_and_an_empty_table_message() {
        let path = scratch_path("empty");
        sqlite3::test_support::create_database(&path, &[]);

        assert_eq!(
            list_users(&Opts {
                dbpath: path.to_string_lossy().into_owned(),
            })
            .unwrap(),
            "USERNAME  EMAIL  CREATED AT (UTC)\n--------  -----  ----------------\n(no users)\n"
        );
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn missing_database_is_not_created() {
        let path = scratch_path("missing");
        assert!(!path.exists());
        assert!(
            list_users(&Opts {
                dbpath: path.to_string_lossy().into_owned(),
            })
            .is_err()
        );
        assert!(!path.exists());
    }

    #[test]
    fn missing_user_table_and_invalid_timestamps_are_errors() {
        let missing_table = scratch_path("missing-table");
        sqlite3::test_support::create_empty_database(&missing_table);
        let before = fs::read(&missing_table).unwrap();
        let error = list_users(&Opts {
            dbpath: missing_table.to_string_lossy().into_owned(),
        })
        .unwrap_err();
        assert!(error.contains("SQLite error while preparing user list"));
        assert_eq!(fs::read(&missing_table).unwrap(), before);
        fs::remove_file(missing_table).unwrap();

        let malformed_schema = scratch_path("malformed-schema");
        sqlite3::test_support::create_database_with_sql(
            &malformed_schema,
            "CREATE TABLE \"user\" (username TEXT, password TEXT, email TEXT);",
        );
        let error = list_users(&Opts {
            dbpath: malformed_schema.to_string_lossy().into_owned(),
        })
        .unwrap_err();
        assert!(error.contains("SQLite error while preparing user list"));
        fs::remove_file(malformed_schema).unwrap();

        let invalid_timestamp = scratch_path("invalid-timestamp");
        sqlite3::test_support::create_database_with_sql(
            &invalid_timestamp,
            "CREATE TABLE \"user\" (username TEXT, password TEXT, email TEXT, created_at INTEGER); \
             INSERT INTO \"user\" VALUES ('alice', 'hash', 'alice@example.test', NULL);",
        );
        let error = list_users(&Opts {
            dbpath: invalid_timestamp.to_string_lossy().into_owned(),
        })
        .unwrap_err();
        assert!(error.contains("NULL created_at"));
        fs::remove_file(invalid_timestamp).unwrap();
    }
}
