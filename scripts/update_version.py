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
    mariadb_c_release_file = project_root / "mariadb_c" / "src" / "release_info.py"
    mariadb_c_release_content = f'''# This file is auto-generated during build from root pyproject.toml
# Do not edit manually

__version__ = "{version}"
__author__ = "MariaDB Corporation"
__version_info__ = {tuple(int(x) for x in version.split('-')[0].split('.'))}
'''
    
    # Create parent directory if it doesn't exist
    mariadb_c_release_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(mariadb_c_release_file, "w") as f:
        f.write(mariadb_c_release_content)
    
    print(f"Updated {mariadb_c_release_file}")
    
    # Update release_info.py for mariadb_pool package to ensure version sync
    mariadb_pool_release_file = project_root / "mariadb_pool" / "src" / "release_info.py"
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
