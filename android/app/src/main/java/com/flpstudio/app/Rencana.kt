package com.flpstudio.app

/** Satu kata hasil transkrip, waktu dalam detik di video asli. */
data class Kata(val w: String, val s: Double, val e: Double)

/** Bagian video asli yang dipakai, berurutan di hasil. zoom 1.0 = bingkai lebar. */
data class Potongan(val mulai: Double, val selesai: Double, val zoom: Float)

/** Satu baris subtitle, waktu dalam detik di video HASIL. */
data class Frasa(val a: Double, val b: Double, val teks: String)

data class Rencana(val potongan: List<Potongan>, val frasa: List<Frasa>, val hook: String) {
    val durasi: Double get() = potongan.sumOf { it.selesai - it.mulai }
}

/**
 * Edit seperti editor profesional, dari prinsip dasar (sama dengan pro.py versi PC):
 * 1. tidak ada jeda mati: jeda > ~0,36 s dan kata pengisi dibuang,
 * 2. gambar tidak diam lama: bingkai berganti (punch-in) di tiap potongan dan setiap ~4 detik bicara,
 * 3. hook pembuka dari kalimat pertama, subtitle pendek yang mudah dibaca tanpa suara.
 */
object Perencana {
    private val PENGISI = Regex("^(um+|uh+|uhm+|er+|erm+|eh+|em+|ehm+|hmm+|mm+|ah+|anu)[.,!?]*$", RegexOption.IGNORE_CASE)
    private const val PAD = 0.12
    private const val JEDA = 0.12 // dibandingkan SETELAH padding kiri-kanan: jeda asli > 0,36 s dibuang

    fun buat(semua: List<Kata>, durasi: Double, buang: Set<Int>, hookGemini: String?, zoom: Float): Rencana {
        val kata = semua.filterIndexed { i, k -> i !in buang && !PENGISI.matches(k.w.trim()) && k.e > k.s }
        val bagian = mutableListOf<DoubleArray>()
        for (k in kata) {
            val a = maxOf(0.0, k.s - PAD)
            val b = minOf(durasi, k.e + PAD)
            val akhir = bagian.lastOrNull()
            if (akhir != null && a - akhir[1] <= JEDA) akhir[1] = maxOf(akhir[1], b) else bagian.add(doubleArrayOf(a, b))
        }
        if (bagian.isEmpty()) bagian.add(doubleArrayOf(0.0, durasi))
        val pecah = bagian.filter { it[1] - it[0] > 0.25 }.flatMap { pecahPanjang(it[0], it[1], kata) }
        val potongan = pecah.mapIndexed { i, (a, b) -> Potongan(a, b, if (i % 2 == 1) zoom else 1f) }
        return Rencana(potongan, frasa(kata, potongan), hookGemini?.trim()?.trimEnd(',', '.', ';', ':').orEmpty().ifEmpty { hookDariUcapan(kata) })
    }

    /** Bagian panjang dipecah di akhir kalimat/anak kalimat tiap ~3-5 detik (tidak ada yang dibuang). */
    private fun pecahPanjang(a: Double, b: Double, kata: List<Kata>, target: Double = 4.0): List<Pair<Double, Double>> {
        val batas = kata.indices.filter { i ->
            val k = kata[i]
            k.e > a && k.e < b && (k.w.trimEnd().lastOrNull() in ".,!?;:".toList() ||
                (i + 1 < kata.size && kata[i + 1].s - k.e > 0.15))
        }.map { kata[it].e }
        val hasil = mutableListOf<Pair<Double, Double>>()
        var mulai = a
        val batasPakai = if (batas.isEmpty() && kata.isEmpty()) generateSequence(a + target) { it + target }
            .takeWhile { it < b }.toList() else batas
        for (t in batasPakai) {
            if (t - mulai >= target * 0.75 && b - t >= 1.5) {
                hasil.add(mulai to t); mulai = t
            }
        }
        hasil.add(mulai to b)
        return hasil
    }

    /** Kata dipindah ke waktu hasil, lalu dikelompokkan jadi baris pendek (maks 5 kata). */
    private fun frasa(kata: List<Kata>, potongan: List<Potongan>): List<Frasa> {
        val geser = mutableListOf<Kata>()
        var total = 0.0
        for (p in potongan) {
            kata.filter { it.s >= p.mulai && it.s <= p.selesai }
                .forEach { geser.add(Kata(it.w, it.s - p.mulai + total, minOf(it.e, p.selesai) - p.mulai + total)) }
            total += p.selesai - p.mulai
        }
        val grup = mutableListOf<List<Kata>>()
        var kini = mutableListOf<Kata>()
        geser.forEachIndexed { i, k ->
            kini.add(k)
            val akhirKalimat = k.w.trimEnd().lastOrNull() in ".,!?;:".toList()
            val jeda = i + 1 < geser.size && geser[i + 1].s - k.e > 0.4
            if (kini.size >= 5 || akhirKalimat || jeda) { grup.add(kini); kini = mutableListOf() }
        }
        if (kini.isNotEmpty()) grup.add(kini)
        return grup.mapIndexed { i, g ->
            val a = g.first().s
            val huruf = g.sumOf { it.w.length + 1 }
            var b = minOf(maxOf(g.last().e, a + maxOf(5.0 / 6, huruf / 17.0)), a + 7)
            if (i + 1 < grup.size) b = minOf(b, grup[i + 1].first().s)
            Frasa(a, minOf(b, total), g.joinToString(" ") { it.w.trim() }.trim(' ', ','))
        }.filter { it.b - it.a > 0.15 }
    }

    /** Kalimat pertama yang diucapkan (maks 9 kata, atau sampai koma pertama); tidak dipotong di tengah. */
    private fun hookDariUcapan(kata: List<Kata>): String {
        val kalimat = mutableListOf<String>()
        var koma = 0
        var selesai = false
        for (k in kata.take(40)) {
            val w = k.w.trim()
            kalimat.add(w)
            if (w.endsWith(",") && koma == 0) koma = kalimat.size
            if (w.lastOrNull() in ".!?".toList()) { selesai = true; break }
        }
        if (!selesai) return ""
        val pakai = when {
            kalimat.size <= 9 -> kalimat
            koma in 3..9 -> kalimat.take(koma)
            else -> return ""
        }
        return if (pakai.size >= 3) pakai.joinToString(" ").trim(' ', ',', '.', ';') else ""
    }
}
