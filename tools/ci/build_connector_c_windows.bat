@echo off
echo Starting MariaDB Connector/C build script...

if not exist "C:\mariadb-connector-c.build" (
    echo Building MariaDB Connector/C from source...
    git clone --depth 1 --branch v%MARIADB_CONNECTOR_C_VERSION% https://github.com/mariadb-corporation/mariadb-connector-c.git C:\mariadb-connector-c-src
    if errorlevel 1 (
        echo ERROR: Git clone failed
        exit /b 1
    )
    
    cmake -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=C:\mariadb-connector-c.build -S C:\mariadb-connector-c-src -B C:\mariadb-connector-c-src\build
    if errorlevel 1 (
        echo ERROR: CMake configuration failed
        exit /b 1
    )
    
    cmake --build C:\mariadb-connector-c-src\build --config Release
    if errorlevel 1 (
        echo ERROR: CMake build failed
        exit /b 1
    )
    
    cmake --install C:\mariadb-connector-c-src\build --config Release
    if errorlevel 1 (
        echo ERROR: CMake install failed
        exit /b 1
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
    exit /b 1
)

echo.
echo === Looking for header files ===
if exist "C:\mariadb-connector-c.build\include" (
    dir C:\mariadb-connector-c.build\include\*.h /s /b
) else (
    echo ERROR: Include directory does not exist!
    exit /b 1
)

echo.
echo Build script completed
