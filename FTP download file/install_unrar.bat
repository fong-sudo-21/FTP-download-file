@echo off
setlocal EnableExtensions

:: --- Elevate to Admin ---
net session >nul 2>&1
if %errorlevel% NEQ 0 (
  echo [*] Dang yeu cau quyen Administrator...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

:: --- Detect arch & set download URL ---
set "ARCH=%PROCESSOR_ARCHITECTURE%"
if /I "%ARCH%"=="AMD64" (
  set "URL=https://www.rarlab.com/rar/unrarw64.exe"
) else if /I "%ARCH%"=="ARM64" (
  rem RARLAB chua co goi ARM64 rieng -> dung ban x64 tren Windows ARM (emulation)
  set "URL=https://www.rarlab.com/rar/unrarw64.exe"
) else (
  set "URL=https://www.rarlab.com/rar/unrarw32.exe"
)

set "TARGET_DIR=%ProgramFiles%\UnRAR"
set "SFX=%TEMP%\unrar_sfx.exe"

echo [1/4] Tai UnRAR tu: %URL%
powershell -NoProfile -Command "try{Invoke-WebRequest -Uri '%URL%' -OutFile '%SFX%' -UseBasicParsing}catch{exit 1}"
if errorlevel 1 (
  echo [!] Loi: Khong tai duoc goi cai dat UnRAR.
  exit /b 1
)

echo [2/4] Cai dat vao: "%TARGET_DIR%"
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%" >nul 2>&1

:: unrarw*.exe la SFX; dung tham so SFX de giai nen im lang den thu muc dich
"%SFX%" -y -o+ -inul -d"%TARGET_DIR%"
if errorlevel 1 (
  echo [!] Loi: Giai nen that bai.
  exit /b 1
)

echo [3/4] Them vao PATH he thong (neu chua co)...
for /f "usebackq tokens=*" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine')"`) do set "CURPATH=%%P"
echo %CURPATH% | find /I "%TARGET_DIR%" >nul
if errorlevel 1 (
  powershell -NoProfile -Command "$p=[Environment]::GetEnvironmentVariable('Path','Machine'); if($p -notmatch [regex]::Escape('%TARGET_DIR%')){[Environment]::SetEnvironmentVariable('Path', ($p.TrimEnd(';')+';%TARGET_DIR%'), 'Machine')}"
) else (
  echo [i] PATH da co: %TARGET_DIR%
)

echo [4/4] Kiem tra cai dat...
where unrar >nul 2>&1
if errorlevel 1 (
  echo [!] Chua thay "unrar" trong PATH cua cmd hien tai.
  echo     Hay mo cua so Command Prompt moi (hoac dang xuat/dang nhap lai) de cap nhat PATH.
) else (
  for /f "delims=" %%v in ('unrar ^| findstr /I "UNRAR"') do echo [+] Cai dat thanh cong: %%v
)

del "%SFX%" >nul 2>&1
echo [OK] Hoan tat.
exit /b 0
