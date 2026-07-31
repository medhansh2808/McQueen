package com.kartik.mcqueencontroller

import java.util.Locale

object Protocol {
    const val DEFAULT_PORT = 5007
    const val TOKEN = "rc-car"
    const val MAX_STEERING = 1000
    const val MAX_THROTTLE_COMMAND = 1000

    fun newSessionId(): String = String.format(Locale.US, "%08x", System.nanoTime().toInt())

    fun hello(session: String, sequence: Long, timestampMs: Long): String =
        "H,$TOKEN,$session,$sequence,$timestampMs\n"

    fun command(
        session: String,
        sequence: Long,
        timestampMs: Long,
        steering: Int,
        throttle: Int,
        motorEnabled: Boolean,
    ): String =
        "C,$TOKEN,$session,$sequence,$timestampMs,$steering,$throttle,${if (motorEnabled) 1 else 0}\n"

    fun emergency(session: String, sequence: Long, timestampMs: Long): String =
        "E,$TOKEN,$session,$sequence,$timestampMs\n"

    fun parseStatus(raw: String): StatusPacket? {
        val fields = raw.trim().split(',')
        if (fields.size != 11 || fields[0] != "S") return null

        return runCatching {
            StatusPacket(
                session = fields[1],
                acknowledgedSequence = fields[2].toLong(),
                echoTimestampMs = fields[3].toLong(),
                commandedSteering = fields[4].toInt(),
                actualServoAngle = fields[5].toInt(),
                commandedThrottle = fields[6].toInt(),
                actualThrottle = fields[7].toInt(),
                failsafe = fields[8].toInt() != 0,
                source = fields[9],
                rssi = fields[10].toInt(),
            )
        }.getOrNull()
    }
}

data class StatusPacket(
    val session: String,
    val acknowledgedSequence: Long,
    val echoTimestampMs: Long,
    val commandedSteering: Int,
    val actualServoAngle: Int,
    val commandedThrottle: Int,
    val actualThrottle: Int,
    val failsafe: Boolean,
    val source: String,
    val rssi: Int,
) {
    val latencyMs: Long
        get() = (System.currentTimeMillis() - echoTimestampMs).coerceAtLeast(0L)
}
