"""
Custom build backend that runs update_version.py before building.
This ensures version files are generated at build time.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from setuptools import build_meta as _orig


# Run update_version.py before any build operation
def _run_update_version() -> None:
    """Run the update_version.py script to generate version files"""
    script_path = Path(__file__).parent / "scripts" / "update_version.py"
    if script_path.exists():
        print("Running update_version.py to generate version files...")
        result = subprocess.run([sys.executable, str(script_path)],
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"Warning: update_version.py failed: {result.stderr}",
                  file=sys.stderr)
    else:
        print(f"Warning: {script_path} not found", file=sys.stderr)


# Wrap all build_meta functions to run update_version first
def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    _run_update_version()
    return _orig.build_wheel(wheel_directory, config_settings, metadata_directory)


def build_sdist(
    sdist_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    _run_update_version()
    return _orig.build_sdist(sdist_directory, config_settings)


def build_editable(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    _run_update_version()
    return _orig.build_editable(wheel_directory, config_settings, metadata_directory)


def prepare_metadata_for_build_wheel(
    metadata_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    _run_update_version()
    return _orig.prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def prepare_metadata_for_build_editable(
    metadata_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    _run_update_version()
    return _orig.prepare_metadata_for_build_editable(metadata_directory, config_settings)


# Re-export other functions from setuptools.build_meta
get_requires_for_build_wheel = _orig.get_requires_for_build_wheel
get_requires_for_build_sdist = _orig.get_requires_for_build_sdist
get_requires_for_build_editable = _orig.get_requires_for_build_editable
