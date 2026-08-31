#!/bin/bash

# Build the macOS dependencies of a mariadb wheel - OpenSSL and MariaDB
# Connector/C - from source. Designed to be used as CIBW_BEFORE_ALL_MACOS.
#
# Why not Homebrew: a bottle is compiled with a minimum target of the runner's
# own macOS release, and delocate copies it into the wheel. The wheel then
# inherits that minimum, so it will not install on anything older - on a macOS
# 26 runner, openssl@3 makes a wheel that only macOS 26 can use. Building here
# lets us set the floor ourselves.
#
# The floors are the ones cibuildwheel applies to the wheel itself: 11.0 on
# arm64, which is the first macOS with Apple Silicon, and 10.9 on x86_64.
# Building the dependencies at or below the wheel's own target is what keeps
# delocate happy.
#
# MACOSX_ARCHITECTURE selects the target architecture, so x86_64 can be
# cross-compiled on an arm64 runner - GitHub has retired the Intel macOS
# runners.
#
# Reads OPENSSL_VERSION and MARIADB_CONNECTOR_C_VERSION from the environment.

set -euo pipefail
set -x

arch="${MACOSX_ARCHITECTURE:-$(uname -m)}"
prefix="/tmp/mariadb-deps-${arch}.build"

if [ "${arch}" == "x86_64" ]; then
    export MACOSX_DEPLOYMENT_TARGET=10.9
else
    export MACOSX_DEPLOYMENT_TARGET=11.0
fi

if [ -f "${prefix}/lib/mariadb/libmariadb.3.dylib" ]; then
    echo "Using the cached dependency build in ${prefix}"
    otool -L "${prefix}/lib/mariadb/libmariadb.3.dylib"
    exit 0
fi

mkdir -p /tmp/deps-src
cd /tmp/deps-src

# --- OpenSSL --------------------------------------------------------------
openssl_dir="openssl-${OPENSSL_VERSION}"
if [ ! -d "${openssl_dir}" ]; then
    curl -sSL -o openssl.tar.gz \
        "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz"
    tar xzf openssl.tar.gz
fi
pushd "${openssl_dir}"
# darwin64-<arch>-cc is the cross-compilation switch: it targets the given
# architecture whatever the host is.
./Configure "darwin64-${arch}-cc" \
    --prefix="${prefix}" \
    --openssldir="${prefix}/ssl" \
    --libdir=lib \
    no-docs \
    shared
make -j"$(sysctl -n hw.ncpu)"
# install_sw skips the man pages, which is all we need and much faster.
make install_sw
popd

# --- MariaDB Connector/C --------------------------------------------------
cc_dir="mariadb-connector-c-${arch}"
if [ ! -d "${cc_dir}" ]; then
    echo "Using MariaDB Connector/C version: ${MARIADB_CONNECTOR_C_VERSION}"
    git clone --depth 1 --branch "v${MARIADB_CONNECTOR_C_VERSION}" \
        https://github.com/mariadb-corporation/mariadb-connector-c.git "${cc_dir}"
fi
pushd "${cc_dir}"
cmake -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="${prefix}" \
      -DCMAKE_OSX_ARCHITECTURES="${arch}" \
      -DCMAKE_OSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET}" \
      -DWITH_EXTERNAL_ZLIB=On \
      -DWITH_SSL=OPENSSL \
      -DOPENSSL_ROOT_DIR="${prefix}" \
      -DCMAKE_IGNORE_PATH=/opt/homebrew/opt/openssl@3\;/usr/local/opt/openssl@3 \
      .
make -j"$(sysctl -n hw.ncpu)"
make install
popd

# Show what the wheel will end up vendoring.
otool -L "${prefix}/lib/mariadb/libmariadb.3.dylib"
