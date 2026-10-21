"""UI sederhana untuk editor otomatis. Jalankan:  python ui.py   (atau klik dua kali UI.bat)
Membuka http://127.0.0.1:8765 di browser. Semua berjalan di komputer ini; hanya tombol Magic yang
mengirim 8 frame kecil + transkrip ke Gemini.
"""
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import autoedit as ae
import selera

HERE = Path(__file__).resolve().parent
PROYEK = HERE / "proyek"  # semua file yang diunggah dan hasil render ada di sini
PROYEK.mkdir(exist_ok=True)
PORT = 8765
OTOMATIS = {}  # path video -> hasil ukur koreksi otomatis (diukur sekali per file)
TUGAS = {}  # id -> {"log": [...], "selesai": bool, "hasil": ..., "galat": ...}


def jalan_tugas(fungsi):
    """Jalankan pekerjaan lama (transkrip, Gemini, render) di belakang; UI menanyakan statusnya."""
    tid = uuid.uuid4().hex[:8]
    TUGAS[tid] = {"log": [], "selesai": False, "hasil": None, "galat": None}

    def kerja():
        global DETAK
        try:
            TUGAS[tid]["hasil"] = fungsi(TUGAS[tid]["log"])
        except BaseException as e:  # sys.exit dari autoedit juga ditangkap
            TUGAS[tid]["galat"] = str(e) or e.__class__.__name__
        DETAK = time.time()  # jendela yang tersembunyi mengirim ping jarang; beri waktu mengambil hasil
        TUGAS[tid]["selesai"] = True

    threading.Thread(target=kerja, daemon=True).start()
    return tid


def path_aman(p):
    """Hanya file di dalam folder proyek yang boleh dibaca/dipakai lewat UI."""
    q = (PROYEK / Path(p).name).resolve()
    if q.parent != PROYEK.resolve() or not q.exists():
        raise ValueError(f"file tidak ditemukan: {p}")
    return q


def ukur_otomatis(video):
    kunci = (str(video), video.stat().st_mtime)  # file diunggah ulang -> ukur ulang
    if kunci not in OTOMATIS:
        OTOMATIS[kunci] = ae.atur_otomatis(video)
    return OTOMATIS[kunci]


def atur_template(auto, tambah):
    """Koreksi otomatis + sentuhan template, dijaga tetap di rentang slider."""
    return {k: max(0 if k in ("vignette", "glow", "tajam", "grain") else -100,
                   min(100, auto.get(k, 0) + tambah.get(k, 0))) for k in ae.ATUR}


def argumen(o, video):
    """Opsi dari UI -> argumen command line autoedit.py."""
    arg = [str(video), "--gaya", o["gaya"], "--rasio", o.get("rasio", "asli"),
           "--atur", json.dumps(o.get("atur", {}))]
    if o.get("warna"):
        arg += ["--warna", o["warna"]]
    if o.get("judul"):
        arg += ["--judul", o["judul"]]
    if o.get("hook"):
        arg += [f"--hook={o['hook']}"]  # bentuk "=" supaya hook yang diawali "-" tidak dikira opsi
    if o.get("audio"):
        arg += ["--audio", str(path_aman(o["audio"]))]
    if o.get("musik"):
        arg += ["--musik", "auto" if o["musik"] == "auto" else str(path_aman(o["musik"]))]
    if o.get("tanpa_potong"):
        arg += ["--tanpa-potong"]
    return arg


def jalankan_autoedit(arg, log):
    p = subprocess.Popen([sys.executable, str(HERE / "autoedit.py"), *arg], cwd=HERE, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         creationflags=ae.TANPA_JENDELA,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})  # hook beremoji tidak boleh bikin print gagal
    for baris in p.stdout:
        log.append(baris.rstrip())
    if p.wait() != 0:
        raise RuntimeError("\n".join(log[-8:]))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def kirim(self, data, tipe="application/json", kode=200):
        if not isinstance(data, (bytes, bytearray)):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(kode)
        self.send_header("Content-Type", tipe)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/":
                self.kirim((HERE / "ui.html").read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/editor":  # Full Edit (timeline ala CapCut)
                self.kirim((HERE / "editor.html").read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/strip":
                # deretan thumbnail kecil sepanjang video untuk timeline: satu JPG berisi n gambar berjajar
                video = path_aman(unquote(q["video"][0]))
                n = max(4, min(120, int(q.get("n", ["40"])[0])))
                tinggi = int(q.get("tinggi", ["72"])[0])
                keluar = PROYEK / f"_strip_{video.stem}_{n}_{tinggi}.jpg"
                if not keluar.exists() or keluar.stat().st_mtime < video.stat().st_mtime:
                    _, _, d = ae.info_video(video)
                    ae.jalankan(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf",
                                 f"fps={n / max(d, 0.1):.5f},scale=-2:{tinggi},tile={n}x1", "-frames:v", "1",
                                 "-update", "1", "-q:v", "5", str(keluar)])
                self.kirim({"p": keluar.name, "n": n})
            elif u.path == "/ikon.ico":
                self.kirim((HERE / "ikon.ico").read_bytes(), "image/x-icon")
            elif u.path == "/ping":  # jendela aplikasi masih terbuka
                global DETAK
                DETAK = time.time()
                self.kirim({"ok": True})
            elif u.path == "/info":
                self.kirim({"gaya": ae.INFO_GAYA, "warna": ae.INFO_WARNA, "judul": ae.INFO_JUDUL,
                            "atur": ae.ATUR, "rasio": list(ae.RASIO), "template": ae.TEMPLATE,
                            "efek": ae.NAMA_EFEK, "transisi": ae.NAMA_TRANSISI})
            elif u.path == "/desain_info":  # desain koleksi + isian yang bisa diedit (UI membuat form otomatis)
                import desain
                import koleksi
                self.kirim([{"gaya": g, "nama": koleksi.NAMA_LAIN[g], "rasio": desain.RASIO_BAWAAN[g],
                             "isian": [{"kunci": k, "label": lb, "contoh": c, "jenis": j}
                                       for k, lb, c, j in koleksi.ISIAN_LAIN[g]]} for g in koleksi.GAYA_LAIN])
            elif u.path == "/koran_isi":  # isi bawaan potongan koran samping, untuk diisi ke form
                import desain
                self.kirim({"potongan": desain.isi_koran_bawaan()})
            elif u.path == "/setelan":  # kunci API tidak pernah dikirim balik ke halaman
                import magic
                self.kirim({"online": magic.boleh_online(), "ada_kunci": magic.ada_kunci()})
            elif u.path == "/status":
                t = TUGAS[q["id"][0]]
                self.kirim({**t, "log": t["log"][-30:]})
            elif u.path == "/file":
                f = path_aman(unquote(q["p"][0]))
                tipe = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                rentang = self.headers.get("Range", "")
                if rentang.startswith("bytes="):  # supaya video hasil bisa digeser (seek) di pemutar
                    ukuran = f.stat().st_size
                    awal, _, akhir = rentang[6:].partition("-")
                    awal = int(awal or 0)
                    akhir = min(int(akhir) if akhir else ukuran - 1, ukuran - 1)
                    with open(f, "rb") as fp:
                        fp.seek(awal)
                        data = fp.read(akhir - awal + 1)
                    self.send_response(206)
                    self.send_header("Content-Type", tipe)
                    self.send_header("Content-Range", f"bytes {awal}-{akhir}/{ukuran}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.kirim(f.read_bytes(), tipe)
            elif u.path == "/buka":  # tampilkan hasil di File Explorer
                f = path_aman(unquote(q["p"][0]))
                subprocess.Popen(["explorer", "/select,", str(f)])
                self.kirim({"ok": True})
            else:
                self.kirim({"galat": "tidak ada"}, kode=404)
        except Exception as e:
            self.kirim({"galat": str(e)}, kode=400)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/unggah":
                nama = Path(unquote(q["nama"][0])).name
                tujuan = PROYEK / nama
                sisa = int(self.headers["Content-Length"])
                with open(tujuan, "wb") as f:
                    while sisa > 0:
                        potong = self.rfile.read(min(sisa, 1 << 20))
                        if not potong:
                            break
                        f.write(potong)
                        sisa -= len(potong)
                # file baru dengan nama sama: transkrip & suara sinkron lama sudah tidak berlaku
                stem = tujuan.stem
                for lama in [*PROYEK.glob(f"{stem}.*kata.json"), *PROYEK.glob(f"*.{stem}.kata.json"),
                             *PROYEK.glob(f"{stem}.*sinkron.wav"), *PROYEK.glob(f"*.{stem}.sinkron.wav")]:
                    lama.unlink(missing_ok=True)
                info = {}
                if q.get("jenis", [""])[0] == "video":
                    w, h, d = ae.info_video(tujuan)
                    info = {"w": w, "h": h, "durasi": d}
                self.kirim({"p": nama, **info})

            elif u.path == "/gabung":
                nama = self.body_json()["videos"]
                klip = [path_aman(n) for n in nama]
                if len(klip) == 1:  # satu klip: tidak perlu digabung
                    w, h, d = ae.info_video(klip[0])
                    self.kirim({"id": jalan_tugas(lambda log: {"p": klip[0].name, "w": w, "h": h, "durasi": d})})
                    return
                # nama gabungan tergantung urutan & waktu ubah klip: urutan atau file berganti -> gabung ulang
                sidik = "|".join(f"{k.name}:{k.stat().st_mtime_ns}" for k in klip)
                keluar = PROYEK / f"gabungan_{hashlib.md5(sidik.encode()).hexdigest()[:8]}.mp4"

                def kerja(log):
                    if not keluar.exists():
                        log.append(f"Menggabungkan {len(klip)} klip…")
                        sementara = keluar.with_name(f"_{keluar.name}")  # gagal di tengah jalan tidak meninggalkan file separuh
                        try:
                            ae.gabung(klip, sementara)
                            os.replace(sementara, keluar)
                        finally:
                            sementara.unlink(missing_ok=True)
                    w, h, d = ae.info_video(keluar)
                    return {"p": keluar.name, "w": w, "h": h, "durasi": d}

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/magic":
                o = self.body_json()

                def kerja(log):
                    import magic
                    video = path_aman(o["video"])
                    audio = path_aman(o["audio"]) if o.get("audio") else None
                    if ae.foto(video):  # foto: tanpa suara, langsung ke Gemini
                        log.append("Gemini sedang melihat fotomu...")
                        return magic.rekomendasi(video, [])
                    _, _, durasi = ae.info_video(video)
                    sumber = video
                    if audio:
                        log.append("Menyinkronkan suara rekaman terpisah...")
                        sumber = video.with_name(f"{video.stem}.{audio.stem}.sinkron.wav")
                        geser, yakin = ae.siapkan_suara(video, audio, sumber, durasi)
                        log.append(f"Suara digeser {geser:+.2f} detik" if yakin else
                                   "Video tanpa suara bawaan, suara dianggap mulai bersamaan")
                    log.append("Mentranskrip suara (Whisper)...")
                    cache = video.with_name(video.stem + (f".{audio.stem}" if audio else "") + ".kata.json")
                    kata = ae.transkrip(sumber, None, cache)
                    log.append(f"{len(kata)} kata. Gemini sedang melihat videomu...")
                    return magic.rekomendasi(video, kata)

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/sutradara":
                # Edit Otomatis: Gemini menonton seluruh video lalu menulis rencana edit + 3 versi
                o = self.body_json()

                def kerja(log):
                    import sutradara
                    video = path_aman(o["video"])
                    audio = path_aman(o["audio"]) if o.get("audio") else None
                    r = sutradara.buat_rencana(video, audio, o.get("rasio", "9:16"), log.append)
                    video.with_name(video.stem + ".rencana.json").write_text(
                        json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
                    return r

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/edit_pro":
                # Edit Pro sekali jalan: video mentah -> proyek siap export (Gemini kalau ada, kalau tidak offline)
                o = self.body_json()

                def kerja(log):
                    import pro
                    return pro.edit_pro(path_aman(o["video"]), path_aman(o["audio"]) if o.get("audio") else None,
                                        o.get("rasio", "asli"), log.append)

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/capcut":
                # proyek -> draft CapCut (potongan, teks, subtitle, musik) supaya bisa dilanjutkan di CapCut
                p = self.body_json()["proyek"]
                p["sumber"] = [str(path_aman(x)) for x in p["sumber"]]
                for k in ("audio", "musik"):
                    p[k] = (p[k] if p.get(k) == "auto" else str(path_aman(p[k]))) if p.get(k) else None

                def kerja(log):
                    import capcut
                    return {"nama": capcut.kirim(p, log=log.append)}

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/transkrip":
                # kata + waktu (detik sumber) untuk timeline Full Edit; disimpan di cache seperti biasa
                o = self.body_json()

                def kerja(log):
                    video = path_aman(o["video"])
                    audio = path_aman(o["audio"]) if o.get("audio") else None
                    sumber = video
                    if audio:
                        sumber = video.with_name(f"{video.stem}.{audio.stem}.sinkron.wav")
                        if not sumber.exists():
                            log.append("Menyinkronkan suara rekaman terpisah...")
                            ae.siapkan_suara(video, audio, sumber, ae.info_video(video)[2])
                    log.append("Mentranskrip suara...")
                    cache = video.with_name(video.stem + (f".{audio.stem}" if audio else "") + ".kata.json")
                    kata = ae.transkrip(sumber, None, cache)
                    return {"kata": kata, "hening": ae.bagian_dipakai(kata, ae.info_video(video)[2])}

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/simpan_proyek":
                # simpan proyek kerja (dari Mode Mudah atau Full Edit) supaya bisa dibuka lagi; nama tetap per video
                o = self.body_json()
                p = o["proyek"]
                nama = Path(o.get("nama") or f"{Path(p['sumber'][0]).stem}.kerja.proyek.json").name
                if not nama.endswith(".proyek.json"):
                    raise ValueError("nama proyek harus berakhiran .proyek.json")
                (PROYEK / nama).write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
                self.kirim({"p": nama})

            elif u.path == "/poster":
                # Poster film: foto -> JPG, video -> cuplikan MP4. pratinjau=true -> satu gambar cepat.
                o = self.body_json()
                import poster
                media = path_aman(o["media"])
                cepat = bool(o.get("pratinjau"))
                if cepat:
                    for lama in PROYEK.glob("_poster_*.jpg"):
                        lama.unlink(missing_ok=True)
                    keluar = PROYEK / f"_poster_{uuid.uuid4().hex[:6]}.jpg"
                else:
                    ext = ".jpg" if ae.foto(media) else ".mp4"
                    keluar = PROYEK / f"{media.stem}_POSTER_{time.strftime('%H%M%S')}{ext}"
                arg = (media, keluar, o.get("data", {}), o.get("rasio", "2:3"), float(o.get("mulai", 0)),
                       float(o["durasi"]) if o.get("durasi") else None, o.get("tema", "kertas"),
                       o.get("warna") or "serasi", o.get("atur") or {}, o.get("crop") or None, cepat)
                if cepat:  # langsung (±1 s) supaya preview terasa hidup
                    poster.buat_poster(*arg)
                    self.kirim({"p": keluar.name})
                else:
                    self.kirim({"id": jalan_tugas(lambda log: (log.append("Membuat poster..."),
                                                              poster.buat_poster(*arg), {"p": keluar.name})[2])})

            elif u.path == "/desain":
                # Koran/Tiket/Polaroid/Majalah (1 media) atau Carousel (banyak media). pratinjau=true -> 1 JPG cepat
                o = self.body_json()
                import desain
                gaya = o.get("gaya", "koran")
                daftar = [path_aman(x) for x in (o.get("media") if isinstance(o.get("media"), list) else [o["media"]])]
                data = o.get("data", {})
                cepat = bool(o.get("pratinjau"))
                if gaya == "carousel":
                    nama = f"{daftar[0].stem}_CAROUSEL_{time.strftime('%H%M%S')}"  # _01.jpg, _02.mp4, ...

                    def kerja(log):
                        f = desain.buat_carousel(daftar, PROYEK, data, o.get("warna") or "serasi", nama,
                                                 log=log.append)
                        return {"p": [x.name for x in f]}

                    self.kirim({"id": jalan_tugas(kerja)})
                else:
                    media = daftar[0]
                    if cepat:
                        for lama in PROYEK.glob("_desain_*.jpg"):
                            lama.unlink(missing_ok=True)
                        keluar = PROYEK / f"_desain_{uuid.uuid4().hex[:6]}.jpg"
                    else:
                        ext = ".jpg" if ae.foto(media) else ".mp4"
                        keluar = PROYEK / f"{media.stem}_{gaya.upper()}_{time.strftime('%H%M%S')}{ext}"
                    arg = (media, keluar, data, gaya, o.get("rasio") or None, float(o.get("mulai", 0)),
                           float(o["durasi"]) if o.get("durasi") else None, o.get("warna") or "serasi",
                           o.get("atur") or None, o.get("crop") or None, cepat)
                    if cepat:
                        desain.buat_desain(*arg)
                        self.kirim({"p": keluar.name})
                    else:
                        self.kirim({"id": jalan_tugas(lambda log: (log.append("Membuat desain..."),
                                                                  desain.buat_desain(*arg),
                                                                  selera.catat("desain", {"gaya": gaya}),
                                                                  {"p": keluar.name})[3])})

            elif u.path == "/caption":
                # caption + hashtag untuk IG/TikTok/YouTube/X/LinkedIn + cover terbaik dari video hasil
                o = self.body_json()
                video = path_aman(o["video"])

                def kerja(log):
                    import caption
                    kata = []
                    if not ae.foto(video) and ae.punya_audio(video):
                        log.append("Mendengarkan isi video...")
                        kata = ae.transkrip(video, None, video.with_name(video.stem + ".kata.json"))
                    log.append("Menulis caption untuk tiap platform...")
                    h = caption.proses(video, kata, o.get("catatan", ""))
                    return {"siap": h["siap"], "cover": h["cover"], "model": h.get("model")}

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/montage":
                # banyak foto/video -> satu reel dipotong mengikuti ketukan musik
                o = self.body_json()
                media = [path_aman(x) for x in o["media"]]
                keluar = PROYEK / f"MONTAGE_{time.strftime('%H%M%S')}.mp4"

                def kerja(log):
                    import montage
                    montage.buat_montage(media, keluar, o.get("judul", ""), o.get("warna") or "matte",
                                         o.get("rasio") or "9:16", log=log.append)
                    selera.catat("desain", {"gaya": "montage"})
                    return {"p": keluar.name}

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/batch":
                # banyak video sekaligus: tiap video ditranskrip, Magic memilih tampilan, dirender, diberi caption
                o = self.body_json()
                daftar = [path_aman(x) for x in o["media"]]

                def kerja(log):
                    import caption
                    import magic
                    hasil = []
                    for i, video in enumerate(daftar):
                        awal = f"[{i + 1}/{len(daftar)}] {video.name}:"
                        try:
                            kata = []
                            if not ae.foto(video):
                                log.append(f"{awal} mentranskrip...")
                                kata = ae.transkrip(video, None, video.with_name(video.stem + ".kata.json"))
                            log.append(f"{awal} memilih tampilan...")
                            r = magic.rekomendasi(video, kata)
                            ext = ".jpg" if ae.foto(video) else ".mp4"
                            keluar = PROYEK / f"{video.stem}_EDIT_{time.strftime('%H%M%S')}{ext}"
                            opsi = {"gaya": r["gaya"], "warna": r["warna"], "judul": r["judul"], "hook": r["hook"],
                                    "atur": r["atur"], "rasio": o.get("rasio") or "9:16"}
                            log.append(f"{awal} merender ({r['model']})...")
                            jalankan_autoedit(argumen(opsi, video) + ["--keluar", str(keluar)], log)
                            item = {"sumber": video.name, "p": keluar.name}
                            if o.get("caption", True) and not ae.foto(video):
                                log.append(f"{awal} menulis caption...")
                                c = caption.proses(keluar, kata, "")
                                item.update(caption=c["siap"], cover=c["cover"])
                            hasil.append(item)
                        except Exception as e:  # satu video gagal tidak menghentikan yang lain
                            log.append(f"{awal} GAGAL: {e}")
                            hasil.append({"sumber": video.name, "galat": str(e)})
                    return {"hasil": hasil}

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/koran_isi":
                # isi bawaan potongan koran (fun fact kamu); disimpan supaya dipakai lagi di desain berikutnya
                import desain
                o = self.body_json()
                lama = json.loads(desain.ISI_KORAN.read_text(encoding="utf-8-sig"))
                lama["potongan"] = o["potongan"][:4]
                desain.ISI_KORAN.write_text(json.dumps(lama, ensure_ascii=False, indent=1), encoding="utf-8")
                self.kirim({"ok": True})

            elif u.path == "/render_proyek":
                # proyek = rencana dasar + versi pilihan + elemen yang sudah diedit di UI
                p = self.body_json()["proyek"]
                p["sumber"] = [str(path_aman(x)) for x in p["sumber"]]
                for k in ("audio", "musik"):
                    p[k] = (p[k] if p.get(k) == "auto" else str(path_aman(p[k]))) if p.get(k) else None
                stem = Path(p["sumber"][0]).stem
                waktu_ = time.strftime("%H%M%S")
                berkas = PROYEK / f"{stem}_EDIT_{waktu_}.proyek.json"  # disimpan: bisa dibuka/diedit lagi
                berkas.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
                keluar = PROYEK / f"{stem}_EDIT_{waktu_}.mp4"

                def kerja(log):
                    jalankan_autoedit(["--proyek", str(berkas), "--keluar", str(keluar)], log)
                    selera.catat("edit", {k: p.get(k) for k in ("gaya", "warna", "judul", "bingkai", "rasio", "versi")})
                    return {"p": keluar.name, "proyek": berkas.name}

                self.kirim({"id": jalan_tugas(kerja)})

            elif u.path == "/otomatis":
                self.kirim(ukur_otomatis(path_aman(self.body_json()["video"])))

            elif u.path == "/setelan":
                import magic
                o = self.body_json()
                magic.simpan_setelan(o.get("online"), o.get("kunci"))
                self.kirim({"online": magic.boleh_online(), "ada_kunci": magic.ada_kunci()})

            elif u.path == "/contoh":
                # gambar kecil media ini dengan satu template, untuk kartu pilihan template
                o = self.body_json()
                video = path_aman(o["video"])
                tpl = ae.TEMPLATE[o["template"]]
                src_w, src_h, _ = ae.info_video(video)
                w, h = ae.ukuran_keluar(src_w, src_h, o.get("rasio", "asli"))
                k = 360 / min(w, h)
                w, h = round(w * k / 2) * 2, round(h * k / 2) * 2
                keluar = PROYEK / f"_contoh_{hashlib.md5(o['template'].encode()).hexdigest()[:6]}.jpg"
                ae.pratinjau(video, keluar, float(o.get("t", 1.0)), tpl["gaya"], tpl["warna"], tpl["judul"],
                             o.get("hook", ""),
                             atur_template({} if tpl.get("tanpa_auto") else ukur_otomatis(video), tpl["atur"]),
                             w, h, None)
                self.kirim({"p": keluar.name})

            elif u.path == "/pratinjau":
                # langsung di proses ini (tanpa membuka python baru) supaya preview cepat
                o = self.body_json()
                video = path_aman(o["video"])
                audio = Path(o["audio"]).stem if o.get("audio") else None
                cache = video.with_name(video.stem + (f".{audio}" if audio else "") + ".kata.json")
                src_w, src_h, _ = ae.info_video(video)
                w, h = ae.ukuran_keluar(src_w, src_h, o.get("rasio", "asli"))
                keluar = PROYEK / f"_pratinjau_{uuid.uuid4().hex[:6]}.jpg"
                for lama in PROYEK.glob("_pratinjau_*.jpg"):  # preview lama tidak perlu disimpan
                    lama.unlink(missing_ok=True)
                ae.pratinjau(video, keluar, float(o.get("t", 1.0)), o["gaya"], o.get("warna") or None,
                             o.get("judul") or None, o.get("hook", ""), o.get("atur", {}), w, h, cache,
                             bingkai=o.get("bingkai", "isi"))
                self.kirim({"p": keluar.name})

            elif u.path == "/render":
                o = self.body_json()
                video = path_aman(o["video"])
                ext = ".jpg" if ae.foto(video) else ".mp4"
                keluar = PROYEK / f"{video.stem}_EDIT_{time.strftime('%H%M%S')}{ext}"

                def kerja(log):
                    jalankan_autoedit(argumen(o, video) + ["--keluar", str(keluar)], log)
                    selera.catat("edit", {k: o.get(k) for k in ("gaya", "warna", "judul", "rasio")})
                    return {"p": keluar.name}

                self.kirim({"id": jalan_tugas(kerja)})
            else:
                self.kirim({"galat": "tidak ada"}, kode=404)
        except Exception as e:
            self.kirim({"galat": str(e)}, kode=400)


def buka_jendela(url):
    """Buka sebagai jendela aplikasi sendiri (mode --app Edge/Chrome: tanpa tab & address bar)."""
    for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(exe).exists():
            subprocess.Popen([exe, f"--app={url}", "--window-size=1400,900"])
            return
    webbrowser.open(url)


def jaga():
    """Matikan server kalau jendela aplikasi sudah ditutup (tidak ada ping 20 detik), kecuali sedang render."""
    while True:
        time.sleep(5)
        sibuk = any(not t["selesai"] for t in TUGAS.values())
        if not sibuk and time.time() - DETAK > 20:
            os._exit(0)


DETAK = time.time() + 40  # beri waktu jendela untuk terbuka

if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:  # sudah jalan (dibuka dua kali): cukup buka jendelanya lagi
        buka_jendela(url)
        sys.exit(0)
    print(f"Editor Otomatis jalan di {url}")
    if "--tanpa-browser" not in sys.argv:
        buka_jendela(url)
        threading.Thread(target=jaga, daemon=True).start()
    server.serve_forever()
