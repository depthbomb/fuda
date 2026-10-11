use num_bigint::BigUint;
use pyo3::exceptions::{PyOSError, PyOverflowError, PyValueError};
use pyo3::prelude::*;
use rayon::prelude::*;
use sha3::{Digest, Sha3_512};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

mod encoding;
mod hashids;
mod sqids;

const ALPHABET: &[u8; 36] = b"0123456789abcdefghijklmnopqrstuvwxyz";
const MAX_BATCH: usize = 1_000_000;
static PARALLEL_PID: AtomicU32 = AtomicU32::new(0);

fn pool_belongs_to_process(owner: &AtomicU32, pid: u32) -> bool {
    // Set this before Rayon starts initialization. A child must not touch an
    // inherited pool or its initialization lock, even with a new generator.
    match owner.compare_exchange(0, pid, Ordering::Relaxed, Ordering::Relaxed) {
        Ok(_) => true,
        Err(original) => original != u32::MAX && original == pid,
    }
}

#[pyfunction]
fn _after_fork() {
    if PARALLEL_PID.load(Ordering::Relaxed) != 0 {
        // Keep descendants serial even if the original process's PID is reused.
        PARALLEL_PID.store(u32::MAX, Ordering::Relaxed);
    }
}

fn entropy(data: &mut [u8]) -> PyResult<()> {
    getrandom::fill(data).map_err(|error| PyOSError::new_err(error.to_string()))
}

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

fn generate(length: usize, fingerprint: &str, counter: u64, initial: &[u8]) -> PyResult<String> {
    let mut refill = [0_u8; 128];
    let mut bytes = initial;
    let mut offset = 0;
    let mut first = None;
    let mut salt = String::with_capacity(length);

    while first.is_none() || salt.len() < length {
        if offset == bytes.len() {
            entropy(&mut refill)?;
            bytes = &refill;
            offset = 0;
        }
        let value = bytes[offset];
        offset += 1;
        if first.is_none() {
            if value < 234 {
                first = Some((b'a' + value % 26) as char);
            }
        } else if value < 252 {
            salt.push(ALPHABET[(value % 36) as usize] as char);
        }
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
    result.push(first.expect("first letter was sampled"));
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
    let mut bytes = [0_u8; 128];
    let needed = (length + 16).min(bytes.len());
    entropy(&mut bytes[..needed])?;

    generate(length, fingerprint, counter, &bytes[..needed])
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
    if count > MAX_BATCH {
        return Err(PyValueError::new_err(
            "batch count must not exceed 1000000; use iter_ids",
        ));
    }
    if counter
        .checked_add(count.saturating_sub(1) as u64)
        .is_none()
    {
        return Err(PyOverflowError::new_err("CUID2 counter exhausted"));
    }
    let fingerprint = fingerprint.to_owned();
    let parallel =
        parallel && count >= 32 && pool_belongs_to_process(&PARALLEL_PID, std::process::id());

    py.detach(move || {
        let stride = length + 16;
        let mut random = vec![0_u8; stride * count];
        entropy(&mut random)?;
        if parallel {
            random
                .par_chunks_exact(stride)
                .enumerate()
                .map(|(index, bytes)| generate(length, &fingerprint, counter + index as u64, bytes))
                .collect()
        } else {
            random
                .chunks_exact(stride)
                .enumerate()
                .map(|(index, bytes)| generate(length, &fingerprint, counter + index as u64, bytes))
                .collect()
        }
    })
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    encoding::register(module)?;
    module.add_class::<hashids::HashidsCodec>()?;
    module.add_class::<sqids::SqidsCodec>()?;
    module.add_function(wrap_pyfunction!(_after_fork, module)?)?;
    module.add_function(wrap_pyfunction!(hash_base36, module)?)?;
    module.add_function(wrap_pyfunction!(cuid2, module)?)?;
    module.add_function(wrap_pyfunction!(cuid2_many, module)?)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inherited_pool_uses_serial_path() {
        let owner = AtomicU32::new(0);
        assert!(pool_belongs_to_process(&owner, 100));
        assert!(pool_belongs_to_process(&owner, 100));
        assert!(!pool_belongs_to_process(&owner, 200));
        assert!(!pool_belongs_to_process(&owner, 300));
        assert_eq!(owner.load(Ordering::Relaxed), 100);
    }

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
