from setuptools import setup
from setuptools_rust import Binding, RustExtension

setup(
    rust_extensions=[
        RustExtension('fuda._native', path='Cargo.toml', binding=Binding.PyO3, py_limited_api=True, debug=False)
    ],
    options={'bdist_wheel': {'py_limited_api': 'cp314'}},
)
