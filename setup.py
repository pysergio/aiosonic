"""Setup module."""

import os
import re

from pkg_resources import parse_requirements
from setuptools import Extension, setup

try:
    from Cython.Build import cythonize
except ImportError:
    cythonize = None


# https://cython.readthedocs.io/en/latest/src/userguide/source_files_and_compilation.html#distributing-cython-modules
def no_cythonize(extensions, **_ignore):
    for extension in extensions:
        sources = []
        for sfile in extension.sources:
            path, ext = os.path.splitext(sfile)
            if ext in (".pyx", ".py"):
                if extension.language == "c++":
                    ext = ".cpp"
                else:
                    ext = ".c"
                sfile = path + ext
            sources.append(sfile)
        extension.sources[:] = sources
    return extensions


extensions = [
    Extension("aiosonic.http_parser", ["aiosonic/http_parser.pyx"]),
    Extension("aiosonic.connection", ["aiosonic/connection.pyx"]),
]

CYTHONIZE = bool(int(os.getenv("CYTHONIZE", 0))) and cythonize is not None

if CYTHONIZE:
    compiler_directives = {"language_level": 3, "embedsignature": True}
    extensions = cythonize(extensions, compiler_directives=compiler_directives)
else:
    extensions = no_cythonize(extensions)


def read_file(filename):
    """Read file correctly."""
    with open(filename) as _file:
        return _file.read().strip()


def requirements(filename):
    """Parse requirements from file."""
    return [str(r) for r in parse_requirements(read_file(filename))]


def version():
    data = read_file("./aiosonic/version.py")
    return re.findall(r"VERSION = \"([a-z0-9.]*)\"", data)[0]


# copied form uvicorn, mark to not install uvloop in windows
env_marker = (
    "sys_platform != 'win32'"
    " and sys_platform != 'cygwin'"
    " and platform_python_implementation != 'PyPy'"
)

pypy_marker = "platform_python_implementation != 'PyPy'"


def add_marks(dependencies, marks):
    """Add markers to dependencies.

    Example:
        uvloop==0.12.0 -> uvloop==0.12.0 ; sys_platform != 'win32'...
    """

    def _map_func(dependency):
        for item, marker in marks.items():
            if item in dependency:
                return dependency + marker
        return dependency

    return list(map(_map_func, dependencies))


setup(
    name="aiosonic",
    version=version(),
    description="Async http client",
    author="Johanderson Mogollon",
    author_email="johanderson@mogollon.com.ve",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    license="MIT",
    packages=[
        "aiosonic",
        "aiosonic_utils",
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    setup_requires=["pytest-runner"],
    install_requires=requirements("./requirements.txt"),
    ext_modules=extensions,
    extras_require={
        "test": add_marks(
            requirements("./test-requirements.txt"),
            {
                "uvloop": " ;" + env_marker,
                "httptools": " ;" + env_marker,
                "mypy": " ;" + pypy_marker,
                "mypy-extensions": " ;" + pypy_marker,
                "pytest-mypy": " ;" + pypy_marker,
                "typed-ast": " ;" + pypy_marker,
            },
        )
    },
)
