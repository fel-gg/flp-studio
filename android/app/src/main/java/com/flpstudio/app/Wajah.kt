package com.flpstudio.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.PointF
import android.media.FaceDetector
import android.media.MediaMetadataRetriever
import android.net.Uri

/** Ukuran tampil video (sudah memperhitungkan rotasi) dan posisi subjek (0..1) untuk crop 9:16. */
data class Bingkai(val lebar: Int, val tinggi: Int, val fx: Float, val fy: Float)

/**
 * Video 16:9 dijadikan 9:16: crop harus mengikuti wajah, bukan selalu di tengah (sama dengan posisi_wajah
 * di versi PC). Beberapa frame diperiksa dengan FaceDetector bawaan Android; posisi wajah dirata-rata.
 */
object Wajah {
    fun cari(ctx: Context, video: Uri, durasi: Double, n: Int = 6): Bingkai {
        val m = MediaMetadataRetriever()
        try {
            m.setDataSource(ctx, video)
            var w = m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
            var h = m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
            val rot = m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
            if (rot == 90 || rot == 270) { val t = w; w = h; h = t }
            if (w <= 0 || h <= 0) return Bingkai(9, 16, 0.5f, 0.45f)
            if (w.toFloat() / h < 0.7f) return Bingkai(w, h, 0.5f, 0.45f) // sudah tegak: tidak perlu digeser
            val xs = mutableListOf<Float>()
            val ys = mutableListOf<Float>()
            for (i in 1..n) {
                val t = (durasi * i / (n + 1) * 1_000_000).toLong()
                val f = m.getFrameAtTime(t, MediaMetadataRetriever.OPTION_CLOSEST_SYNC) ?: continue
                val lebar = 480
                val kecil = Bitmap.createScaledBitmap(f, lebar, (lebar * f.height / f.width) / 2 * 2, true)
                    .copy(Bitmap.Config.RGB_565, false)
                f.recycle()
                val hasil = arrayOfNulls<FaceDetector.Face>(3)
                val jumlah = FaceDetector(kecil.width, kecil.height, 3).findFaces(kecil, hasil)
                // wajah terbesar (paling yakin subjek utama)
                hasil.take(jumlah).filterNotNull().maxByOrNull { it.eyesDistance() }?.let {
                    val p = PointF(); it.getMidPoint(p)
                    xs.add(p.x / kecil.width); ys.add(p.y / kecil.height)
                }
                kecil.recycle()
            }
            if (xs.isEmpty()) return Bingkai(w, h, 0.5f, 0.45f)
            return Bingkai(w, h, xs.sorted()[xs.size / 2], ys.sorted()[ys.size / 2]) // median: tahan salah deteksi
        } catch (e: RuntimeException) {
            return Bingkai(9, 16, 0.5f, 0.45f)
        } finally {
            m.release()
        }
    }
}
