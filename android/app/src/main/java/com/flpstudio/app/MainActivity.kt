package com.flpstudio.app

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** Satu layar untuk orang awam: pilih video -> otomatis jadi -> pilih gaya -> simpan/bagikan. */
class MainActivity : AppCompatActivity() {
    private var video: Uri? = null
    private var rencana: Rencana? = null
    private var bingkai: Bingkai? = null
    private var gaya = Gaya.BERSIH
    private var hasil: File? = null
    private var kerja: Job? = null
    private var pemain: ExoPlayer? = null
    private val tombolGaya = mutableMapOf<Gaya, Button>()

    private val pilih = registerForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) mulai(uri)
    }

    private val prefs by lazy { getSharedPreferences("flp", Context.MODE_PRIVATE) }
    private val status by lazy { findViewById<TextView>(R.id.status) }
    private val bar by lazy { findViewById<ProgressBar>(R.id.bar) }

    override fun onCreate(simpanan: Bundle?) {
        super.onCreate(simpanan)
        setContentView(R.layout.activity_main)
        findViewById<Button>(R.id.pilih).setOnClickListener {
            pilih.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.VideoOnly))
        }
        findViewById<Button>(R.id.simpan).setOnClickListener { simpanKeGaleri() }
        findViewById<Button>(R.id.bagikan).setOnClickListener { bagikan() }
        findViewById<Button>(R.id.setelan).setOnClickListener { bukaSetelan() }
        val baris = findViewById<LinearLayout>(R.id.gayaBaris)
        Gaya.entries.forEach { g ->
            val b = Button(this).apply {
                text = g.nama; isAllCaps = false; isEnabled = false
                setOnClickListener { if (g != gaya) { gaya = g; segarGaya(); jalankan() } }
            }
            tombolGaya[g] = b
            baris.addView(b)
        }
        segarGaya()
        // video yang dibagikan dari Galeri/aplikasi lain langsung diedit
        if (intent?.action == Intent.ACTION_SEND) {
            @Suppress("DEPRECATION")
            (intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))?.let { mulai(it) }
        }
        if (simpanan == null && kunci().isBlank()) {
            status.text = "Tanpa kunci API Gemini, video tetap dirapikan (9:16, zoom, warna). " +
                "Subtitle dan potong jeda butuh kunci: buka Setelan."
        }
    }

    private fun kunci(): String = prefs.getString("kunci", null)?.trim()?.takeIf { it.isNotEmpty() } ?: BuildConfig.GEMINI_KEY

    private fun mulai(uri: Uri) {
        video = uri; rencana = null; bingkai = null
        jalankan()
    }

    private fun jalankan() {
        val uri = video ?: return
        kerja?.cancel()
        kerja = lifecycleScope.launch {
            sibuk(true)
            try {
                val dur = withContext(Dispatchers.IO) { durasi(uri) }
                if (rencana == null) rencana = rencanakan(uri, dur)
                val r = rencana!!
                if (bingkai == null) {
                    status.text = "Mencari wajah untuk bingkai 9:16…"
                    bingkai = withContext(Dispatchers.Default) { Wajah.cari(this@MainActivity, uri, dur) }
                }
                status.text = "Membuat video…"
                File(cacheDir, "hasil").listFiles()?.forEach { it.delete() }
                val f = Penyunting.render(this@MainActivity, uri, r, gaya, bingkai!!,
                    File(cacheDir, "hasil/FLP_${System.currentTimeMillis()}.mp4")) { p ->
                    bar.isIndeterminate = false; bar.progress = p; status.text = "Membuat video… $p%"
                }
                hasil = f
                putar(f)
                val ket = if (r.frasa.isEmpty()) "" else ", ${r.frasa.size} baris subtitle"
                status.text = "Selesai: ${detik(dur)} jadi ${detik(r.durasi)}, ${r.potongan.size} potongan$ket. " +
                    "Coba gaya lain, atau Simpan."
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                status.text = e.message ?: "Terjadi kesalahan."
            } finally {
                sibuk(false)
            }
        }
    }

    /** Gemini kalau ada kunci; kalau tidak (atau gagal), rencana tanpa transkrip supaya tetap jadi. */
    private suspend fun rencanakan(uri: Uri, dur: Double): Rencana {
        val k = kunci()
        if (k.isNotBlank()) {
            try {
                val t = withContext(Dispatchers.IO) {
                    Gemini.transkrip(this@MainActivity, uri, k) { s -> runOnUiThread { status.text = s } }
                }
                return Perencana.buat(t.kata, dur, t.buang, t.hook, gaya.zoom)
            } catch (e: GeminiGagal) {
                status.text = "${e.message} Lanjut tanpa subtitle…"
            }
        }
        return Perencana.buat(emptyList(), dur, emptySet(), null, gaya.zoom)
    }

    private fun sibuk(ya: Boolean) {
        bar.visibility = if (ya) View.VISIBLE else View.INVISIBLE
        if (ya) bar.isIndeterminate = true
        findViewById<Button>(R.id.simpan).isEnabled = !ya && hasil != null
        findViewById<Button>(R.id.bagikan).isEnabled = !ya && hasil != null
        tombolGaya.values.forEach { it.isEnabled = !ya && video != null }
    }

    private fun segarGaya() {
        tombolGaya.forEach { (g, b) -> b.alpha = if (g == gaya) 1f else 0.55f }
    }

    private fun putar(f: File) {
        val p = pemain ?: ExoPlayer.Builder(this).build().also {
            pemain = it
            findViewById<PlayerView>(R.id.pemutar).player = it
        }
        findViewById<View>(R.id.kosong).visibility = View.GONE
        findViewById<View>(R.id.pemutar).visibility = View.VISIBLE
        p.setMediaItem(MediaItem.fromUri(Uri.fromFile(f)))
        p.repeatMode = Player.REPEAT_MODE_ALL
        p.prepare()
        p.play()
    }

    private fun simpanKeGaleri() {
        val f = hasil ?: return
        status.text = if (simpanFile(f, f.name)) "Tersimpan di Galeri (Movies/FLP Studio)." else "Gagal menyimpan ke Galeri."
    }

    private fun simpanFile(f: File, nama: String): Boolean {
        val nilai = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, nama)
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            if (Build.VERSION.SDK_INT >= 29) put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/FLP Studio")
        }
        val uri = contentResolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, nilai) ?: return false
        contentResolver.openOutputStream(uri)?.use { out -> f.inputStream().use { it.copyTo(out) } } ?: return false
        return true
    }

    private fun bagikan() {
        val f = hasil ?: return
        val uri = FileProvider.getUriForFile(this, "$packageName.berkas", f)
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "video/mp4"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }, "Bagikan video"))
    }

    private fun bukaSetelan() {
        val isian = EditText(this).apply {
            hint = if (kunci().isBlank()) "belum ada" else "sudah tersimpan (isi untuk mengganti)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        AlertDialog.Builder(this)
            .setTitle("Kunci API Gemini")
            .setMessage("Untuk subtitle dan potong jeda otomatis. Gratis di aistudio.google.com/apikey. " +
                "Kunci hanya disimpan di HP ini.")
            .setView(isian)
            .setPositiveButton("Simpan") { _, _ ->
                val k = isian.text.toString().trim()
                if (k.isNotEmpty()) { prefs.edit().putString("kunci", k).apply(); status.text = "Kunci API tersimpan." }
            }
            .setNeutralButton("Hapus kunci") { _, _ -> prefs.edit().remove("kunci").apply(); status.text = "Kunci API dihapus." }
            .setNegativeButton("Batal", null)
            .show()
    }

    /** Durasi video (detik). Sebagian penyedia file menolak MediaMetadataRetriever: coba MediaExtractor. */
    private fun durasi(uri: Uri): Double {
        val m = MediaMetadataRetriever()
        try {
            m.setDataSource(this, uri)
            m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()?.let { return it / 1000.0 }
        } catch (e: RuntimeException) {
            // lanjut ke cara kedua
        } finally {
            m.release()
        }
        val ex = android.media.MediaExtractor()
        try {
            ex.setDataSource(this, uri, null)
            val us = (0 until ex.trackCount).maxOfOrNull {
                val f = ex.getTrackFormat(it)
                if (f.containsKey(android.media.MediaFormat.KEY_DURATION)) f.getLong(android.media.MediaFormat.KEY_DURATION) else 0L
            } ?: 0L
            if (us > 0) return us / 1e6
        } catch (e: java.io.IOException) {
            // tidak bisa dibaca sama sekali
        } finally {
            ex.release()
        }
        throw Exception("Video ini tidak bisa dibuka. Coba pilih lagi dari Galeri.")
    }

    private fun detik(d: Double) = "%.1f detik".format(d).replace('.', ',')

    override fun onDestroy() {
        pemain?.release(); pemain = null
        super.onDestroy()
    }
}
