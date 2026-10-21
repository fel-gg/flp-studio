"""Kirim proyek FLP Studio ke CapCut sebagai draft yang bisa langsung dibuka dan diedit lagi di CapCut
(potongan + zoom, judul pembuka, subtitle, teks, musik). Pakai mesin draft pyJianYingDraft dari capcut-mate
(vendor/pyJianYingDraft, lisensi Apache-2.0). Warna, pembersih suara, dan stabilisasi tidak ikut karena itu
dikerjakan saat export di FLP Studio; di CapCut kamu bisa memakai efek CapCut sendiri.

    python capcut.py proyek/xxx.proyek.json
"""
import json
import os
import sys
import time
from pathlib import Path

import autoedit as ae

sys.path.insert(0, str(Path(__file__).parent / "vendor"))
import pyJianYingDraft as draft  # noqa: E402
from pyJianYingDraft import SEC, trange  # noqa: E402

FOLDER_DRAFT = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def versi_capcut(folder, kecuali):
    """Draft harus mengaku dibuat oleh CapCut yang terpasang (bukan Jianying, bukan versi lebih baru), kalau tidak
    CapCut menolak membukanya. Ambil dari draft buatan CapCut sendiri yang paling baru."""
    cadangan = {"platform": {"app_id": 359289, "app_source": "cc", "app_version": "3.9.0", "os": "windows"},
                "version": 360000, "new_version": "110.0.0"}
    for d in sorted((x for x in folder.iterdir() if x.is_dir() and x.name != kecuali),
                    key=lambda x: (x / "draft_content.json").stat().st_mtime if (x / "draft_content.json").exists() else 0,
                    reverse=True):
        try:
            j = json.loads((d / "draft_content.json").read_text(encoding="utf-8"))
            if (j.get("platform") or {}).get("app_source") == "cc":
                return {"platform": j["platform"], "version": j["version"], "new_version": j["new_version"]}
        except (OSError, ValueError, KeyError):
            continue
    return cadangan


def warna_ass(ass, cadangan=(1.0, 0.95, 0.9)):
    """Warna ASS &HAABBGGRR -> RGB 0..1 untuk CapCut."""
    try:
        h = ass[-6:]
        return tuple(int(h[i:i + 2], 16) / 255 for i in (4, 2, 0))
    except (TypeError, ValueError):
        return cadangan


def teks(isi, a, b, y, ukuran, gaya_, tebal=False, miring=False):
    """Satu teks di CapCut. y: -1 (bawah) .. 1 (atas)."""
    g = ae.GAYA.get(gaya_, {})
    return draft.TextSegment(
        isi, trange(f"{a:.3f}s", f"{b - a:.3f}s"),
        style=draft.TextStyle(size=ukuran, bold=tebal, italic=miring, color=warna_ass(g.get("warna")), align=1,
                              auto_wrapping=True, max_line_width=0.82),
        border=draft.TextBorder(color=(0.28, 0.19, 0.13), width=30),
        clip_settings=draft.ClipSettings(transform_y=y))


def kirim(p, nama=None, folder=FOLDER_DRAFT, log=print):
    nama = nama or f"FLP {Path(p['sumber'][0]).stem} {time.strftime('%H%M%S')}"
    try:
        return _kirim(p, nama, folder, log)
    except Exception:
        import shutil  # draft setengah jadi akan ditolak CapCut: jangan ditinggalkan
        shutil.rmtree(folder / nama, ignore_errors=True)
        raise


def _kirim(p, nama, folder, log):
    if not folder.exists():
        raise RuntimeError("Folder draft CapCut tidak ditemukan. Buka CapCut sekali dulu.")
    video = ae.siapkan_video([Path(x).resolve() for x in p["sumber"]])
    sw, sh, durasi = ae.info_video(video)
    w, h = ae.ukuran_keluar(sw, sh, p.get("rasio", "asli"))
    audio = Path(p["audio"]).resolve() if p.get("audio") else None
    cache = video.with_name(video.stem + (f".{audio.stem}" if audio else "") + ".kata.json")
    kata = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else []
    pot = [x for x in p.get("potongan") or [] if min(durasi, x["selesai"]) - max(0.0, x["mulai"]) > 0.05]
    bagian = ([(max(0.0, x["mulai"]), min(durasi, x["selesai"]), float(x.get("zoom", 1))) for x in pot] or
              [(a, b, 1.0) for a, b in (ae.bagian_dipakai(kata, durasi) if kata else [(0.0, durasi)])])
    kec = [min(4.0, max(0.25, float(x.get("kecepatan", 1.0)))) for x in pot] or [1.0] * len(bagian)

    log(f"Membuat draft CapCut '{nama}'...")
    s = draft.DraftFolder(str(folder)).create_draft(nama, w, h, 30)
    s.add_track(draft.TrackType.video).add_track(draft.TrackType.text, "teks").add_track(draft.TrackType.audio, "musik")

    # CapCut menaruh video "pas di dalam" kanvas; skala ini membuatnya memenuhi kanvas seperti di FLP Studio
    isi = 1.0 if p.get("bingkai") == "letterbox" else max((w / h) / (sw / sh), (sw / sh) / (w / h))
    cw, ch = (w, w * sh / sw) if sw / sh > w / h else (h * sw / sh, h)  # ukuran video "pas di dalam" kanvas
    # bentuk berubah (16:9 -> 9:16): geser gambar supaya wajah tetap di tengah, tanpa tepi hitam
    wajah = (ae.posisi_wajah(video, [(a, b) for a, b, _ in bagian], sw, sh) if isi > 1.15
             else [(0.5, 0.5)] * len(bagian))
    bahan = draft.VideoMaterial(str(video))
    t = 0
    for (a, b, z), (fx, fy), c in zip(bagian, wajah, kec):
        k = isi * z
        bx, by = max(0.0, (cw * k - w) / 2), max(0.0, (ch * k - h) / 2)
        gx = max(-bx, min(bx, (0.5 - fx) * cw * k)) / (w / 2)
        gy = max(-by, min(by, (fy - 0.5) * ch * k)) / (h / 2)  # y CapCut: positif = ke atas
        # waktu dalam mikrodetik (bilangan bulat) seperti di draft: pembulatan detik membuat potongan bertumpuk
        sumber = draft.Timerange(round(a * SEC), round((b - a) * SEC))
        s.add_segment(draft.VideoSegment(bahan, draft.Timerange(t, round(sumber.duration / c)),
                                         source_timerange=sumber, speed=c,
                                         volume=float(p.get("volume_suara", 1.0)),
                                         clip_settings=draft.ClipSettings(scale_x=k, scale_y=k,
                                                                          transform_x=gx, transform_y=gy)))
        t += round(sumber.duration / c)
    total = t / SEC

    gaya_ = p.get("gaya", "hangat-kotak")
    if p.get("hook"):
        s.add_segment(teks(p["hook"].replace("|", "\n"), 0, min(total, p.get("durasi_hook", 3.0)), 0.55, 11, gaya_,
                           miring=True), "teks")
    if p.get("subtitle", True) and kata:
        k = [x for x in ae.geser_waktu(kata, [(a, b) for a, b, _ in bagian], kec) if not ae.PENGISI.match(x["w"].strip())]
        akhir = 0.0
        for kel in ae.potong_kalimat(k, ae.GAYA.get(gaya_, {}).get("maks_kata", 5)):
            a = max(kel[0]["s"], akhir, p.get("durasi_hook", 3.0) if p.get("hook") else 0.0)
            b = min(total, kel[-1]["e"] + 0.15)
            if b - a < 0.25:
                continue
            s.add_segment(teks(" ".join(x["w"].strip() for x in kel), a, b, -0.45, 7, gaya_, tebal=True), "teks")
            akhir = b + 0.001
    for e in p.get("elemen") or []:
        if (e.get("teks") or "").strip() and e["mulai"] < total:
            y = {"judul": 0.55, "label": 0.75, "tanggal": 0.75, "daftar": 0.6}.get(e["jenis"], 0.0)
            # elemen bisa bertumpuk dengan subtitle: tiap elemen di lajur teks sendiri
            jalur = f"elemen{len(s.tracks)}"
            s.add_track(draft.TrackType.text, jalur)
            s.add_segment(teks(e["teks"].replace("|", "\n"), e["mulai"], min(total, e["selesai"]), y, 9, gaya_), jalur)

    lagu = p.get("musik")
    if lagu == "auto":
        import musik
        lagu = musik.pilih("tenang" if len(kata) > 10 else "ceria")
    if lagu:  # musik diulang sampai video habis, pelan di bawah suara (CapCut tidak punya ducking otomatis)
        m = draft.AudioMaterial(str(Path(lagu).resolve()))
        panjang, t = m.duration / SEC, 0.0
        while t < total - 0.05:
            d = min(panjang, total - t)
            s.add_segment(draft.AudioSegment(m, trange(f"{t:.3f}s", f"{d:.3f}s"), source_timerange=trange("0s", f"{d:.3f}s"),
                                             volume=(0.12 if len(kata) > 10 else 0.6) * float(p.get("volume_musik", 1.0))), "musik")
            t += d
    s.save()
    v = versi_capcut(folder, nama)
    for f in ("draft_content.json", "draft_info.json"):
        berkas = folder / nama / f
        if berkas.exists():
            j = json.loads(berkas.read_text(encoding="utf-8"))
            j.update(version=v["version"], new_version=v["new_version"], platform=v["platform"],
                     last_modified_platform=v["platform"])
            berkas.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    log(f"Draft siap di CapCut: {nama}")
    return nama


if __name__ == "__main__":
    pr = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(kirim(pr))
