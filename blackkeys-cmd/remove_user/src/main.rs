mod sqlite3;

use std::{env, path::PathBuf, process};

struct Opts {
    dbpath: String,
    username: String,
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
    match remove_user(&opts) {
        Ok(path) => println!("removed user {} from {}", opts.username, path.display()),
        Err(error) => {
            eprintln!("error: {error}");
            process::exit(1);
        }
    }
}

fn remove_user(opts: &Opts) -> Result<PathBuf, String> {
    validate_opts(opts)?;
    let path = std::fs::canonicalize(&opts.dbpath)
        .map_err(|error| format!("cannot resolve database path: {error}"))?;
    sqlite3::delete_user(&path, &opts.username)?;
    Ok(path)
}

fn validate_opts(opts: &Opts) -> Result<(), String> {
    if opts.username.is_empty() {
        return Err("username must not be empty".into());
    }
    if opts.username.len() > 250 {
        return Err("username must be at most 250 UTF-8 bytes".into());
    }
    if opts
        .username
        .bytes()
        .any(|byte| byte <= b' ' || byte == 0x7f)
    {
        return Err("username must not contain ASCII spaces or control characters".into());
    }
    Ok(())
}

fn wants_help(args: &[String]) -> bool {
    args.iter().any(|arg| arg == "-h" || arg == "--help")
}

fn usage() -> &'static str {
    "Usage: blackkeys-remove_user <username> [-d <dbpath>] [-h|--help]"
}

fn parse_opts<I>(mut args: I) -> Result<Opts, String>
where
    I: Iterator<Item = String>,
{
    let mut username = None;
    let mut dbpath = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "-d" | "--dbpath" => {
                let value = match args.next() {
                    Some(value) if !value.starts_with('-') => value,
                    _ => return Err(format!("missing value for {arg}")),
                };
                if dbpath.replace(value).is_some() {
                    return Err(format!("duplicate option: {arg}"));
                }
            }
            _ if arg.starts_with('-') => return Err(format!("unknown option: {arg}")),
            _ => {
                if username.replace(arg).is_some() {
                    return Err("unexpected argument: extra username".into());
                }
            }
        }
    }
    Ok(Opts {
        username: username.ok_or_else(|| "missing required argument: username".to_string())?,
        dbpath: dbpath.unwrap_or_else(|| "./blackkeys.db".into()),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(args: &[&str]) -> Result<Opts, String> {
        parse_opts(args.iter().map(|arg| arg.to_string()))
    }

    fn valid() -> Opts {
        Opts {
            dbpath: "x".into(),
            username: "alice".into(),
        }
    }

    #[test]
    fn parses_positional_username_with_default_dbpath() {
        let o = parse(&["alice"]).unwrap();
        assert_eq!(o.username, "alice");
        assert_eq!(o.dbpath, "./blackkeys.db");
    }

    #[test]
    fn parses_dbpath_before_and_after_username() {
        let before = parse(&["-d", "custom.db", "alice"]).unwrap();
        assert_eq!(before.username, "alice");
        assert_eq!(before.dbpath, "custom.db");
        let after = parse(&["bob", "--dbpath", "/tmp/blackkeys.db"]).unwrap();
        assert_eq!(after.username, "bob");
        assert_eq!(after.dbpath, "/tmp/blackkeys.db");
    }

    #[test]
    fn rejects_missing_extra_unknown_and_duplicate_options() {
        assert!(parse(&[]).is_err());
        assert!(parse(&["alice", "bob"]).is_err());
        assert!(parse(&["--unknown", "alice"]).is_err());
        assert!(parse(&["-d"]).is_err());
        assert!(parse(&["-d", "one.db", "--dbpath", "two.db", "alice"]).is_err());
    }

    #[test]
    fn recognizes_help_aliases() {
        assert!(wants_help(&["-h".into()]));
        assert!(wants_help(&["--help".into()]));
        assert!(!wants_help(&["alice".into()]));
    }

    #[test]
    fn validates_username_contract() {
        assert!(validate_opts(&valid()).is_ok());
        for username in ["", "a b", "a\tb", "a\u{7f}b"] {
            let mut opts = valid();
            opts.username = username.into();
            assert!(validate_opts(&opts).is_err());
        }
        let mut opts = valid();
        opts.username = "a".repeat(251);
        assert!(validate_opts(&opts).is_err());
    }

    #[test]
    fn refuses_to_touch_missing_database() {
        let path = std::env::temp_dir().join(format!("blackkeys-missing-{}", process::id()));
        let _ = std::fs::remove_file(&path);
        let mut opts = valid();
        opts.dbpath = path.to_string_lossy().into_owned();
        assert!(remove_user(&opts).is_err());
        assert!(!path.exists());
    }
}
