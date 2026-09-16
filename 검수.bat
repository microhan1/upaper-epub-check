@echo off
rem EPUB 파일을 이 배치 파일 위로 끌어다 놓으면 검수 후 HTML 보고서를 엽니다.
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
if "%~1"=="" (
  echo EPUB 파일을 이 파일 위로 끌어다 놓거나:  검수.bat 책.epub
  pause
  exit /b 1
)
for %%F in (%*) do (
  echo ===== %%~nxF =====
  python "%HERE%upaper_check.py" "%%~F" --html
  if exist "%%~dpnF_검수보고서.html" start "" "%%~dpnF_검수보고서.html"
)
echo.
pause
