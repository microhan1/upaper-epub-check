@echo off
rem 단일 EXE 빌드: dist\유페이퍼EPUB검수.exe
chcp 65001 >nul
setlocal
cd /d "%~dp0"
python -c "import PyInstaller" >nul 2>&1 || python -m pip install pyinstaller || (echo PyInstaller 설치 실패 & pause & exit /b 1)
python -m PyInstaller --noconfirm --distpath dist --workpath build upaper_check.spec
if errorlevel 1 (echo 빌드 실패 & pause & exit /b 1)
echo.
echo 빌드 완료: dist\유페이퍼EPUB검수.exe
pause
