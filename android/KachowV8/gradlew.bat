@echo off
set GRADLE_VERSION=9.4.1
set BASE_DIR=%USERPROFILE%\.gradle\mcqueen-bootstrap
set GRADLE_HOME=%BASE_DIR%\gradle-%GRADLE_VERSION%
set ZIP_FILE=%BASE_DIR%\gradle-%GRADLE_VERSION%-bin.zip

if not exist "%GRADLE_HOME%\bin\gradle.bat" (
  if not exist "%BASE_DIR%" mkdir "%BASE_DIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip' -OutFile '%ZIP_FILE%'"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force '%ZIP_FILE%' '%BASE_DIR%'"
)

call "%GRADLE_HOME%\bin\gradle.bat" %*
