#!/usr/bin/env python3
"""
Script to update version information from pyproject.toml
Works with all Python versions without external dependencies.
"""

import re
import sys
from pathlib import Path


def parse_version_from_pyproject(pyproject_path):
    """
    Parse version from pyproject.toml using simple regex
    Works without external TOML libraries
    """
    with open(pyproject_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Look for version = "x.y.z" in the [project] section
    # This regex handles various quote styles and whitespace
    version_pattern = r'^\s*version\s*=\s*["\']([^"\']+)["\']'
    
    lines = content.split('\n')
    in_project_section = False
    
    for line in lines:
        line = line.strip()
        
        # Check if we're entering the [project] section
        if line == '[project]':
            in_project_section = True
            continue
        
        # Check if we're leaving the [project] section
        if line.startswith('[') and line != '[project]':
            in_project_section = False
            continue
        
        # Look for version in the [project] section
        if in_project_section:
            match = re.match(version_pattern, line)
            if match:
                return match.group(1)
    
    return None


def update_version():
    """Update version file from pyproject.toml"""
    
    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Read version from pyproject.toml
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} not found")
        sys.exit(1)
    
    version = parse_version_from_pyproject(pyproject_path)
    if not version:
        print("Error: No version found in pyproject.toml [project] section")
        sys.exit(1)
    
    print(f"Found version: {version}")
    
    # Update release_info.py for main mariadb package
    mariadb_release_file = project_root / "mariadb" / "release_info.py"
    mariadb_release_content = f'''# This file is auto-generated during build from root pyproject.toml
# Do not edit manually

__version__ = "{version}"
'''
    
    # Create parent directory if it doesn't exist
    mariadb_release_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(mariadb_release_file, "w") as f:
        f.write(mariadb_release_content)
    
    print(f"Updated {mariadb_release_file}")
    
    # Update release_info.py for mariadb_c package to ensure version sync
    mariadb_c_release_file = project_root / "mariadb-c" / "mariadb_c" / "release_info.py"
    
    # Parse version to extract numeric parts and suffix
    # Handle formats like "2.0.0", "2.0.0.dev", "2.0.0-dev"
    version_match = re.match(r'^(\d+)\.(\d+)\.(\d+)([.-](.+)|([a-zA-Z].*))?$', version)
    if version_match:
        major = int(version_match.group(1))
        minor = int(version_match.group(2))
        patch = int(version_match.group(3))
        suffix = version_match.group(5) or version_match.group(6)
        
        if suffix:
            version_info_tuple = f"({major}, {minor}, {patch}, '{suffix}')"
        else:
            version_info_tuple = f"({major}, {minor}, {patch})"
    else:
        # Fallback for unexpected format
        version_info_tuple = "(0, 0, 0)"
    
    mariadb_c_release_content = f'''# This file is auto-generated during build from root pyproject.toml
# Do not edit manually

__version__ = "{version}"
__author__ = "MariaDB Corporation"
__version_info__ = {version_info_tuple}
'''
    
    # Create parent directory if it doesn't exist
    mariadb_c_release_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(mariadb_c_release_file, "w") as f:
        f.write(mariadb_c_release_content)
    
    print(f"Updated {mariadb_c_release_file}")
    
    # Update release_info.py for mariadb_pool package to ensure version sync
    mariadb_pool_release_file = project_root / "mariadb-pool" / "src" / "release_info.py"
    mariadb_pool_release_content = f'''# This file is auto-generated during build from root pyproject.toml
# Do not edit manually

__version__ = "{version}"
'''
    
    # Create parent directory if it doesn't exist
    mariadb_pool_release_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(mariadb_pool_release_file, "w") as f:
        f.write(mariadb_pool_release_content)
    
    print(f"Updated {mariadb_pool_release_file}")


if __name__ == "__main__":
    update_version()
