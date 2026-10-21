@echo off
rem Seret (drag) satu atau beberapa video ke file ini. Hasil muncul di sebelah video aslinya.
rem Taruh file bernama musik.mp3 di folder ini kalau mau musik latar otomatis.
rem Setiap menu menunggu sampai kamu menekan angka, tidak ada yang terpilih otomatis.
if "%~1"=="" (
  echo Seret video ke file edit.bat ini.
  pause
  exit /b
)

echo.
echo === GAYA TEKS ===
echo   1 = hangat-kotak    (teks di atas kotak gelap, paling mudah dibaca)
echo   2 = hangat-kuning   (seluruh teks kuning hangat)
echo   3 = hangat-serif    (serif miring seperti judul majalah)
echo   4 = hangat          (teks krem tanpa kotak)
echo   5 = SEMUA versi hangat (buat dibandingkan)
echo   6 = sinematik       (teks tipis putih di samping wajah)
echo   7 = minimal         (subtitle kecil monospace di bawah)
echo   8 = bold            (HURUF KAPITAL, kata yang diucapkan disorot ungu)
echo   9 = pop             (1-2 kata besar hijau mint di tengah)
choice /c 123456789 /n /m "Tekan angka: "
set G=hangat-kotak
if errorlevel 2 set G=hangat-kuning
if errorlevel 3 set G=hangat-serif
if errorlevel 4 set G=hangat
if errorlevel 5 set G=versi-hangat
if errorlevel 6 set G=sinematik
if errorlevel 7 set G=minimal
if errorlevel 8 set G=bold
if errorlevel 9 set G=pop
echo   -^> %G%

echo.
echo === WARNA ===
echo   1 = hangat      (warm aesthetic halus)
echo   2 = natural     (hampir seperti aslinya)
echo   3 = golden      (sore keemasan)
echo   4 = film        (film pudar, kalem)
echo   5 = sinematik   (teal ^& orange)
echo   6 = terang      (bright ^& airy)
echo   7 = moody       (gelap dan dingin)
echo   8 = kaya        (film kaya warna, kontras dalam, ala CineRaw)
echo   9 = pastel      (cerah lembut, ala "The beauty of Color Grading")
echo  10 = arsip       (digital unfiltered, ala "visual archives")
echo  11 = vhs         (camcorder 80-an, lembut pink, ala "Footage from 86")
echo  12 = asli        (tanpa color grading)
echo  13 = SEMUA warna (buat dibandingkan)
:pilih_warna
set W=
set NW=
set /p NW=Ketik nomor lalu Enter: 
if "%NW%"=="1" set W=hangat
if "%NW%"=="2" set W=natural
if "%NW%"=="3" set W=golden
if "%NW%"=="4" set W=film
if "%NW%"=="5" set W=sinematik
if "%NW%"=="6" set W=terang
if "%NW%"=="7" set W=moody
if "%NW%"=="8" set W=kaya
if "%NW%"=="9" set W=pastel
if "%NW%"=="10" set W=arsip
if "%NW%"=="11" set W=vhs
if "%NW%"=="12" set W=asli
if "%NW%"=="13" set W=semua
if not defined W goto pilih_warna
echo   -^> %W%

echo.
echo === BENTUK VIDEO ===
echo   1 = asli (vertikal tetap vertikal, horizontal tetap horizontal)
echo   2 = vertikal 9:16 untuk Reels
choice /c 12 /n /m "Tekan angka: "
set R=asli
if errorlevel 2 set R=9:16
echo   -^> %R%

echo.
echo === HOOK ===
set HOOK=
set /p HOOK=Ketik hook lalu Enter (Enter saja = ambil acak dari hooks.txt, ketik - = tanpa hook):
if "%HOOK%"=="" set HOOK=auto
if "%HOOK%"=="-" set HOOK=
set MUSIK=
if exist "%~dp0musik.mp3" set MUSIK=--musik "%~dp0musik.mp3"

:loop
if "%~1"=="" goto done
echo.
echo === %~nx1
python "%~dp0autoedit.py" "%~1" --gaya %G% --warna %W% --rasio %R% --hook "%HOOK%" %MUSIK%
shift
goto loop
:done
echo.
echo Selesai.
pause
