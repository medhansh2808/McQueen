package com.kartik.mcqueencontroller

import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException
import java.util.concurrent.Executors

/**
 * Finds Kachow devices on the current LAN using a tiny UDP broadcast protocol.
 * Both the ESP32 and the laptop camera server answer the same discovery request.
 */
class DiscoveryClient {
    data class Result(
        val carIp: String? = null,
        val carPort: Int = Protocol.DEFAULT_PORT,
        val hostIp: String? = null,
        val hostHttpPort: Int = 8080,
        val hostTelemetryPort: Int = 5008,
    )

    private val executor = Executors.newSingleThreadExecutor()

    fun discover(callback: (Result) -> Unit) {
        executor.execute {
            var carIp: String? = null
            var carPort = Protocol.DEFAULT_PORT
            var hostIp: String? = null
            var hostHttpPort = 8080
            var hostTelemetryPort = 5008

            runCatching {
                DatagramSocket().use { socket ->
                    socket.broadcast = true
                    socket.soTimeout = 150

                    val request = "KACHOW_DISCOVER_V1\n".toByteArray(Charsets.US_ASCII)
                    val targets = broadcastAddresses().toMutableSet().apply {
                        add(InetAddress.getByName("255.255.255.255"))
                        add(InetAddress.getByName("192.168.4.255"))
                    }

                    // Two rounds help when Wi-Fi has just associated or Android initially drops a broadcast.
                    repeat(2) {
                        targets.forEach { address ->
                            runCatching {
                                socket.send(
                                    DatagramPacket(
                                        request,
                                        request.size,
                                        address,
                                        DISCOVERY_PORT,
                                    ),
                                )
                            }
                        }
                        Thread.sleep(80)
                    }

                    val deadline = System.currentTimeMillis() + 1_300L
                    val buffer = ByteArray(512)
                    while (System.currentTimeMillis() < deadline) {
                        val packet = DatagramPacket(buffer, buffer.size)
                        try {
                            socket.receive(packet)
                        } catch (_: SocketTimeoutException) {
                            continue
                        }

                        val text = String(packet.data, packet.offset, packet.length, Charsets.US_ASCII)
                            .trim()
                        val fields = text.split(',')
                        when (fields.firstOrNull()) {
                            "KACHOW_CAR_V1" -> {
                                carIp = fields.getOrNull(1)?.takeIf { it.isNotBlank() }
                                    ?: packet.address.hostAddress
                                carPort = fields.getOrNull(2)?.toIntOrNull()
                                    ?: Protocol.DEFAULT_PORT
                            }

                            "KACHOW_HOST_V1" -> {
                                hostIp = fields.getOrNull(1)?.takeIf { it.isNotBlank() }
                                    ?: packet.address.hostAddress
                                hostHttpPort = fields.getOrNull(2)?.toIntOrNull() ?: 8080
                                hostTelemetryPort = fields.getOrNull(3)?.toIntOrNull() ?: 5008
                            }
                        }

                        if (carIp != null && hostIp != null) break
                    }
                }
            }

            callback(
                Result(
                    carIp = carIp,
                    carPort = carPort,
                    hostIp = hostIp,
                    hostHttpPort = hostHttpPort,
                    hostTelemetryPort = hostTelemetryPort,
                ),
            )
        }
    }

    fun close() {
        executor.shutdownNow()
    }

    private fun broadcastAddresses(): Set<InetAddress> {
        val result = linkedSetOf<InetAddress>()
        runCatching {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val network = interfaces.nextElement()
                if (!network.isUp || network.isLoopback) continue
                network.interfaceAddresses.forEach { interfaceAddress ->
                    interfaceAddress.broadcast?.let(result::add)
                }
            }
        }
        return result
    }

    companion object {
        const val DISCOVERY_PORT = 5006
    }
}
