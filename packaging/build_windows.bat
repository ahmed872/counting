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

REM The manual and the icon are committed, not regenerated, and this refuses
REM to build if either has been damaged. Regenerating the manual on a machine
REM without the right fonts produces a PDF of empty boxes.
echo [2/4] التحقق من الدليل والايقونة...
python packaging\verify_artifacts.py
if errorlevel 1 (
    echo [خطأ] الدليل او الايقونة غير سليمة.
    pause
    exit /b 1
)

echo [3/4] بناء نسخة الملف الواحد...
set ONEFILE=1
python -m PyInstaller packaging\restaurant_erp.spec --noconfirm --distpath dist-single --workpath build\single
set ONEFILE=
if errorlevel 1 (
    echo [خطأ] فشل بناء الملف الواحد.
    pause
    exit /b 1
)
copy /y "packaging\اقرأني-قبل-التشغيل.txt" "dist-single\" >nul
copy /y "docs\دليل-الاستخدام.pdf" "dist-single\" >nul

echo [4/4] بناء نسخة المجلد...
python -m PyInstaller packaging\restaurant_erp.spec --noconfirm --distpath dist-folder --workpath build\folder
if errorlevel 1 (
    echo [خطأ] فشل بناء نسخة المجلد.
    pause
    exit /b 1
)
REM Sits next to the .exe where the customer will actually see it. Bundling it
REM as PyInstaller data would hide it inside _internal\.
copy /y "packaging\اقرأني-قبل-التشغيل.txt" "dist-folder\نظام-إدارة-المطعم\" >nul

echo.
echo ============================================
echo   تم البناء بنجاح
echo ============================================
echo.
echo 1) للارسال للعملاء - ملف واحد يدوس عليه ويشتغل:
echo        dist-single\نظام إدارة المطعم.exe
echo.
echo 2) نسخة احتياطية على شكل مجلد ^(اسرع في الفتح^):
echo        dist-folder\نظام-إدارة-المطعم\
echo    اضغطها: كليك يمين ^> Send to ^> Compressed (zipped) folder
echo.
pause
