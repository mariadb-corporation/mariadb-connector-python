# Minimal stand-in for numpy's own stubs, found first through `mypy_path`.
#
# numpy is only an optional accelerator that the library uses duck-typed
# (declared as `Any`); its real stubs use the `type` statement, which mypy
# rejects under the project's python_version = "3.10" whenever numpy happens
# to be installed. This stub keeps mypy out of them.
from typing import Any

def __getattr__(name: str) -> Any: ...
