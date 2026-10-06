@echo off
echo Starting MariaDB Connector/C build script...

rem cmake generator platform: x64 (default) or Win32. Set outside the block
rem below on purpose: %VAR% inside a parenthesised block expands when the
rem block is parsed, so a default set there would not reach the cmake line.
if "%CMAKE_ARCH%"=="" set CMAKE_ARCH=x64

if not exist "C:\mariadb-connector-c.build" (
    echo Building MariaDB Connector/C from source...
    echo Using MariaDB Connector/C version: %MARIADB_CONNECTOR_C_VERSION%
    echo Using cmake platform: %CMAKE_ARCH%
    git clone --depth 1 --branch v%MARIADB_CONNECTOR_C_VERSION% https://github.com/mariadb-corporation/mariadb-connector-c.git C:\mariadb-connector-c-src
    if errorlevel 1 (
        echo ERROR: Git clone failed
        exit 1
    )
    
    cmake -A %CMAKE_ARCH% -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=C:\mariadb-connector-c.build -S C:\mariadb-connector-c-src -B C:\mariadb-connector-c-src\build
    if errorlevel 1 (
        echo ERROR: CMake configuration failed
        exit 1
    )
    
    cmake --build C:\mariadb-connector-c-src\build --config Release
    if errorlevel 1 (
        echo ERROR: CMake build failed
        exit 1
    )
    
    cmake --install C:\mariadb-connector-c-src\build --config Release
    if errorlevel 1 (
        echo ERROR: CMake install failed
        exit 1
    )
    
    echo Build completed successfully
) else (
    echo Using cached MariaDB Connector/C build
)

echo.
echo === Checking what was installed ===
if exist "C:\mariadb-connector-c.build" (
    dir C:\mariadb-connector-c.build /s /b
) else (
    echo ERROR: Build directory does not exist!
    exit 1
)

echo.
echo === Looking for header files ===
if exist "C:\mariadb-connector-c.build\include" (
    dir C:\mariadb-connector-c.build\include\*.h /s /b
) else (
    echo ERROR: Include directory does not exist!
    exit 1
)

echo.
echo Build script completed
