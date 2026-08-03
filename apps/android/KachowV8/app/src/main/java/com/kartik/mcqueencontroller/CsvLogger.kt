package com.kartik.mcqueencontroller

import android.content.Context
import android.os.Environment
import java.io.BufferedWriter
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Local phone log. Laptop camera logger fills image_path in the final dataset. */
class CsvLogger(private val context: Context) {

    data class Row(
        val timestamp: Long,
        val imagePath: String,
        val throttleSent: Int,
        val servoSent: Int,
    )

    private var writer: BufferedWriter? = null
    private var activeFile: File? = null
    private var lastSequence = Long.MIN_VALUE
    private val recentRows = ArrayDeque<Row>()

    val isLogging: Boolean
        @Synchronized get() = writer != null

    @Synchronized
    fun start(): File {
        stop()
        val base = context.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS)
            ?: File(context.filesDir, "documents")
        val folder = File(base, "KachowLogs").apply { mkdirs() }
        val stamp = SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.US).format(Date())
        val file = File(folder, "kachow_$stamp.csv")
        writer = BufferedWriter(FileWriter(file, false)).also {
            it.write("timestamp,throttle_sent,servo_sent,image_path")
            it.newLine()
            it.flush()
        }
        activeFile = file
        lastSequence = Long.MIN_VALUE
        recentRows.clear()
        return file
    }

    @Synchronized
    fun append(timestamp: Long, sequence: Long, throttleSent: Int, servoSent: Int) {
        val localWriter = writer ?: return
        if (sequence == lastSequence) return
        lastSequence = sequence
        val row = Row(timestamp, "", throttleSent, servoSent)
        localWriter.write("${row.timestamp},${row.throttleSent},${row.servoSent},")
        localWriter.newLine()
        localWriter.flush()
        recentRows.addLast(row)
        while (recentRows.size > 60) recentRows.removeFirst()
    }

    @Synchronized
    fun stop(): File? {
        runCatching { writer?.flush() }
        runCatching { writer?.close() }
        writer = null
        return activeFile
    }

    @Synchronized fun currentFile(): File? = activeFile
    @Synchronized fun rows(): List<Row> = recentRows.toList().asReversed()
}
