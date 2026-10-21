package com.flpstudio.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import androidx.media3.common.Effect
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.OverlaySettings
import androidx.media3.effect.BitmapOverlay
import androidx.media3.effect.Brightness
import androidx.media3.effect.Contrast
import androidx.media3.effect.Crop
import androidx.media3.effect.HslAdjustment
import androidx.media3.effect.OverlayEffect
import androidx.media3.effect.Presentation
import androidx.media3.effect.RgbAdjustment
import androidx.media3.effect.RgbFilter
import androidx.media3.effect.StaticOverlaySettings
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.EditedMediaItemSequence
import androidx.media3.transformer.Effects
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.ProgressHolder
import androidx.media3.transformer.Transformer
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Gaya sekali klik: warna + kuatnya punch-in. Sama dengan tombol gaya di versi PC. */
enum class Gaya(val nama: String, val zoom: Float) {
    BERSIH("Bersih", 1.07f), SINEMATIK("Sinematik", 1.05f), MONOKROM("Monokrom", 1.06f),
    ENERGIK("Energik", 1.12f), LEMBUT("Lembut", 1.04f);

    fun warna(): List<Effect> = when (this) {
        BERSIH -> listOf(Contrast(0.08f), HslAdjustment.Builder().adjustSaturation(8f).build(),
            RgbAdjustment.Builder().setRedScale(1.03f).setBlueScale(0.97f).build())
        SINEMATIK -> listOf(Contrast(0.15f), HslAdjustment.Builder().adjustSaturation(-12f).build(),
            RgbAdjustment.Builder().setRedScale(1.04f).setGreenScale(0.99f).setBlueScale(1.02f).build())
        MONOKROM -> listOf(RgbFilter.createGrayscaleFilter(), Contrast(0.18f))
        ENERGIK -> listOf(Contrast(0.2f), HslAdjustment.Builder().adjustSaturation(18f).build())
        LEMBUT -> listOf(Brightness(0.05f), Contrast(-0.06f), HslAdjustment.Builder().adjustSaturation(-8f).build(),
            RgbAdjustment.Builder().setRedScale(1.02f).build())
    }
}

/** Render rencana edit jadi MP4 9:16 di HP (Media3 Transformer, encoder hardware). */
object Penyunting {
    private const val W = 1080
    private const val H = 1920
    private const val DURASI_HOOK = 3.0

    suspend fun render(ctx: Context, video: Uri, r: Rencana, gaya: Gaya, b: Bingkai, keluar: File, progres: (Int) -> Unit): File {
        val warna = gaya.warna()
        val baris = buildList {
            r.frasa.forEach { add(Triple(Triple(it.a, it.b, it.teks), -0.58f, false)) }
            if (r.hook.isNotBlank()) add(Triple(Triple(0.0, minOf(DURASI_HOOK, r.durasi), r.hook), 0.42f, true))
        }
        var awal = 0.0
        val item = r.potongan.map { p ->
            val panjang = p.selesai - p.mulai
            val dari = awal
            awal += panjang
            val media = MediaItem.Builder().setUri(video).setClippingConfiguration(
                MediaItem.ClippingConfiguration.Builder()
                    .setStartPositionMs((p.mulai * 1000).toLong())
                    .setEndPositionMs((p.selesai * 1000).toLong()).build()).build()
            val z = if (p.zoom > 1.001f) gaya.zoom else 1f
            val efek = buildList {
                potong916(b, z)?.let { add(it) }
                add(Presentation.createForWidthAndHeight(W, H, Presentation.LAYOUT_SCALE_TO_FIT_WITH_CROP))
                addAll(warna)
                // teks dipasang per potongan dengan waktu relatif ke awal potongan itu. Overlay di tingkat
                // komposisi menampilkan dua baris sekaligus saat potongannya banyak (teruji di emulator).
                lapisanUntuk(baris, dari, dari + panjang)?.let { add(it) }
            }
            EditedMediaItem.Builder(media).setEffects(Effects(listOf(), efek)).build()
        }
        val komposisi = Composition.Builder(EditedMediaItemSequence.Builder(item).build())
            .setHdrMode(Composition.HDR_MODE_TONE_MAP_HDR_TO_SDR_USING_OPEN_GL)
            .build()
        keluar.parentFile?.mkdirs()
        keluar.delete()

        return suspendCancellableCoroutine { lanjut ->
            val utama = Handler(Looper.getMainLooper())
            val t = Transformer.Builder(ctx)
                .setVideoMimeType(MimeTypes.VIDEO_H264)
                .setAudioMimeType(MimeTypes.AUDIO_AAC)
                .addListener(object : Transformer.Listener {
                    override fun onCompleted(c: Composition, e: ExportResult) {
                        utama.removeCallbacksAndMessages(null); lanjut.resume(keluar)
                    }
                    override fun onError(c: Composition, e: ExportResult, x: ExportException) {
                        utama.removeCallbacksAndMessages(null)
                        lanjut.resumeWithException(Exception("Gagal membuat video: ${x.errorCodeName}", x))
                    }
                }).build()
            val ph = ProgressHolder()
            val pantau = object : Runnable {
                override fun run() {
                    if (t.getProgress(ph) == Transformer.PROGRESS_STATE_AVAILABLE) progres(ph.progress)
                    utama.postDelayed(this, 300)
                }
            }
            t.start(komposisi, keluar.path)
            utama.post(pantau)
            lanjut.invokeOnCancellation { utama.post { utama.removeCallbacksAndMessages(null); t.cancel() } }
        }
    }

    /** Overlay untuk teks yang tampil di rentang [dari, sampai) hasil, dengan waktu relatif ke `dari`. */
    private fun lapisanUntuk(baris: List<Triple<Triple<Double, Double, String>, Float, Boolean>>,
                             dari: Double, sampai: Double): OverlayEffect? {
        val lapis = baris.groupBy { it.second to it.third }.mapNotNull { (k, isi) ->
            val dalam = isi.map { it.first }.filter { it.second > dari && it.first < sampai }
                .map { Triple(maxOf(0.0, it.first - dari), it.second - dari, it.third) }
            if (dalam.isEmpty()) null else TeksBerwaktu(dalam, k.first, if (k.second) ::gambarHook else ::gambarSubtitle)
        }
        return if (lapis.isEmpty()) null else OverlayEffect(lapis)
    }

    /**
     * Area 9:16 (diperkecil 1/z untuk punch-in) yang berpusat di wajah, dalam koordinat Crop (-1..1, atas = +1).
     * Seperti crop_ikut di versi PC: wajah di tengah mendatar, mata sedikit di atas tengah, tidak keluar tepi.
     */
    private fun potong916(b: Bingkai, z: Float): Crop? {
        val a = b.lebar.toFloat() / b.tinggi
        val r = W.toFloat() / H
        val wN = (if (a > r) r / a else 1f) / z
        val hN = (if (a > r) 1f else a / r) / z
        if (wN > 0.999f && hN > 0.999f) return null
        val cx = b.fx.coerceIn(wN / 2, 1 - wN / 2)
        val cy = (b.fy + 0.08f * hN).coerceIn(hN / 2, 1 - hN / 2)
        return Crop(2 * (cx - wN / 2) - 1, 2 * (cx + wN / 2) - 1, 1 - 2 * (cy + hN / 2), 1 - 2 * (cy - hN / 2))
    }

    private fun gambarSubtitle(teks: String): Bitmap = gambar(teks, 62f, Typeface.create("sans-serif", Typeface.BOLD),
        Color.WHITE, kotak = Color.argb(150, 30, 24, 20))

    private fun gambarHook(teks: String): Bitmap = gambar(teks, 86f, Typeface.create("serif", Typeface.BOLD_ITALIC),
        Color.rgb(255, 244, 230), kotak = null)

    /** Teks dibungkus maks 900 px, rata tengah; subtitle di atas kotak gelap, hook dengan bayangan lembut. */
    private fun gambar(teks: String, ukuran: Float, huruf: Typeface, warna: Int, kotak: Int?): Bitmap {
        val p = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            textSize = ukuran; typeface = huruf; color = warna
            if (kotak == null) setShadowLayer(10f, 0f, 3f, Color.argb(170, 0, 0, 0))
        }
        val lebar = minOf(900, p.measureText(teks).toInt() + 2)
        val tata = StaticLayout.Builder.obtain(teks, 0, teks.length, p, lebar)
            .setAlignment(Layout.Alignment.ALIGN_CENTER).setLineSpacing(0f, 1.05f).build()
        val pad = if (kotak != null) 26 else 20
        val bmp = Bitmap.createBitmap(lebar + pad * 2, tata.height + pad * 2, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        if (kotak != null) {
            c.drawRoundRect(RectF(0f, 0f, bmp.width.toFloat(), bmp.height.toFloat()), 22f, 22f,
                Paint(Paint.ANTI_ALIAS_FLAG).apply { color = kotak })
        }
        c.translate(pad.toFloat(), pad.toFloat())
        tata.draw(c)
        return bmp
    }
}

/** Teks yang muncul pada rentang waktu tertentu di video hasil (detik). y: -1 bawah .. 1 atas. */
private class TeksBerwaktu(
    private val baris: List<Triple<Double, Double, String>>,
    y: Float,
    private val buat: (String) -> Bitmap,
) : BitmapOverlay() {
    private val cache = HashMap<String, Bitmap>()
    private val kosong = Bitmap.createBitmap(2, 2, Bitmap.Config.ARGB_8888)
    private var dasar = Long.MIN_VALUE
    private val atur = StaticOverlaySettings.Builder().setOverlayFrameAnchor(0f, 0f).setBackgroundFrameAnchor(0f, y).build()

    override fun getBitmap(presentationTimeUs: Long): Bitmap {
        if (dasar == Long.MIN_VALUE) dasar = presentationTimeUs // waktu frame pertama = detik 0 hasil
        val d = (presentationTimeUs - dasar) / 1e6
        val b = baris.firstOrNull { d >= it.first && d < it.second } ?: return kosong
        return cache.getOrPut(b.third) { buat(b.third) }
    }

    override fun getOverlaySettings(presentationTimeUs: Long): OverlaySettings = atur
}
