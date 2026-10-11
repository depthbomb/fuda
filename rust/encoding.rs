use data_encoding::{
    BASE32_NOPAD, BASE64, BASE64_NOPAD, BASE64URL, BASE64URL_NOPAD, HEXLOWER, HEXUPPER,
};
use num_bigint::BigUint;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

const BASE36: &str = "0123456789abcdefghijklmnopqrstuvwxyz";
const BASE58: &str = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
const MAX_WIDTH: usize = 1_000_000;

#[pyclass(frozen, module = "fuda._native")]
pub struct RadixCodec {
    alphabet: Vec<u8>,
    digits: [u8; 128],
}

fn invalid(message: &str) -> PyErr {
    PyValueError::new_err(message.to_owned())
}

impl RadixCodec {
    fn make(alphabet: &str) -> PyResult<Self> {
        if !alphabet.is_ascii() || !(2..=128).contains(&alphabet.len()) {
            return Err(invalid(
                "alphabet requires 2 to 128 unique ASCII characters",
            ));
        }
        let mut digits = [u8::MAX; 128];
        for (index, &byte) in alphabet.as_bytes().iter().enumerate() {
            if digits[byte as usize] != u8::MAX {
                return Err(invalid("alphabet characters must be unique"));
            }
            digits[byte as usize] = index as u8;
        }

        Ok(Self {
            alphabet: alphabet.as_bytes().to_vec(),
            digits,
        })
    }

    fn digit(&self, byte: u8) -> PyResult<u8> {
        let digit = self.digits.get(byte as usize).copied().unwrap_or(u8::MAX);
        if digit == u8::MAX {
            return Err(invalid(
                "identifier contains a character outside its alphabet",
            ));
        }

        Ok(digit)
    }

    fn width(width: usize) -> PyResult<()> {
        if width > MAX_WIDTH {
            return Err(invalid("encoding width exceeds 1000000"));
        }

        Ok(())
    }

    fn big_digits(&self, text: &str) -> PyResult<BigUint> {
        let digits = text
            .bytes()
            .map(|byte| self.digit(byte))
            .collect::<PyResult<Vec<_>>>()?;

        // The lookup above has already checked every digit, including case.
        Ok(BigUint::from_radix_be(&digits, self.alphabet.len() as u32)
            .expect("digits match the radix"))
    }
}

#[pymethods]
impl RadixCodec {
    #[new]
    fn new(alphabet: &str) -> PyResult<Self> {
        Self::make(alphabet)
    }

    fn encode_u128(&self, mut value: u128, width: usize) -> PyResult<String> {
        Self::width(width)?;
        let radix = self.alphabet.len() as u128;
        let mut output = vec![self.alphabet[0]; width];
        let mut offset = width;
        while value != 0 {
            if offset == 0 {
                return Err(invalid("integer exceeds the encoding width"));
            }
            offset -= 1;
            output[offset] = self.alphabet[(value % radix) as usize];
            value /= radix;
        }

        Ok(String::from_utf8(output).expect("alphabet is ASCII"))
    }

    fn encode_bytes(&self, value: &[u8], width: usize) -> PyResult<String> {
        Self::width(width)?;
        let number = BigUint::from_bytes_be(value);
        let digits = number.to_radix_be(self.alphabet.len() as u32);
        if digits.len() > width && !(width == 0 && number.bits() == 0) {
            return Err(invalid("integer exceeds the encoding width"));
        }
        let mut output = vec![self.alphabet[0]; width.saturating_sub(digits.len())];
        if width > 0 {
            output.extend(digits.iter().map(|&digit| self.alphabet[digit as usize]));
        }

        Ok(String::from_utf8(output).expect("alphabet is ASCII"))
    }

    fn decode_u128(&self, text: &str, width: usize, bits: u32) -> PyResult<u128> {
        if text.len() != width {
            return Err(invalid("identifier has the wrong length"));
        }
        if bits > 128 {
            return Err(invalid("binary width exceeds 128 bits"));
        }
        let mut number = 0_u128;
        for byte in text.bytes() {
            number = number
                .checked_mul(self.alphabet.len() as u128)
                .and_then(|value| value.checked_add(self.digit(byte).ok()? as u128))
                .ok_or_else(|| invalid("invalid digit or identifier exceeds its binary width"))?;
        }
        if bits < 128 && number >= (1_u128 << bits) {
            return Err(invalid("identifier exceeds its binary width"));
        }

        Ok(number)
    }

    fn decode_bytes<'py>(
        &self,
        py: Python<'py>,
        text: &str,
        width: usize,
        bits: u64,
    ) -> PyResult<Bound<'py, PyBytes>> {
        if text.len() != width {
            return Err(invalid("identifier has the wrong length"));
        }
        let number = self.big_digits(text)?;
        if number.bits() > bits {
            return Err(invalid("identifier exceeds its binary width"));
        }

        Ok(PyBytes::new(py, &number.to_bytes_be()))
    }
}

fn base_encode(data: &[u8], alphabet: &str) -> String {
    // An integer conversion would lose leading zero bytes. Multibase keeps them.
    let zeros = data.iter().take_while(|&&byte| byte == 0).count();
    let mut output = vec![alphabet.as_bytes()[0]; zeros];
    if zeros < data.len() {
        let digits = BigUint::from_bytes_be(data).to_radix_be(alphabet.len() as u32);
        output.extend(
            digits
                .iter()
                .map(|&digit| alphabet.as_bytes()[digit as usize]),
        );
    }

    String::from_utf8(output).expect("alphabet is ASCII")
}

fn base_decode(text: &str, alphabet: &str) -> PyResult<Vec<u8>> {
    let codec = RadixCodec::make(alphabet)?;
    let zeros = text
        .bytes()
        .take_while(|&byte| byte == alphabet.as_bytes()[0])
        .count();
    let mut output = vec![0; zeros];
    if zeros < text.len() {
        output.extend(codec.big_digits(&text[zeros..])?.to_bytes_be());
    }

    Ok(output)
}

#[pyfunction]
pub fn multibase_encode(data: &[u8], prefix: &str) -> PyResult<String> {
    let encoded = match prefix {
        "b" => BASE32_NOPAD.encode(data).to_ascii_lowercase(),
        "B" => BASE32_NOPAD.encode(data),
        "f" => HEXLOWER.encode(data),
        "F" => HEXUPPER.encode(data),
        "z" => base_encode(data, BASE58),
        "k" => base_encode(data, BASE36),
        "K" => base_encode(data, BASE36).to_ascii_uppercase(),
        "m" => BASE64_NOPAD.encode(data),
        "M" => BASE64.encode(data),
        "u" => BASE64URL_NOPAD.encode(data),
        "U" => BASE64URL.encode(data),
        _ => return Err(invalid("unsupported multibase encoding")),
    };

    Ok(prefix.to_owned() + &encoded)
}

#[pyfunction]
pub fn multibase_decode<'py>(py: Python<'py>, value: &str) -> PyResult<Bound<'py, PyBytes>> {
    if value.is_empty() || !value.is_ascii() {
        return Err(invalid("expected an ASCII multibase string"));
    }
    let (prefix, payload) = value.split_at(1);
    let decoded = match prefix {
        "b" => BASE32_NOPAD.decode(payload.to_ascii_uppercase().as_bytes()),
        "B" => BASE32_NOPAD.decode(payload.as_bytes()),
        "f" => HEXLOWER.decode(payload.as_bytes()),
        "F" => HEXUPPER.decode(payload.as_bytes()),
        "m" => BASE64_NOPAD.decode(payload.as_bytes()),
        "M" => BASE64.decode(payload.as_bytes()),
        "u" => BASE64URL_NOPAD.decode(payload.as_bytes()),
        "U" => BASE64URL.decode(payload.as_bytes()),
        "z" | "k" | "K" => Ok(base_decode(
            payload,
            match prefix {
                "z" => BASE58,
                "k" => BASE36,
                _ => "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            },
        )?),
        _ => return Err(invalid("unsupported multibase prefix")),
    }
    .map_err(|error| invalid(&format!("invalid multibase: {error}")))?;
    // Reject alternate case and spare padding bits, even if decoding worked.
    if multibase_encode(&decoded, prefix)? != value {
        return Err(invalid("noncanonical multibase spelling or padding"));
    }

    Ok(PyBytes::new(py, &decoded))
}

const CONSONANTS: &[u8] = b"bdfghjklmnprstvz";
const VOWELS: &[u8] = b"aiou";

#[pyfunction]
pub fn proquint_encode(data: &[u8]) -> PyResult<String> {
    if data.is_empty() || data.len() % 2 != 0 {
        return Err(invalid(
            "Proquint requires a nonempty, even number of bytes",
        ));
    }
    let mut output = String::with_capacity(data.len() / 2 * 6 - 1);
    for (index, chunk) in data.chunks_exact(2).enumerate() {
        if index > 0 {
            output.push('-');
        }
        let number = u16::from_be_bytes([chunk[0], chunk[1]]) as usize;
        output.push(CONSONANTS[number >> 12] as char);
        output.push(VOWELS[(number >> 10) & 3] as char);
        output.push(CONSONANTS[(number >> 6) & 15] as char);
        output.push(VOWELS[(number >> 4) & 3] as char);
        output.push(CONSONANTS[number & 15] as char);
    }

    Ok(output)
}

#[pyfunction]
pub fn proquint_decode<'py>(py: Python<'py>, value: &str) -> PyResult<Bound<'py, PyBytes>> {
    let mut output = Vec::with_capacity(value.len() / 3);
    for word in value.split('-') {
        if word.len() != 5 {
            return Err(invalid(
                "each Proquint word must contain five lowercase letters",
            ));
        }
        let mut number = 0_u16;
        for (index, byte) in word.bytes().enumerate() {
            let alphabet = if index % 2 == 0 { CONSONANTS } else { VOWELS };
            let digit = alphabet
                .iter()
                .position(|&char| char == byte)
                .ok_or_else(|| invalid("invalid Proquint consonant or vowel"))?;
            number = number * alphabet.len() as u16 + digit as u16;
        }
        output.extend(number.to_be_bytes());
    }

    Ok(PyBytes::new(py, &output))
}

#[pyfunction]
pub fn hex_checkdigit(value: &str) -> PyResult<String> {
    let mut total = 0;
    for (index, byte) in value.bytes().rev().enumerate() {
        let digit = (byte as char)
            .to_digit(16)
            .ok_or_else(|| invalid("invalid hex digit"))?;
        // Luhn mod 16 doubles every other digit, starting at the right.
        let product = digit * if index % 2 == 0 { 2 } else { 1 };
        total = (total + product / 16 + product % 16) % 16;
    }

    Ok(format!("{:x}", (16 - total) % 16))
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<RadixCodec>()?;
    module.add_function(wrap_pyfunction!(multibase_encode, module)?)?;
    module.add_function(wrap_pyfunction!(multibase_decode, module)?)?;
    module.add_function(wrap_pyfunction!(proquint_encode, module)?)?;
    module.add_function(wrap_pyfunction!(proquint_decode, module)?)?;
    module.add_function(wrap_pyfunction!(hex_checkdigit, module)?)?;

    Ok(())
}
