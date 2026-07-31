package com.kartik.mcqueencontroller

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/** Reliable acknowledged start/stop control for the laptop dataset recorder. */
class DatasetControlClient {
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()

    fun start(host: String, callback: (Boolean, String) -> Unit) = request(host, "start", callback)
    fun stop(host: String, callback: (Boolean, String) -> Unit) = request(host, "stop", callback)

    fun close() {
        executor.shutdownNow()
    }

    private fun request(host: String, action: String, callback: (Boolean, String) -> Unit) {
        val cleanHost = host.trim()
        if (cleanHost.isBlank()) {
            callback(false, "missing host IP")
            return
        }
        executor.execute {
            var connection: HttpURLConnection? = null
            try {
                connection = (URL("http://$cleanHost:8080/api/log/$action").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 1500
                    readTimeout = 2500
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json")
                }
                connection.outputStream.use { it.write("{}".toByteArray(Charsets.UTF_8)) }
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
                if (code !in 200..299) {
                    callback(false, "HTTP $code ${body.take(120)}")
                } else {
                    val json = runCatching { JSONObject(body) }.getOrNull()
                    callback(json?.optBoolean("ok", true) ?: true, json?.optString("detail", "ok") ?: "ok")
                }
            } catch (error: Exception) {
                callback(false, error.message ?: error.javaClass.simpleName)
            } finally {
                connection?.disconnect()
            }
        }
    }
}
