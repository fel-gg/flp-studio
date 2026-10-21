package com.flpstudio.app

import android.content.Context
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaMuxer
import android.net.Uri
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer

class GeminiGagal(pesan: String) : Exception(pesan)

data class Transkrip(val kata: List<Kata>, val buang: Set<Int>, val hook: String)

/** Transkrip kata per kata + kata yang sebaiknya dibuang, lewat Gemini (sama dengan model versi PC). */
object Gemini {
    private val MODEL = listOf("gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3-flash-preview")

    private const val PERINTAH = """Transkrip semua ucapan di audio ini KATA PER KATA, dalam bahasa aslinya.
Untuk tiap kata beri waktu mulai "s" dan selesai "e" dalam detik (2 desimal), urut dari awal.
Sertakan tanda baca menempel di kata (koma, titik, tanda tanya) supaya akhir kalimat terlihat.
"buang": indeks kata yang sebaiknya dibuang editor: kata pengisi (eh, em, um, anu), kata yang terulang
karena gagap, dan kalimat/take yang diulang (buang yang gagal, simpan take terakhir yang lengkap).
"hook": kalimat pembuka paling kuat dari ucapan itu sendiri, maksimal 9 kata, tidak boleh terpotong
di tengah kalimat. Kosongkan kalau tidak ada ucapan."""

    fun transkrip(ctx: Context, video: Uri, kunci: String, log: (String) -> Unit): Transkrip {
        val audio = ambilAudio(ctx, video)
        try {
            if (audio.length() > 14_000_000) throw GeminiGagal("Video terlalu panjang untuk versi HP (maks ±10 menit).")
            val data = Base64.encodeToString(audio.readBytes(), Base64.NO_WRAP)
            val badan = JSONObject()
                .put("contents", JSONArray().put(JSONObject().put("parts", JSONArray()
                    .put(JSONObject().put("inline_data", JSONObject().put("mime_type", "audio/mp4").put("data", data)))
                    .put(JSONObject().put("text", PERINTAH)))))
                .put("generationConfig", JSONObject()
                    .put("temperature", 0)
                    .put("responseMimeType", "application/json")
                    .put("responseSchema", skema()))
            var galat = "Gemini tidak bisa dihubungi."
            for (m in MODEL) {
                log("Mendengarkan ucapan…")
                val (kode, isi) = kirim(m, kunci, badan.toString())
                when {
                    kode == 200 -> return baca(isi)
                    kode == 400 && isi.contains("API_KEY", true) -> throw GeminiGagal("Kunci API Gemini tidak valid. Periksa di Setelan.")
                    kode == 403 -> throw GeminiGagal("Kunci API Gemini ditolak. Periksa di Setelan.")
                    else -> galat = "Gemini ($m): HTTP $kode"
                }
            }
            throw GeminiGagal(galat)
        } finally {
            audio.delete()
        }
    }

    private fun kirim(model: String, kunci: String, badan: String): Pair<Int, String> {
        val c = URL("https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent")
            .openConnection() as HttpURLConnection
        c.requestMethod = "POST"
        c.connectTimeout = 20_000
        c.readTimeout = 180_000
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.setRequestProperty("x-goog-api-key", kunci)
        return try {
            c.outputStream.use { it.write(badan.toByteArray()) }
            val kode = c.responseCode
            val isi = (if (kode in 200..299) c.inputStream else c.errorStream)?.bufferedReader()?.readText().orEmpty()
            kode to isi
        } catch (e: java.io.IOException) {
            throw GeminiGagal("Tidak ada internet, atau Gemini tidak menjawab.")
        } finally {
            c.disconnect()
        }
    }

    private fun baca(isi: String): Transkrip {
        val teks = JSONObject(isi).getJSONArray("candidates").getJSONObject(0)
            .getJSONObject("content").getJSONArray("parts").getJSONObject(0).getString("text")
        val j = JSONObject(teks)
        val ka = j.optJSONArray("kata") ?: JSONArray()
        val kata = (0 until ka.length()).map {
            val k = ka.getJSONObject(it)
            Kata(k.optString("w"), k.optDouble("s", 0.0), k.optDouble("e", 0.0))
        }
        val bu = j.optJSONArray("buang") ?: JSONArray()
        return Transkrip(kata, (0 until bu.length()).map { bu.getInt(it) }.toSet(), j.optString("hook"))
    }

    private fun skema(): JSONObject {
        val kata = JSONObject().put("type", "OBJECT").put("properties", JSONObject()
            .put("w", JSONObject().put("type", "STRING"))
            .put("s", JSONObject().put("type", "NUMBER"))
            .put("e", JSONObject().put("type", "NUMBER")))
            .put("required", JSONArray().put("w").put("s").put("e"))
        return JSONObject().put("type", "OBJECT").put("properties", JSONObject()
            .put("kata", JSONObject().put("type", "ARRAY").put("items", kata))
            .put("buang", JSONObject().put("type", "ARRAY").put("items", JSONObject().put("type", "INTEGER")))
            .put("hook", JSONObject().put("type", "STRING")))
            .put("required", JSONArray().put("kata").put("buang").put("hook"))
    }

    /** Salin trek suara video apa adanya (tanpa encode ulang) ke file .m4a kecil untuk dikirim ke Gemini. */
    private fun ambilAudio(ctx: Context, video: Uri): File {
        val keluar = File(ctx.cacheDir, "suara.m4a")
        val ex = MediaExtractor()
        try {
            ex.setDataSource(ctx, video, null)
            val trek = (0 until ex.trackCount).firstOrNull {
                ex.getTrackFormat(it).getString(android.media.MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            } ?: throw GeminiGagal("Video ini tidak punya suara.")
            ex.selectTrack(trek)
            val mux = MediaMuxer(keluar.path, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
            val t = mux.addTrack(ex.getTrackFormat(trek))
            mux.start()
            val buf = ByteBuffer.allocate(1 shl 20)
            val info = MediaCodec.BufferInfo()
            while (true) {
                info.size = ex.readSampleData(buf, 0)
                if (info.size < 0) break
                info.offset = 0
                info.presentationTimeUs = ex.sampleTime
                info.flags = if (ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0
                mux.writeSampleData(t, buf, info)
                ex.advance()
            }
            mux.stop(); mux.release()
        } catch (e: IllegalStateException) {
            throw GeminiGagal("Format suara video ini belum didukung.")
        } finally {
            ex.release()
        }
        return keluar
    }
}
