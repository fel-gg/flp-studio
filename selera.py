"""Belajar dari selera pemilik: setiap kali hasil diekspor, pilihan gaya/warna/judul/bingkai/desain dicatat.
Ringkasannya dikirim ke Gemini (sutradara & Magic) dan dipakai mode offline, jadi edit berikutnya makin
mirip yang biasa dipilih, tanpa perlu disetel.

Catatan disimpan di selera.json (lokal, tidak dikirim ke mana pun selain ringkasan teks di prompt Gemini).
"""
import json
import time
from collections import Counter
from pathlib import Path

BERKAS = Path(__file__).resolve().parent / "selera.json"
MAKS = 300  # catatan terbaru yang disimpan


def _baca():
    try:
        return json.loads(BERKAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def catat(jenis, pilihan):
    """jenis: 'edit' (video/foto yang diekspor) atau 'desain'. pilihan: dict nilai yang dipakai."""
    data = _baca()
    data.append({"t": round(time.time()), "jenis": jenis,
                 **{k: v for k, v in pilihan.items() if isinstance(v, (str, int, float)) and v != ""}})
    BERKAS.write_text(json.dumps(data[-MAKS:], ensure_ascii=False), encoding="utf-8")


def hitung(jenis, kunci, terbaru=60, bobot=True):
    """Counter nilai `kunci` dari catatan terbaru jenis itu (yang baru lebih berbobot)."""
    c = Counter()
    data = [x for x in _baca() if x.get("jenis") == jenis][-terbaru:]
    for i, x in enumerate(data):
        if kunci in x:
            c[x[kunci]] += 1 + (i / max(len(data), 1) if bobot else 0)  # pilihan terakhir sedikit lebih berat
    return c


def favorit(jenis, kunci, minimal=2):
    """Nilai yang paling sering dipilih (minimal dipakai `minimal` kali), atau None."""
    c = hitung(jenis, kunci)
    if not c:
        return None
    nilai, skor = c.most_common(1)[0]
    return nilai if skor >= minimal else None


def ringkas():
    """Teks pendek untuk prompt Gemini; kosong kalau belum ada catatan."""
    bagian = []
    for kunci, nama in (("gaya", "gaya teks"), ("warna", "warna"), ("judul", "font judul"), ("bingkai", "bingkai"),
                        ("rasio", "rasio"), ("versi", "nomor versi")):
        c = hitung("edit", kunci, bobot=False)
        if c:
            atas = ", ".join(f"{k} ({v}x)" for k, v in c.most_common(3))
            bagian.append(f"- {nama}: {atas}")
    d = hitung("desain", "gaya", bobot=False)
    if d:
        bagian.append("- desain favorit: " + ", ".join(f"{k} ({v}x)" for k, v in d.most_common(3)))
    if not bagian:
        return ""
    return ("RIWAYAT PILIHAN PEMILIK (ekspor terakhir; paling sering di depan). Jadikan Versi 1 paling dekat dengan "
            "kebiasaan ini, tapi tetap sesuaikan dengan isi & cahaya video:\n" + "\n".join(bagian))
