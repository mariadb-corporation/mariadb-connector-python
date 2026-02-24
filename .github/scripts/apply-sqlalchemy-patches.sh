#!/bin/bash
set -e

SQLALCHEMY_DIR="${1:-sqlalchemy}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCHES_DIR="$SCRIPT_DIR/../patches"

echo "Applying SQLAlchemy patches..."
echo "SQLAlchemy directory: $SQLALCHEMY_DIR"
echo "Patches directory: $PATCHES_DIR"

if [ ! -d "$SQLALCHEMY_DIR" ]; then
    echo "Error: SQLAlchemy directory not found: $SQLALCHEMY_DIR"
    exit 1
fi

cd "$SQLALCHEMY_DIR"

# Apply MariaDB Enterprise version detection patch
if [ -f "$PATCHES_DIR/sqlalchemy-mariadb-enterprise-version.patch" ]; then
    echo "Applying MariaDB Enterprise version detection patch..."
    if patch -p1 --dry-run < "$PATCHES_DIR/sqlalchemy-mariadb-enterprise-version.patch" > /dev/null 2>&1; then
        patch -p1 < "$PATCHES_DIR/sqlalchemy-mariadb-enterprise-version.patch"
        echo "✓ MariaDB Enterprise version patch applied successfully"
    else
        echo "⚠ Patch already applied or conflicts detected, skipping..."
    fi
else
    echo "⚠ Patch file not found: $PATCHES_DIR/sqlalchemy-mariadb-enterprise-version.patch"
fi

# Apply PyPy error message compatibility patch
if [ -f "$PATCHES_DIR/sqlalchemy-pypy-error-message.patch" ]; then
    echo "Applying PyPy error message compatibility patch..."
    if patch -p1 --dry-run < "$PATCHES_DIR/sqlalchemy-pypy-error-message.patch" > /dev/null 2>&1; then
        patch -p1 < "$PATCHES_DIR/sqlalchemy-pypy-error-message.patch"
        echo "✓ PyPy error message patch applied successfully"
    else
        echo "⚠ Patch already applied or conflicts detected, skipping..."
    fi
else
    echo "⚠ Patch file not found: $PATCHES_DIR/sqlalchemy-pypy-error-message.patch"
fi

# Apply MariaDB 12.3 CONNECTION table option removal patch
if [ -f "$PATCHES_DIR/sqlalchemy-mariadb-12.3-connection-option.patch" ]; then
    echo "Applying MariaDB 12.3 CONNECTION table option patch..."
    if patch -p1 --dry-run < "$PATCHES_DIR/sqlalchemy-mariadb-12.3-connection-option.patch" > /dev/null 2>&1; then
        patch -p1 < "$PATCHES_DIR/sqlalchemy-mariadb-12.3-connection-option.patch"
        echo "✓ MariaDB 12.3 CONNECTION option patch applied successfully"
    else
        echo "⚠ Patch already applied or conflicts detected, skipping..."
    fi
else
    echo "⚠ Patch file not found: $PATCHES_DIR/sqlalchemy-mariadb-12.3-connection-option.patch"
fi

echo "Patch application complete!"
