use crate::batch;
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use std::collections::HashSet;

pub struct RandomSource {
    bytes: [u8; 4096],
    offset: usize,
    capacity: usize,
}

#[pyclass(frozen, module = "fuda._native")]
pub struct RandomAlphabet {
    alphabet: Vec<char>,
}

impl RandomSource {
    pub fn new(capacity: usize) -> Self {
        let capacity = capacity.clamp(64, 4096);
        Self {
            bytes: [0; 4096],
            offset: capacity,
            capacity,
        }
    }

    pub fn fill(&mut self, output: &mut [u8]) -> PyResult<()> {
        let mut written = 0;
        while written < output.len() {
            if self.offset == self.capacity {
                getrandom::fill(&mut self.bytes[..self.capacity])
                    .map_err(|error| PyOSError::new_err(error.to_string()))?;
                self.offset = 0;
            }
            let count = (output.len() - written).min(self.capacity - self.offset);
            output[written..written + count]
                .copy_from_slice(&self.bytes[self.offset..self.offset + count]);
            written += count;
            self.offset += count;
        }

        Ok(())
    }

    pub fn sample(&mut self, radix: usize) -> PyResult<usize> {
        let limit = 256 - 256 % radix;
        loop {
            let mut byte = [0];
            self.fill(&mut byte)?;
            if (byte[0] as usize) < limit {
                return Ok(byte[0] as usize % radix);
            }
        }
    }
}

#[pymethods]
impl RandomAlphabet {
    #[new]
    fn new(alphabet: &str) -> PyResult<Self> {
        let alphabet: Vec<_> = alphabet.chars().collect();
        if !(2..=256).contains(&alphabet.len())
            || alphabet.iter().collect::<HashSet<_>>().len() != alphabet.len()
        {
            return Err(PyValueError::new_err(
                "alphabet requires 2 to 256 unique characters",
            ));
        }

        Ok(Self { alphabet })
    }

    #[pyo3(signature = (count, length, parallel=false))]
    fn generate_many(
        &self,
        py: Python<'_>,
        count: usize,
        length: usize,
        parallel: bool,
    ) -> PyResult<Vec<String>> {
        if !(1..=1_000_000).contains(&length) {
            return Err(PyValueError::new_err(
                "length must be between 1 and 1000000",
            ));
        }

        py.detach(|| {
            batch::random(count, parallel, length.saturating_mul(2), |_, random| {
                let mut value = String::with_capacity(length);
                for _ in 0..length {
                    value.push(self.alphabet[random.sample(self.alphabet.len())?]);
                }

                Ok(value)
            })
        })
    }
}

#[pyfunction]
#[pyo3(signature = (count, mask, fixed=0, parallel=false))]
pub fn random_u128_many(
    py: Python<'_>,
    count: usize,
    mask: u128,
    fixed: u128,
    parallel: bool,
) -> PyResult<Vec<u128>> {
    py.detach(|| {
        batch::random(count, parallel, 16, |_, random| {
            let mut bytes = [0; 16];
            random.fill(&mut bytes)?;

            Ok((u128::from_be_bytes(bytes) & mask) | fixed)
        })
    })
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<RandomAlphabet>()?;
    module.add_function(wrap_pyfunction!(random_u128_many, module)?)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejection_sampling_gives_each_symbol_equal_weight() {
        for radix in 2..=256 {
            let mut random = RandomSource::new(4096);
            for (index, byte) in random.bytes.iter_mut().enumerate() {
                *byte = index as u8;
            }
            random.offset = 0;
            let mut counts = vec![0; radix];
            for _ in 0..2 * (256 / radix) * radix {
                counts[random.sample(radix).unwrap()] += 1;
            }
            assert!(counts.iter().all(|&count| count == 2 * (256 / radix)));
        }
    }
}
