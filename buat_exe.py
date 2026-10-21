"""Buat aplikasi sendiri: ikon + FLPStudio.exe (peluncur kecil, tanpa jendela hitam).
Ganti NAMA di bawah kalau mau nama lain, lalu jalankan:  python buat_exe.py

    python buat_exe.py                 # versi biasa: kunci API Gemini diminta di aplikasi (Setelan)
    python buat_exe.py --dengan-kunci  # versi PRIBADI: kunci API dari .env komputer ini ditanam di exe.
                                       # Jangan bagikan exe ini: kuncinya bisa dibaca dari file exe.
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

NAMA = "FLP Studio"
HERE = Path(__file__).resolve().parent
EXE = HERE / (NAMA.replace(" ", "") + ".exe")
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


def ikon(path, n=512):
    """Kotak membulat gradasi hangat (kuning madu -> terakota) dengan tombol play krem."""
    img = Image.new("RGBA", (n, n))
    atas, bawah = (242, 190, 92), (196, 92, 62)
    grad = Image.new("RGBA", (n, n))
    d = ImageDraw.Draw(grad)
    for y in range(n):
        t = y / (n - 1)
        d.line([(0, y), (n, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(atas, bawah)) + (255,))
    topeng = Image.new("L", (n, n))
    ImageDraw.Draw(topeng).rounded_rectangle([0, 0, n - 1, n - 1], radius=n * 0.23, fill=255)
    img.paste(grad, (0, 0), topeng)
    d = ImageDraw.Draw(img)
    c, r = n * 0.53, n * 0.24  # segitiga play, sedikit ke kanan supaya terlihat di tengah
    d.polygon([(c - r * 0.8, n / 2 - r), (c - r * 0.8, n / 2 + r), (c + r * 0.95, n / 2)], fill=(255, 242, 230, 255))
    s, x, y = n * 0.07, n * 0.75, n * 0.24  # kilau kecil
    d.polygon([(x, y - s), (x + s * 0.28, y - s * 0.28), (x + s, y), (x + s * 0.28, y + s * 0.28),
               (x, y + s), (x - s * 0.28, y + s * 0.28), (x - s, y), (x - s * 0.28, y - s * 0.28)],
              fill=(255, 250, 240, 255))
    img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


PELUNCUR = r'''
using System; using System.Diagnostics; using System.IO; using System.Windows.Forms;
[assembly: System.Reflection.AssemblyTitle("%NAMA%")]
[assembly: System.Reflection.AssemblyProduct("%NAMA%")]
class P {
  [STAThread] static void Main() {
    string dir = AppDomain.CurrentDomain.BaseDirectory;
    string py = "pythonw.exe";
    foreach (string d in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';')) {
      try { if (File.Exists(Path.Combine(d, "pythonw.exe"))) { py = Path.Combine(d, "pythonw.exe"); break; } } catch {}
    }
    if (py == "pythonw.exe" && File.Exists(@"%PYW%")) py = @"%PYW%";
    try {
      var si = new ProcessStartInfo(py, "\"" + Path.Combine(dir, "ui.py") + "\"");
      si.WorkingDirectory = dir; si.UseShellExecute = false; si.CreateNoWindow = true;
      if ("%KUNCI%".Length > 0) si.EnvironmentVariables["GEMINI_API_KEY"] = "%KUNCI%";
      Process.Start(si);
    } catch (Exception e) {
      MessageBox.Show("Python tidak ditemukan. Pasang Python 3.12 lalu coba lagi.\n\n" + e.Message, "%NAMA%");
    }
  }
}'''

if __name__ == "__main__":
    import shutil
    ico = HERE / "ikon.ico"
    ikon(ico)
    pyw = shutil.which("pythonw") or ""
    src = HERE / "_peluncur.cs"
    kunci = ""
    if "--dengan-kunci" in sys.argv:
        import magic
        try:
            kunci = magic.kunci_api()
        except SystemExit:
            kunci = ""
        if not kunci:
            sys.exit("Kunci API belum ada. Isi dulu di aplikasi (Setelan) atau di .env, lalu ulangi.")
    src.write_text(PELUNCUR.replace("%NAMA%", NAMA).replace("%PYW%", pyw).replace("%KUNCI%", kunci.replace('"', "")),
                   encoding="utf-8")
    try:
        subprocess.run([str(CSC), "/nologo", "/target:winexe", f"/win32icon:{ico}", f"/out:{EXE}",
                        "/r:System.Windows.Forms.dll", str(src)], check=True)
    finally:
        src.unlink(missing_ok=True)
    print(EXE)
