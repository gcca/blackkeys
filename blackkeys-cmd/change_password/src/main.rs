mod argon2id;
mod sqlite3;

use std::{env, path::PathBuf, process};

struct Opts {
    dbpath: String,
    username: String,
    password: String,
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
    match change_password(&opts) {
        Ok(path) => println!(
            "changed password for {} in {}",
            opts.username,
            path.display()
        ),
        Err(error) => {
            eprintln!("error: {error}");
            process::exit(1);
        }
    }
}

fn change_password(opts: &Opts) -> Result<PathBuf, String> {
    validate_opts(opts)?;
    let path = std::fs::canonicalize(&opts.dbpath)
        .map_err(|error| format!("cannot resolve database path: {error}"))?;
    let password_hash = argon2id::hash_password(&opts.password)?;
    sqlite3::update_password(&path, &opts.username, &password_hash)?;
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
    if opts.password.is_empty() {
        return Err("password must not be empty".into());
    }
    Ok(())
}

fn wants_help(args: &[String]) -> bool {
    args.iter().any(|arg| arg == "-h" || arg == "--help")
}
fn usage() -> &'static str {
    "Usage: blackkeys-change_password -u <username> -p <password> [-d <dbpath>] [-h|--help]"
}

fn parse_opts<I>(mut args: I) -> Result<Opts, String>
where
    I: Iterator<Item = String>,
{
    let (mut username, mut password, mut dbpath) = (None, None, None);
    while let Some(flag) = args.next() {
        let value = match flag.as_str() {
            "-u" | "--username" | "-p" | "--password" | "-d" | "--dbpath" => match args.next() {
                Some(value) if !value.starts_with('-') => value,
                _ => return Err(format!("missing value for {flag}")),
            },
            _ if flag.starts_with('-') => return Err(format!("unknown option: {flag}")),
            _ => return Err(format!("unexpected argument: {flag}")),
        };
        let slot = match flag.as_str() {
            "-u" | "--username" => &mut username,
            "-p" | "--password" => &mut password,
            "-d" | "--dbpath" => &mut dbpath,
            _ => unreachable!(),
        };
        if slot.replace(value).is_some() {
            return Err(format!("duplicate option: {flag}"));
        }
    }
    Ok(Opts {
        username: username.ok_or_else(|| "missing required option: --username".to_string())?,
        password: password.ok_or_else(|| "missing required option: --password".to_string())?,
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
            password: "test-password".into(),
        }
    }
    #[test]
    fn parses_short_options_with_default_dbpath() {
        let o = parse(&["-u", "alice", "-p", "test-password"]).unwrap();
        assert_eq!(o.username, "alice");
        assert_eq!(o.password, "test-password");
        assert_eq!(o.dbpath, "./blackkeys.db");
    }
    #[test]
    fn parses_long_options_with_dbpath() {
        assert_eq!(
            parse(&[
                "--username",
                "alice",
                "--password",
                "test-password",
                "--dbpath",
                "/tmp/blackkeys.db"
            ])
            .unwrap()
            .dbpath,
            "/tmp/blackkeys.db"
        );
    }
    #[test]
    fn rejects_each_missing_required_option() {
        assert!(parse(&["-p", "x"]).is_err());
        assert!(parse(&["-u", "x"]).is_err());
        assert!(parse(&[]).is_err());
    }
    #[test]
    fn rejects_unknown_duplicate_and_valueless_options() {
        assert!(parse(&["-u", "a", "-p", "p", "--unknown"]).is_err());
        assert!(parse(&["-u", "a", "--username", "b", "-p", "p"]).is_err());
        assert!(parse(&["-u", "a", "-p"]).is_err());
    }
    #[test]
    fn recognizes_help_aliases() {
        assert!(wants_help(&["-h".into()]));
        assert!(wants_help(&["--help".into()]));
        assert!(!wants_help(&["-u".into(), "alice".into()]));
    }
    #[test]
    fn validates_service_contract() {
        assert!(validate_opts(&valid()).is_ok());
        for username in ["", "a b", "a\tb", "a\u{7f}b"] {
            let mut opts = valid();
            opts.username = username.into();
            assert!(validate_opts(&opts).is_err());
        }
        let mut opts = valid();
        opts.username = "a".repeat(251);
        assert!(validate_opts(&opts).is_err());
        let mut opts = valid();
        opts.password.clear();
        assert!(validate_opts(&opts).is_err());
    }
    #[test]
    fn refuses_to_touch_missing_database() {
        let path = std::env::temp_dir().join(format!("blackkeys-missing-{}", process::id()));
        let _ = std::fs::remove_file(&path);
        let mut opts = valid();
        opts.dbpath = path.to_string_lossy().into_owned();
        assert!(change_password(&opts).is_err());
        assert!(!path.exists());
    }
}
