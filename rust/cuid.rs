use crate::{batch, random::RandomSource};
use num_bigint::BigUint;
use pyo3::exceptions::{PyOSError, PyOverflowError, PyValueError};
use pyo3::prelude::*;
use sha3::{Digest, Sha3_512};
use std::time::{SystemTime, UNIX_EPOCH};

const ALPHABET: &[u8; 36] = b"0123456789abcdefghijklmnopqrstuvwxyz";

fn base36(mut value: u128) -> String {
    let mut buffer = [0_u8; 25];
    let mut offset = buffer.len();
    loop {
        offset -= 1;
        buffer[offset] = ALPHABET[(value % 36) as usize];
        value /= 36;
        if value == 0 {
            break;
        }
    }

    // All bytes originate in the ASCII alphabet.
    String::from_utf8(buffer[offset..].to_vec()).expect("base36 is ASCII")
}

fn hash_text(data: &str) -> String {
    BigUint::from_bytes_be(&Sha3_512::digest(data.as_bytes())).to_str_radix(36)
}

fn check_length(length: usize) -> PyResult<()> {
    if !(2..=32).contains(&length) {
        return Err(PyValueError::new_err("length must be between 2 and 32"));
    }

    Ok(())
}

fn generate(
    length: usize,
    fingerprint: &str,
    counter: u64,
    random: &mut RandomSource,
) -> PyResult<String> {
    let first = (b'a' + random.sample(26)? as u8) as char;
    let mut salt = String::with_capacity(length);
    for _ in 0..length {
        salt.push(ALPHABET[random.sample(36)?] as char);
    }

    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| PyOSError::new_err(error.to_string()))?
        .as_nanos();
    let mut input = String::with_capacity(128 + fingerprint.len());
    input.push_str(&base36(nanos));
    input.push_str(&salt);
    input.push_str(&base36(counter as u128));
    input.push_str(fingerprint);
    let hash = hash_text(&input);
    let mut result = String::with_capacity(length);
    result.push(first);
    if hash.len() > 2 {
        result.push_str(&hash[2..hash.len().min(length + 1)]);
    }

    Ok(result)
}

#[pyfunction]
fn hash_base36(data: &str) -> String {
    hash_text(data)
}

#[pyfunction]
fn cuid2(length: usize, fingerprint: &str, counter: u64) -> PyResult<String> {
    check_length(length)?;
    generate(
        length,
        fingerprint,
        counter,
        &mut RandomSource::new(length + 16),
    )
}

#[pyfunction]
#[pyo3(signature = (count, length, fingerprint, counter, parallel=false))]
fn cuid2_many(
    py: Python<'_>,
    count: usize,
    length: usize,
    fingerprint: &str,
    counter: u64,
    parallel: bool,
) -> PyResult<Vec<String>> {
    check_length(length)?;
    batch::check_count(count)?;
    if counter
        .checked_add(count.saturating_sub(1) as u64)
        .is_none()
    {
        return Err(PyOverflowError::new_err("CUID2 counter exhausted"));
    }

    py.detach(|| {
        batch::random(count, parallel, length + 16, |index, random| {
            generate(length, fingerprint, counter + index as u64, random)
        })
    })
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(hash_base36, module)?)?;
    module.add_function(wrap_pyfunction!(cuid2, module)?)?;
    module.add_function(wrap_pyfunction!(cuid2_many, module)?)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha3_empty_vector() {
        let expected = BigUint::parse_bytes(
            b"a69f73cca23a9ac5c8b567dc185a756e97c982164fe25859e0d1dcc1475c80a615b2123af1f5f94c11e3e9402c3ac558f500199d95b6d3e301758586281dcd26",
            16,
        )
        .unwrap();
        assert_eq!(hash_text(""), expected.to_str_radix(36));
    }

    #[test]
    fn integer_conversion_boundaries() {
        assert_eq!(base36(0), "0");
        assert_eq!(base36(35), "z");
        assert_eq!(base36(36), "10");
        assert_eq!(base36(u64::MAX as u128), "3w5e11264sgsf");
    }
}
