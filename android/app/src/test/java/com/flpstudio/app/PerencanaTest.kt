package com.flpstudio.app

import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PerencanaTest {
    private val kata = JSONArray(javaClass.getResource("/contoh_waktu.json")!!.readText()).let { a ->
        (0 until a.length()).map { val k = a.getJSONObject(it); Kata(k.getString("w"), k.getDouble("s"), k.getDouble("e")) }
    }

    @Test
    fun samaDenganVersiPc() {
        val r = Perencana.buat(kata, 30.0, emptySet(), null, 1.07f)
        r.potongan.forEach { println("${it.mulai} ${it.selesai} ${it.zoom}") }
        println("hook: ${r.hook} | frasa ${r.frasa.size}: ${r.frasa.take(3)}")
        assertEquals(7, r.potongan.size)            // pro.py: 7 potongan
        assertEquals(28.36, r.durasi, 0.05)         // pro.py: 28,36 detik
        assertEquals("w0 w1 w2 w3 w4", r.hook)  // kalimat pertama sampai koma
        assertTrue(r.frasa.zipWithNext().all { (a, b) -> a.b <= b.a + 1e-6 })  // subtitle tidak bertumpuk
    }

    @Test
    fun kataDibuangGemini() {
        val r = Perencana.buat(kata, 30.0, setOf(0, 1, 2), null, 1.07f)
        assertEquals(0.48, r.potongan.first().mulai, 0.01)  // kata ke-4 mulai 0,6 s, dikurangi padding 0,12
    }

    @Test
    fun tanpaTranskripTetapJadi() {
        val r = Perencana.buat(emptyList(), 20.0, emptySet(), null, 1.07f)
        assertEquals(20.0, r.durasi, 1e-6)
        assertTrue(r.potongan.size >= 4)            // tetap ganti bingkai tiap ~4 detik
        assertEquals("", r.hook)
    }
}
