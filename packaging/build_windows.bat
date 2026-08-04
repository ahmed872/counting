@echo off
REM ============================================================
REM  Builds the Windows copy that gets sent to the restaurant.
REM
REM  Run this ON A WINDOWS MACHINE that has Python installed.
REM  Double-click it, or run it from a terminal. It installs what
REM  it needs, builds, and leaves the finished program in:
REM
REM      dist\نظام-إدارة-المطعم\
REM
REM  Zip that folder and send it. Nothing else is required on the
REM  restaurant's computer - no Python, no installation.
REM ============================================================

REM UTF-8, otherwise the Arabic file names come out as garbage.
chcp 65001 >nul

cd /d "%~dp0\.."

echo.
echo ============================================
echo   بناء نسخة ويندوز
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [خطأ] Python غير مثبت على هذا الجهاز.
    echo نزّله من https://www.python.org/downloads/
    echo ومهم جدا: علّم على "Add Python to PATH" اثناء التثبيت.
    echo.
    pause
    exit /b 1
)

echo [1/3] تثبيت المكتبات المطلوبة...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt pyinstaller
if errorlevel 1 (
    echo [خطأ] فشل تثبيت المكتبات. تأكد من الاتصال بالإنترنت.
    pause
    exit /b 1
)

echo [2/3] توليد دليل الاستخدام PDF...
python docs\build_manual.py
if errorlevel 1 (
    echo [تحذير] لم يتم توليد الدليل. سيتم استخدام النسخة الموجودة.
)

echo [3/3] بناء البرنامج...
python -m PyInstaller packaging\restaurant_erp.spec --noconfirm --distpath dist --workpath packaging\temp
if errorlevel 1 (
    echo [خطأ] فشل البناء.
    pause
    exit /b 1
)

REM Sits next to the .exe where the owner will actually see it. Bundling it as
REM PyInstaller data would hide it inside _internal\.
copy /y "packaging\اقرأني-قبل-التشغيل.txt" "dist\نظام-إدارة-المطعم\" >nul

echo.
echo ============================================
echo   تم البناء بنجاح
echo ============================================
echo.
echo البرنامج جاهز في المجلد:
echo     dist\نظام-إدارة-المطعم\
echo.
echo اضغط على المجلد بزر الماوس الايمن ثم:
echo     Send to  ^>  Compressed (zipped) folder
echo وابعت الملف المضغوط.
echo.
pause
