use crate::random::RandomSource;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rayon::prelude::*;
use std::sync::atomic::{AtomicU32, Ordering};

const MAX_BATCH: usize = 1_000_000;
static PARALLEL_PID: AtomicU32 = AtomicU32::new(0);

fn pool_belongs_to_process(owner: &AtomicU32, pid: u32) -> bool {
    // Record ownership before Rayon initializes its pool or acquires its locks.
    match owner.compare_exchange(0, pid, Ordering::Relaxed, Ordering::Relaxed) {
        Ok(_) => true,
        Err(original) => original != u32::MAX && original == pid,
    }
}

fn use_workers(count: usize, parallel: bool) -> bool {
    parallel && count >= 256 && pool_belongs_to_process(&PARALLEL_PID, std::process::id())
}

pub fn check_count(count: usize) -> PyResult<()> {
    if count > MAX_BATCH {
        return Err(PyValueError::new_err("batch count must not exceed 1000000"));
    }

    Ok(())
}

pub fn map<T, F>(count: usize, parallel: bool, operation: F) -> PyResult<Vec<T>>
where
    T: Send,
    F: Fn(usize) -> PyResult<T> + Send + Sync,
{
    check_count(count)?;
    if use_workers(count, parallel) {
        (0..count).into_par_iter().map(operation).collect()
    } else {
        (0..count).map(operation).collect()
    }
}

pub fn random<T, F>(
    count: usize,
    parallel: bool,
    bytes_per_item: usize,
    operation: F,
) -> PyResult<Vec<T>>
where
    T: Send,
    F: Fn(usize, &mut RandomSource) -> PyResult<T> + Send + Sync,
{
    check_count(count)?;
    let capacity = count.saturating_mul(bytes_per_item);
    if use_workers(count, parallel) {
        (0..count)
            .into_par_iter()
            .with_min_len(128)
            .map_init(
                || RandomSource::new(capacity),
                |random, index| operation(index, random),
            )
            .collect()
    } else {
        let mut random = RandomSource::new(capacity);
        (0..count)
            .map(|index| operation(index, &mut random))
            .collect()
    }
}

#[pyfunction]
pub fn _after_fork() {
    if PARALLEL_PID.load(Ordering::Relaxed) != 0 {
        // Keep descendants serial even if the original process's PID is reused.
        PARALLEL_PID.store(u32::MAX, Ordering::Relaxed);
    }
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
        owner.store(u32::MAX, Ordering::Relaxed);
        assert!(!pool_belongs_to_process(&owner, 100));
    }

    #[test]
    fn ordered_mapping() {
        for parallel in [false, true] {
            let values = map(1024, parallel, |index| Ok(index * 3)).unwrap();
            assert_eq!(values, (0..1024).map(|index| index * 3).collect::<Vec<_>>());
        }
    }
}
