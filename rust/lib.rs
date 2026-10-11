use pyo3::prelude::*;

mod batch;
mod cuid;
mod encoding;
mod hashids;
mod random;
mod sqids;

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    cuid::register(module)?;
    encoding::register(module)?;
    random::register(module)?;
    module.add_class::<hashids::HashidsCodec>()?;
    module.add_class::<sqids::SqidsCodec>()?;
    module.add_function(wrap_pyfunction!(batch::_after_fork, module)?)?;

    Ok(())
}
