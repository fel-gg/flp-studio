"""Caption, hashtag, dan cover untuk tiap platform: Instagram, TikTok, YouTube (Shorts), X, LinkedIn.

Gemini membaca transkrip + 4 frame kecil (video utuh tidak di-upload). Tanpa internet/kunci: caption dibuat dari
transkrip (kalimat pertama jadi hook, kata kunci jadi hashtag). Cover = frame terbaik (tajam, wajah jelas,
terang cukup) dari video hasil.

    python caption.py hasil.mp4 [--kata video.kata.json] [--catatan "konteks tambahan"]
"""
import argparse
import base64
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import autoedit as ae
import magic

PLATFORM = {
    "instagram": "Instagram Reels",
    "tiktok": "TikTok",
    "youtube": "YouTube Shorts",
    "x": "X (Twitter)",
    "linkedin": "LinkedIn",
}


def skema():
    s = {"type": "STRING"}
    daftar = {"type": "ARRAY", "items": s}
    return {"type": "OBJECT", "properties": {
        "instagram": {"type": "OBJECT", "properties": {"caption": s, "hashtag": daftar}, "required": ["caption", "hashtag"]},
        "tiktok": {"type": "OBJECT", "properties": {"caption": s, "hashtag": daftar}, "required": ["caption", "hashtag"]},
        "youtube": {"type": "OBJECT", "properties": {"judul": s, "deskripsi": s, "tag": daftar},
                    "required": ["judul", "deskripsi", "tag"]},
        "x": {"type": "OBJECT", "properties": {"teks": s}, "required": ["teks"]},
        "linkedin": {"type": "OBJECT", "properties": {"teks": s, "hashtag": daftar}, "required": ["teks", "hashtag"]},
    }, "required": list(PLATFORM)}


def prompt(teks, catatan):
    return f"""You write social captions for a personal brand. The owner is a young creator who documents
learning and everyday moments, speaks English in the videos, and loves a warm, melancholic, cinematic aesthetic
(Lana Del Rey, golden hour, film photos, quiet nights). Voice: honest, soft, a little poetic, never cringe,
never salesy, no fake hype, no clickbait lies. Emojis: at most 1-2, only where natural.

Transcript of the video: "{teks or '(no speech)'}"
Extra context from the owner: "{catatan or '-'}"
Four frames from the video are attached.

Write one version per platform, each adapted to how that platform actually works:
- instagram: first line is a hook that stops the scroll (under 12 words), then 1-3 short lines, line breaks between
  them, end with a gentle question or invitation. 5-8 hashtags: mix of niche and mid-size (no #fyp, no #viral).
- tiktok: one or two short lines under 150 characters, conversational. 3-5 hashtags.
- youtube: Shorts title under 60 characters (curiosity, no ALL CAPS), description of 2-3 sentences, 8-12 tags
  (search phrases, lowercase, no #).
- x: one post under 260 characters that works as a standalone thought; no hashtags or at most one.
- linkedin: 80-150 words, reflective first-person story -> one clear lesson or insight, short paragraphs with blank
  lines between them, professional but warm. 3 hashtags.
Hashtags without the # sign. Everything in English."""


def frame_kecil(video, n=4):
    _, _, d = ae.info_video(video)
    return magic.ambil_frame(video, d, n) if d else magic.ambil_frame(video, 0, 1)


def caption_offline(teks, catatan=""):
    """Tanpa Gemini: hook = kalimat pertama yang pendek, hashtag dari kata yang paling sering muncul."""
    kalimat = [k.strip() for k in re.split(r"(?<=[.!?])\s+", teks) if k.strip()]
    hook = next((k for k in kalimat if 3 <= len(k.split()) <= 12), kalimat[0] if kalimat else "A quiet little moment.")
    isi = " ".join(kalimat[1:3]) if len(kalimat) > 1 else (catatan or "Saving this one.")
    henti = set("the a an and or but to of in on at for with is are was were be been i you he she it we they my your "
                "this that these those so just really very like what when where how not no yes do did does have has "
                "had me im i'm it's its there here about from into out up down if then than as can will would "
                "going gonna get got one all some more most also because".split())
    kata = [w for w in re.findall(r"[a-zA-Z']{4,}", teks.lower()) if w not in henti]
    kunci = [w for w, _ in Counter(kata).most_common(5)]
    tag = list(dict.fromkeys(kunci + ["dailyvlog", "learninginpublic", "slowliving", "aestheticvideo",
                                       "goldenhour", "storytelling"]))
    return {
        "instagram": {"caption": f"{hook}\n\n{isi}\n\nWhat would you have done?", "hashtag": tag[:8]},
        "tiktok": {"caption": hook[:140], "hashtag": tag[:4]},
        "youtube": {"judul": hook[:58], "deskripsi": f"{hook} {isi}".strip(), "tag": [t for t in tag][:10]},
        "x": {"teks": (hook + " " + isi)[:255]},
        "linkedin": {"teks": f"{hook}\n\n{isi}\n\nSmall moments like this are where most of my learning happens.",
                     "hashtag": ["learning", "growth", "storytelling"]},
        "model": "offline",
    }


def buat_caption(video, kata=None, catatan=""):
    teks = " ".join(k["w"] for k in (kata or []))[:3000]
    bagian = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f).decode()}}
              for f in frame_kecil(video)]
    bagian.append({"text": prompt(teks, catatan)})
    try:
        hasil = magic.minta_json(bagian, skema(), 0.8)
    except RuntimeError as e:
        hasil = caption_offline(teks, catatan)
        hasil["sebab"] = str(e)
    for p in ("instagram", "tiktok", "linkedin"):  # rapikan: tanpa '#', tanpa spasi, tanpa duplikat
        hasil[p]["hashtag"] = list(dict.fromkeys(re.sub(r"[^\w]", "", h) for h in hasil[p].get("hashtag", [])
                                                 if re.sub(r"[^\w]", "", h)))
    return hasil


def teks_siap_salin(h):
    """Satu teks per platform, siap ditempel (hashtag sudah diberi #)."""
    tag = lambda xs: " ".join("#" + x for x in xs)
    return {
        "instagram": f"{h['instagram']['caption']}\n\n{tag(h['instagram']['hashtag'])}",
        "tiktok": f"{h['tiktok']['caption']} {tag(h['tiktok']['hashtag'])}",
        "youtube": f"{h['youtube']['judul']}\n\n{h['youtube']['deskripsi']}\n\nTags: {', '.join(h['youtube']['tag'])}",
        "x": h["x"]["teks"],
        "linkedin": f"{h['linkedin']['teks']}\n\n{tag(h['linkedin']['hashtag'])}",
    }


def pilih_cover(video, keluar, n=24):
    """Frame terbaik untuk cover: tajam (variansi Laplacian), ada wajah yang cukup besar, terang cukup;
    hindari 0.6 s awal/akhir (fade). Kembalikan detik yang dipilih."""
    import cv2
    import numpy as np
    w, h, d = ae.info_video(video)
    if not d:
        ae.jalankan(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-q:v", "2", str(keluar)])
        return 0.0
    mata = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    terbaik, skor_maks = d / 2, -1
    for i in range(n):
        t = 0.6 + (d - 1.2) * (i + 0.5) / n
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                            "-vf", "scale=360:-2", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True, creationflags=ae.TANPA_JENDELA)
        hh = round(360 * h / w / 2) * 2
        if len(r.stdout) != 360 * hh:
            continue
        g = np.frombuffer(r.stdout, np.uint8).reshape(hh, 360)
        tajam = cv2.Laplacian(g, cv2.CV_64F).var()
        terang = g.mean() / 255
        wajah = mata.detectMultiScale(g, 1.1, 5, minSize=(40, 40))
        besar = max((fw * fh for _, _, fw, fh in wajah), default=0) / (360 * hh)
        skor = np.log1p(tajam) * (1 + 6 * min(besar, 0.12)) * (1 - abs(terang - 0.5))
        if skor > skor_maks:
            skor_maks, terbaik = skor, t
    ae.jalankan(["ffmpeg", "-y", "-v", "error", "-ss", f"{terbaik:.2f}", "-i", str(video), "-frames:v", "1",
                 "-q:v", "2", str(keluar)])
    return round(terbaik, 2)


def proses(video, kata=None, catatan=""):
    """Tulis <stem>.caption.json, <stem>.caption.txt, dan <stem>_cover.jpg di samping video."""
    video = Path(video)
    h = buat_caption(video, kata, catatan)
    h["siap"] = teks_siap_salin(h)
    h["cover"] = video.with_name(f"{video.stem}_cover.jpg").name
    h["cover_detik"] = pilih_cover(video, video.with_name(h["cover"]))
    video.with_name(f"{video.stem}.caption.json").write_text(json.dumps(h, ensure_ascii=False, indent=1),
                                                            encoding="utf-8")
    video.with_name(f"{video.stem}.caption.txt").write_text(
        "\n\n".join(f"===== {PLATFORM[p]} =====\n{t}" for p, t in h["siap"].items()), encoding="utf-8")
    return h


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--kata", type=Path)
    ap.add_argument("--catatan", default="")
    a = ap.parse_args()
    kata = json.loads(a.kata.read_text(encoding="utf-8")) if a.kata else []
    print(json.dumps(proses(a.video, kata, a.catatan)["siap"], ensure_ascii=False, indent=1))
