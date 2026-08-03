package com.kartik.mcqueencontroller

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress

/** Mirrors final driver commands to the laptop on UDP 5008. */
class TelemetryMirror {
    companion object { const val DEFAULT_PORT = 5008 }

    private val lock = Any()
    private var socket: DatagramSocket? = null
    private var target: InetSocketAddress? = null

    fun configure(ip: String, port: Int = DEFAULT_PORT): Boolean = synchronized(lock) {
        val address = runCatching { InetAddress.getByName(ip.trim()) }.getOrNull() ?: return false
        if (socket == null || socket?.isClosed == true) socket = DatagramSocket()
        target = InetSocketAddress(address, port)
        true
    }

    fun sendTelemetry(timestampMs: Long, sequence: Long, throttleSent: Int, servoSent: Int) {
        val payload = JSONObject()
            .put("type", "telemetry")
            .put("timestamp", timestampMs)
            .put("sequence", sequence)
            .put("throttle_sent", throttleSent)
            .put("servo_sent", servoSent)
        send(payload)
    }


    fun close() = synchronized(lock) {
        socket?.close()
        socket = null
        target = null
    }

    private fun send(json: JSONObject) {
        synchronized(lock) {
            val localSocket = socket ?: return@synchronized
            val localTarget = target ?: return@synchronized
            runCatching {
                val bytes = (json.toString() + "\n").toByteArray(Charsets.UTF_8)
                localSocket.send(DatagramPacket(bytes, bytes.size, localTarget))
            }
        }
    }
}
