// Hashids 1.x algorithm. See src/fuda/LICENSE.hashids for attribution.
use crate::batch;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyclass(frozen, module = "fuda._native")]
pub struct HashidsCodec {
    alphabet: Vec<u8>,
    separators: Vec<u8>,
    guards: Vec<u8>,
    salt: Vec<u32>,
    min_length: usize,
    first_alphabets: Vec<Vec<u8>>,
}

fn invalid() -> PyErr {
    PyValueError::new_err("invalid or noncanonical Hashids encoding")
}

fn shuffle(alphabet: &mut [u8], salt: &[u32]) {
    if salt.is_empty() {
        return;
    }
    let mut total = 0_u64;
    for (index, position) in (1..alphabet.len()).rev().enumerate() {
        let index = index % salt.len();
        let code = salt[index] as u64;
        total += code;
        let other = ((code + index as u64 + total) % position as u64) as usize;
        alphabet.swap(position, other);
    }
}

fn number_digits(mut value: u64, alphabet: &[u8]) -> Vec<u8> {
    let mut output = Vec::new();
    loop {
        output.push(alphabet[(value % alphabet.len() as u64) as usize]);
        value /= alphabet.len() as u64;
        if value == 0 {
            break;
        }
    }
    output.reverse();

    output
}

impl HashidsCodec {
    fn reshuffle(&self, alphabet: &mut [u8], lottery: u8) {
        let salt: Vec<_> = std::iter::once(lottery as u32)
            .chain(self.salt.iter().copied())
            .chain(alphabet.iter().map(|&byte| byte as u32))
            .take(alphabet.len())
            .collect();
        shuffle(alphabet, &salt);
    }

    fn encode_values(&self, values: &[u64]) -> PyResult<Vec<u8>> {
        if values.is_empty() {
            return Ok(Vec::new());
        }
        if values.iter().any(|&value| value > i64::MAX as u64) {
            return Err(PyValueError::new_err("number exceeds 63 bits"));
        }
        // The sum can outgrow one input number, so give it some extra room.
        let total: u128 = values
            .iter()
            .enumerate()
            .map(|(index, &value)| (value % (index as u64 + 100)) as u128)
            .sum();
        let lottery_index = (total % self.alphabet.len() as u128) as usize;
        let lottery = self.alphabet[lottery_index];
        let mut alphabet = self.first_alphabets[lottery_index].clone();
        let mut encoded = vec![lottery];
        for (index, &value) in values.iter().enumerate() {
            if index != 0 {
                self.reshuffle(&mut alphabet, lottery);
            }
            let digits = number_digits(value, &alphabet);
            let first = digits[0];
            encoded.extend(digits);
            if index + 1 < values.len() {
                encoded.push(
                    self.separators[((value % (first as u64 + index as u64))
                        % self.separators.len() as u64)
                        as usize],
                );
            }
        }
        if encoded.len() < self.min_length {
            encoded.insert(
                0,
                self.guards[((total + encoded[0] as u128) % self.guards.len() as u128) as usize],
            );
            if encoded.len() < self.min_length {
                encoded.push(
                    self.guards
                        [((total + encoded[2] as u128) % self.guards.len() as u128) as usize],
                );
            }
        }
        while encoded.len() < self.min_length {
            let salt: Vec<_> = alphabet.iter().map(|&byte| byte as u32).collect();
            shuffle(&mut alphabet, &salt);
            let half = alphabet.len() / 2;
            encoded = [&alphabet[half..], &encoded, &alphabet[..half]].concat();
            if encoded.len() > self.min_length {
                let start = (encoded.len() - self.min_length) / 2;
                encoded = encoded[start..start + self.min_length].to_vec();
            }
        }

        Ok(encoded)
    }
}

#[pymethods]
impl HashidsCodec {
    #[new]
    fn new(
        alphabet: &str,
        separators: &str,
        guards: &str,
        salt: Vec<u32>,
        min_length: usize,
    ) -> PyResult<Self> {
        let combined = format!("{alphabet}{separators}{guards}");
        let mut seen = [false; 128];
        if alphabet.len() < 2
            || separators.is_empty()
            || guards.is_empty()
            || min_length > 255
            || !combined.is_ascii()
            || combined.bytes().any(|byte| {
                let duplicate = seen[byte as usize];
                seen[byte as usize] = true;
                duplicate || !(33..=126).contains(&byte)
            })
        {
            return Err(PyValueError::new_err("invalid Hashids codec configuration"));
        }
        let mut codec = Self {
            alphabet: alphabet.as_bytes().to_vec(),
            separators: separators.as_bytes().to_vec(),
            guards: guards.as_bytes().to_vec(),
            // Python salts can contain any code point, including lone surrogates.
            salt: salt.into_iter().take(alphabet.len()).collect(),
            min_length,
            first_alphabets: Vec::with_capacity(alphabet.len()),
        };
        for &lottery in &codec.alphabet {
            // There are only a few dozen first shuffles. Keeping them here
            // avoids repeated work without needing a shared, mutable cache.
            let mut alphabet = codec.alphabet.clone();
            codec.reshuffle(&mut alphabet, lottery);
            codec.first_alphabets.push(alphabet);
        }

        Ok(codec)
    }

    fn encode(&self, values: Vec<u64>) -> PyResult<String> {
        Ok(String::from_utf8(self.encode_values(&values)?).expect("alphabet is ASCII"))
    }

    fn decode(&self, value: &str) -> PyResult<Vec<u64>> {
        if value.is_empty() {
            return Ok(Vec::new());
        }
        let parts: Vec<_> = value
            .as_bytes()
            .split(|byte| self.guards.contains(byte))
            .collect();
        let body = if matches!(parts.len(), 2 | 3) {
            parts[1]
        } else {
            parts[0]
        };
        let (&lottery, rest) = body.split_first().ok_or_else(invalid)?;
        let index = self
            .alphabet
            .iter()
            .position(|&byte| byte == lottery)
            .ok_or_else(invalid)?;
        let mut alphabet = self.first_alphabets[index].clone();
        let mut values = Vec::new();
        for (index, part) in rest
            .split(|byte| self.separators.contains(byte))
            .enumerate()
        {
            if part.is_empty() {
                return Err(invalid());
            }
            if index != 0 {
                self.reshuffle(&mut alphabet, lottery);
            }
            let mut number = 0_u64;
            for &byte in part {
                let digit = alphabet
                    .iter()
                    .position(|&char| char == byte)
                    .ok_or_else(invalid)?;
                number = number
                    .checked_mul(alphabet.len() as u64)
                    .and_then(|value| value.checked_add(digit as u64))
                    .filter(|&value| value <= i64::MAX as u64)
                    .ok_or_else(invalid)?;
            }
            values.push(number);
        }
        if self.encode_values(&values)? != value.as_bytes() {
            return Err(invalid());
        }

        Ok(values)
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
                Ok(String::from_utf8(self.encode_values(&values[index])?)
                    .expect("alphabet is ASCII"))
            })
        })
    }

    #[pyo3(signature = (values, parallel=false))]
    fn decode_many(
        &self,
        py: Python<'_>,
        values: Vec<String>,
        parallel: bool,
    ) -> PyResult<Vec<Vec<u64>>> {
        py.detach(|| batch::map(values.len(), parallel, |index| self.decode(&values[index])))
    }
}
