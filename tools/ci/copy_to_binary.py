#!/usr/bin/env python3

"""
Create the mariadb-binary package by renaming and patching mariadb_c

This script creates a binary distribution package
The binary package includes precompiled wheels with all dependencies bundled.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

curdir = Path(__file__).parent
pdir = curdir / "../.."

if (target := (pdir / "mariadb_binary")).exists():
    raise Exception(f"path {target} already exists")


def sed_i(pattern: str, repl: str, filename: str | Path) -> None:
    """Replace pattern in file (in-place)"""
    with open(filename, "rb") as f:
        data = f.read()

    if (newdata := re.sub(pattern.encode("utf8"), repl.encode("utf8"), data)) != data:
        with open(filename, "wb") as f:
            f.write(newdata)


# Copy mariadb_c to mariadb_binary
shutil.copytree(pdir / "mariadb_c", target)

# Clean up build artifacts and egg-info directories
for cleanup_dir in ["build", "dist", "__pycache__", ".pytest_cache"]:
    cleanup_path = target / cleanup_dir
    if cleanup_path.exists():
        shutil.rmtree(cleanup_path)

# Remove build backend files if accidentally copied (mariadb_c shouldn't have them)
for build_file in ["build.py", "_build_backend.py"]:
    if (target / build_file).exists():
        (target / build_file).unlink()

# Remove egg-info directories (will be recreated with correct name)
for egg_info in target.rglob("*.egg-info"):
    if egg_info.is_dir():
        shutil.rmtree(egg_info)

# Rename mariadb_c/ subdirectory to mariadb_binary/
if (target / "mariadb_c").exists():
    shutil.move(str(target / "mariadb_c"), str(target / "mariadb_binary"))
else:
    raise Exception(f"Expected 'mariadb_c' directory not found in {target}")

# Create README for binary package
readme_content = """# MariaDB Connector/Python - Binary Package

This is the binary distribution of MariaDB Connector/Python, which includes
precompiled C extensions for better performance.

## Installation

```bash
pip install mariadb-binary
```

## Usage

The binary package is a drop-in replacement for the main mariadb package:

```python
import mariadb

conn = mariadb.connect(
    user="your_user",
    password="your_password",
    host="localhost",
    database="your_database"
)
```

## Differences from mariadb-c

- **mariadb-binary**: Precompiled wheels with bundled dependencies (recommended for most users)
- **mariadb-c**: Source distribution requiring compilation (for advanced users)
- **mariadb**: Pure Python implementation (fallback, slower performance)

## License

See LICENSE file in the main mariadb-connector-python repository.
"""

with open(target / "README.md", "w") as f:
    f.write(readme_content)

# Update pyproject.toml - replace all mariadb_c with mariadb_binary
if (target / "pyproject.toml").exists():
    sed_i(r'\bmariadb_c\b', 'mariadb_binary', target / "pyproject.toml")
    # Ensure build-backend is set correctly (not using custom build backends)
    sed_i(r'build-backend\s*=\s*["\'](?:build|_build_backend)["\']', 'build-backend = "setuptools.build_meta"', target / "pyproject.toml")
    # Remove backend-path if it exists (it references the root build backend)
    sed_i(r'backend-path\s*=\s*\[.*?\]\n?', '', target / "pyproject.toml")

# Update version.py if it exists
if (target / "mariadb_binary" / "version.py").exists():
    sed_i(r'mariadb-c', 'mariadb-binary', target / "mariadb_binary" / "version.py")

# Update __impl__ to "binary" in all Python files
for dirpath, dirnames, filenames in os.walk(target):
    for filename in filenames:
        if os.path.splitext(filename)[1] not in (".py", ".pyx", ".pxd"):
            continue
        filepath = Path(dirpath) / filename
        
        # Replace module name references
        sed_i(r"\bmariadb_c\b", "mariadb_binary", filepath)
        
        # Set implementation type to "binary"
        if filename in ("__init__.py", "version.py"):
            sed_i(r'__impl__\s*=\s*["\']c["\']', '__impl__ = "binary"', filepath)

print(f"[OK] Created mariadb_binary package at {target}")
