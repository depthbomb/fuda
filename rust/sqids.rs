// Sqids algorithm. See src/fuda/LICENSE.sqids for attribution.
use crate::batch;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::HashSet;

#[pyclass(frozen, module = "fuda._native")]
pub struct SqidsCodec {
    alphabet: Vec<u8>,
    min_length: usize,
    exact: HashSet<String>,
    ends: Vec<String>,
    anywhere: Vec<String>,
}

fn invalid(message: &str) -> PyErr {
    PyValueError::new_err(message.to_owned())
}

fn shuffle(alphabet: &mut [u8]) {
    let size = alphabet.len();
    for index in 0..size - 1 {
        let other = size - 1 - index;
        let target = (index * other + alphabet[index] as usize + alphabet[other] as usize) % size;
        alphabet.swap(index, target);
    }
}

impl SqidsCodec {
    fn encode_values(&self, values: &[u64]) -> PyResult<String> {
        if values.is_empty() {
            return Ok(String::new());
        }
        let size = self.alphabet.len();
        let mut offset = values.len() % size;
        for (index, &value) in values.iter().enumerate() {
            if value > i64::MAX as u64 {
                return Err(invalid("number exceeds 63 bits"));
            }
            offset =
                (offset + self.alphabet[(value % size as u64) as usize] as usize + index % size)
                    % size;
        }
        for increment in 0..=size {
            // A blocked spelling gets a new prefix and another shuffle.
            let start = (offset + increment) % size;
            let mut alphabet = self.alphabet.clone();
            alphabet.rotate_left(start);
            let mut encoded = vec![alphabet[0]];
            alphabet.reverse();
            for (index, &value) in values.iter().enumerate() {
                let mut number = value;
                let begin = encoded.len();
                loop {
                    encoded.push(alphabet[(number % (size - 1) as u64) as usize + 1]);
                    number /= (size - 1) as u64;
                    if number == 0 {
                        break;
                    }
                }
                encoded[begin..].reverse();
                if index + 1 < values.len() {
                    encoded.push(alphabet[0]);
                    shuffle(&mut alphabet);
                }
            }
            if encoded.len() < self.min_length {
                // This separator marks the end of the numbers. Anything after
                // it is padding, not another encoded value.
                encoded.push(alphabet[0]);
                while encoded.len() < self.min_length {
                    shuffle(&mut alphabet);
                    encoded.extend(&alphabet[..size.min(self.min_length - encoded.len())]);
                }
            }
            let encoded = String::from_utf8(encoded).expect("alphabet is ASCII");
            let lowered = encoded.to_ascii_lowercase();
            if !self.exact.contains(&lowered)
                && !self
                    .ends
                    .iter()
                    .any(|word| lowered.starts_with(word) || lowered.ends_with(word))
                && !self.anywhere.iter().any(|word| lowered.contains(word))
            {
                return Ok(encoded);
            }
        }

        Err(invalid(
            "blocklist prevents encoding these numbers with this alphabet",
        ))
    }
}

#[pymethods]
impl SqidsCodec {
    #[new]
    fn new(
        alphabet: &str,
        min_length: usize,
        exact: Vec<String>,
        ends: Vec<String>,
        anywhere: Vec<String>,
    ) -> PyResult<Self> {
        if !alphabet.is_ascii()
            || alphabet.len() < 3
            || min_length > 255
            || alphabet.bytes().collect::<HashSet<_>>().len() != alphabet.len()
        {
            return Err(invalid("invalid Sqids codec configuration"));
        }

        Ok(Self {
            alphabet: alphabet.as_bytes().to_vec(),
            min_length,
            exact: exact.into_iter().collect(),
            ends,
            anywhere,
        })
    }

    fn encode(&self, values: Vec<u64>) -> PyResult<String> {
        self.encode_values(&values)
    }

    fn decode(&self, value: &str, canonical: bool) -> PyResult<Vec<u64>> {
        if value.is_empty() {
            return Ok(Vec::new());
        }
        if !value.bytes().all(|byte| self.alphabet.contains(&byte)) {
            return Err(invalid(
                "identifier contains characters outside the Sqids alphabet",
            ));
        }
        let offset = self
            .alphabet
            .iter()
            .position(|&byte| byte == value.as_bytes()[0])
            .expect("alphabet checked");
        let mut alphabet = self.alphabet.clone();
        alphabet.rotate_left(offset);
        alphabet.reverse();
        let mut remaining = &value.as_bytes()[1..];
        let mut numbers = Vec::new();
        while !remaining.is_empty() {
            let separator = remaining.iter().position(|&byte| byte == alphabet[0]);
            let end = separator.unwrap_or(remaining.len());
            let chunk = &remaining[..end];
            if chunk.is_empty() {
                break;
            }
            let mut number = 0_u64;
            for byte in chunk {
                let digit = alphabet[1..]
                    .iter()
                    .position(|char| char == byte)
                    .expect("alphabet checked");
                number = number
                    .checked_mul((alphabet.len() - 1) as u64)
                    .and_then(|value| value.checked_add(digit as u64))
                    .filter(|&value| value <= i64::MAX as u64)
                    .ok_or_else(|| invalid("decoded number exceeds 2**63-1"))?;
            }
            numbers.push(number);
            remaining = if separator.is_some() {
                &remaining[end + 1..]
            } else {
                &[]
            };
            if separator.is_some() {
                shuffle(&mut alphabet);
            }
        }
        // Sqids normally accepts alternate spellings. Only compare the exact
        // encoding when the caller asks for it.
        if canonical && self.encode_values(&numbers)? != value {
            return Err(invalid(
                "noncanonical Sqids identifier for this configuration",
            ));
        }

        Ok(numbers)
    }

    #[pyo3(signature = (values, parallel=false))]
    fn encode_many(
        &self,
        py: Python<'_>,
        values: Vec<Vec<u64>>,
        parallel: bool,
    ) -> PyResult<Vec<String>> {
        py.detach(|| {
            batch::map(values.len(), parallel, |index| {
                self.encode_values(&values[index])
            })
        })
    }

    #[pyo3(signature = (values, canonical=false, parallel=false))]
    fn decode_many(
        &self,
        py: Python<'_>,
        values: Vec<String>,
        canonical: bool,
        parallel: bool,
    ) -> PyResult<Vec<Vec<u64>>> {
        py.detach(|| {
            batch::map(values.len(), parallel, |index| {
                self.decode(&values[index], canonical)
            })
        })
    }
}
