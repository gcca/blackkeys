use std::{
    ffi::CStr,
    fs::File,
    io::Read,
    os::raw::{c_char, c_int, c_uint, c_void},
};

const ARGON2_OK: c_int = 0;
const ARGON2_MEMORY_KIB: c_uint = 65_536;
const ARGON2_TIME_COST: c_uint = 3;
const ARGON2_PARALLELISM: c_uint = 4;
const ARGON2_HASH_LEN: usize = 32;
const ARGON2_SALT_LEN: usize = 16;

#[link(name = "argon2")]
unsafe extern "C" {
    fn argon2_encodedlen(
        time: c_uint,
        memory: c_uint,
        parallelism: c_uint,
        salt_length: usize,
        hash_length: usize,
        variant: c_int,
    ) -> usize;
    fn argon2id_hash_encoded(
        time: c_uint,
        memory: c_uint,
        parallelism: c_uint,
        password: *const c_void,
        password_length: usize,
        salt: *const c_void,
        salt_length: usize,
        hash_length: usize,
        encoded: *mut c_char,
        encoded_length: usize,
    ) -> c_int;
    #[cfg(test)]
    fn argon2id_verify(
        encoded: *const c_char,
        password: *const c_void,
        password_length: usize,
    ) -> c_int;
}

pub fn hash_password(password: &str) -> Result<String, String> {
    let mut salt = [0_u8; ARGON2_SALT_LEN];
    File::open("/dev/urandom")
        .and_then(|mut file| file.read_exact(&mut salt))
        .map_err(|error| format!("cannot read password-hashing entropy: {error}"))?;

    let encoded_len = unsafe {
        argon2_encodedlen(
            ARGON2_TIME_COST,
            ARGON2_MEMORY_KIB,
            ARGON2_PARALLELISM,
            salt.len(),
            ARGON2_HASH_LEN,
            2,
        )
    };
    let mut encoded = vec![0_u8; encoded_len];
    let status = unsafe {
        argon2id_hash_encoded(
            ARGON2_TIME_COST,
            ARGON2_MEMORY_KIB,
            ARGON2_PARALLELISM,
            password.as_ptr().cast(),
            password.len(),
            salt.as_ptr().cast(),
            salt.len(),
            ARGON2_HASH_LEN,
            encoded.as_mut_ptr().cast(),
            encoded.len(),
        )
    };
    if status != ARGON2_OK {
        return Err(format!(
            "password hashing failed (libargon2 status {status})"
        ));
    }
    CStr::from_bytes_until_nul(&encoded)
        .map_err(|_| "password hashing returned an invalid encoded hash".to_string())?
        .to_str()
        .map_err(|_| "password hashing returned a non-UTF-8 encoded hash".to_string())
        .map(str::to_owned)
}

#[cfg(test)]
pub fn verify(encoded: &str, password: &str) -> bool {
    let encoded = std::ffi::CString::new(encoded).expect("PHC hash cannot contain a NUL byte");
    unsafe {
        argon2id_verify(encoded.as_ptr(), password.as_ptr().cast(), password.len()) == ARGON2_OK
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn produces_a_verifiable_argon2id_phc_hash() {
        let hash = hash_password("correct horse battery staple").unwrap();
        assert!(hash.starts_with("$argon2id$"));
        assert!(verify(&hash, "correct horse battery staple"));
        assert!(!verify(&hash, "wrong password"));
    }
}
