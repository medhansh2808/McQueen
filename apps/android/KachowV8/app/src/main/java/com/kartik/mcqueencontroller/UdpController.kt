package com.kartik.mcqueencontroller

import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.SocketTimeoutException
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.abs
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sign

class UdpController(
    private val listener: Listener,
) {
    interface Listener {
        fun onStatus(status: StatusPacket)
        fun onCommandSent(timestampMs: Long, sequence: Long, steering: Int, throttle: Int)
        fun onLinkChanged(connected: Boolean, detail: String)
        fun onNeutralisingChanged(active: Boolean)
        fun onError(message: String)
    }

    private val stateLock = Any()
    private val sendLock = Any()
    private val running = AtomicBoolean(false)

    private var socket: DatagramSocket? = null
    private var remoteAddress: InetSocketAddress? = null
    private var scheduler: ScheduledExecutorService? = null
    private var receiverExecutor = Executors.newSingleThreadExecutor()

    private var sessionId = Protocol.newSessionId()
    private var sequence = 0L
    private var takeoverPacketsRemaining = 0

    private var rawSteeringUnit = 0f
    private var rawThrottleUnit = 0f
    private var speedPercent = 75
    private var armed = false
    private var brakeHeld = false

    private var currentThrottleCommand = 0
    private var activeDirection = 0
    private var pendingDirection = 0
    private var neutralUntilMs = 0L
    private var neutralising = false

    @Volatile private var lastStatusAtMs = 0L
    @Volatile private var linkReportedConnected = false
    @Volatile private var lastNeutralisingReported = false

    fun start(ipAddress: String, port: Int = Protocol.DEFAULT_PORT) {
        stop(sendEmergency = false)

        val address = runCatching { InetAddress.getByName(ipAddress.trim()) }
            .getOrElse {
                listener.onError("Invalid ESP32 IP address")
                return
            }

        val newSocket = runCatching {
            DatagramSocket().apply {
                soTimeout = 120
                reuseAddress = true
            }
        }.getOrElse {
            listener.onError("Could not open UDP socket: ${it.message}")
            return
        }

        synchronized(stateLock) {
            socket = newSocket
            remoteAddress = InetSocketAddress(address, port)
            sessionId = Protocol.newSessionId()
            sequence = 0L
            takeoverPacketsRemaining = 12
            resetControlStateLocked()
            armed = false
            brakeHeld = false
            lastStatusAtMs = 0L
            linkReportedConnected = false
        }

        running.set(true)
        scheduler = Executors.newSingleThreadScheduledExecutor()
        receiverExecutor = Executors.newSingleThreadExecutor()
        receiverExecutor.execute(::receiveLoop)
        scheduler?.scheduleAtFixedRate(::sendLoop, 0L, 16L, TimeUnit.MILLISECONDS)
        listener.onLinkChanged(false, "Taking control…")
    }

    fun takeControl() {
        if (!running.get()) return
        synchronized(stateLock) {
            sessionId = Protocol.newSessionId()
            sequence = 0L
            takeoverPacketsRemaining = 12
            resetControlStateLocked()
            armed = false
            brakeHeld = false
            lastStatusAtMs = 0L
            linkReportedConnected = false
        }
        reportNeutralising(false)
        listener.onLinkChanged(false, "Taking control…")
    }

    fun setControl(steering: Float, throttle: Float) {
        synchronized(stateLock) {
            rawSteeringUnit = steering.coerceIn(-1f, 1f)
            rawThrottleUnit = throttle.coerceIn(-1f, 1f)
        }
    }

    fun setJoystick(steering: Float, throttle: Float) = setControl(steering, throttle)

    fun centreControls() {
        synchronized(stateLock) {
            rawSteeringUnit = 0f
            rawThrottleUnit = 0f
        }
    }

    fun centreJoystick() = centreControls()

    fun setSpeedPercent(value: Int) {
        synchronized(stateLock) { speedPercent = value.coerceIn(10, 100) }
    }

    fun setArmed(value: Boolean) {
        synchronized(stateLock) {
            armed = value
            if (!value) resetControlStateLocked()
        }
        if (!value) reportNeutralising(false)
    }

    fun isArmed(): Boolean = synchronized(stateLock) { armed }

    fun setBrake(held: Boolean) {
        synchronized(stateLock) {
            brakeHeld = held
            if (held) {
                currentThrottleCommand = 0
                activeDirection = 0
                pendingDirection = 0
                neutralUntilMs = 0L
                neutralising = false
            }
        }
        if (held) reportNeutralising(false)
    }

    fun isBrakeHeld(): Boolean = synchronized(stateLock) { brakeHeld }

    fun emergencyStop() {
        synchronized(stateLock) {
            armed = false
            resetControlStateLocked()
        }
        reportNeutralising(false)
        scheduler?.execute { sendEmergencyBurst(5) }
    }

    fun releaseControl() = stop(sendEmergency = true)

    fun isRunning(): Boolean = running.get()

    fun isLinkAlive(): Boolean =
        running.get() && System.currentTimeMillis() - lastStatusAtMs <= 500L

    fun stop(sendEmergency: Boolean = true) {
        if (sendEmergency && running.get()) sendEmergencyBurst(4)

        running.set(false)
        scheduler?.shutdownNow()
        scheduler = null
        runCatching { socket?.close() }
        socket = null
        runCatching { receiverExecutor.shutdownNow() }

        synchronized(stateLock) {
            armed = false
            brakeHeld = false
            resetControlStateLocked()
        }
        reportNeutralising(false)

        if (linkReportedConnected) {
            linkReportedConnected = false
            listener.onLinkChanged(false, "Released")
        }
    }

    private fun resetControlStateLocked() {
        rawSteeringUnit = 0f
        rawThrottleUnit = 0f
        currentThrottleCommand = 0
        activeDirection = 0
        pendingDirection = 0
        neutralUntilMs = 0L
        neutralising = false
    }

    private fun nextSequence(): Long = synchronized(stateLock) {
        sequence += 1L
        sequence
    }

    private fun sendLoop() {
        if (!running.get()) return

        val now = System.currentTimeMillis()
        val localSession: String
        val localTakeoverRemaining: Int
        val steeringUnit: Float
        val throttleUnit: Float
        val localSpeed: Int
        val motorEnabled: Boolean
        val localBrake: Boolean

        synchronized(stateLock) {
            localSession = sessionId
            localTakeoverRemaining = takeoverPacketsRemaining
            steeringUnit = rawSteeringUnit
            throttleUnit = rawThrottleUnit
            localSpeed = speedPercent
            motorEnabled = armed
            localBrake = brakeHeld
            if (takeoverPacketsRemaining > 0) takeoverPacketsRemaining -= 1
        }

        if (localTakeoverRemaining > 0) {
            val seq = nextSequence()
            val packet = if (localTakeoverRemaining % 2 == 0) {
                Protocol.emergency(localSession, seq, now)
            } else {
                Protocol.hello(localSession, seq, now)
            }
            sendRaw(packet)
            return
        }

        val requestedThrottle = if (motorEnabled && !localBrake) {
            (throttleUnit * Protocol.MAX_THROTTLE_COMMAND * localSpeed / 100f).roundToInt()
        } else {
            0
        }

        val shapedSteering = if (motorEnabled) {
            shapeSteering(steeringUnit, abs(requestedThrottle) / Protocol.MAX_THROTTLE_COMMAND.toFloat())
        } else {
            0
        }

        val finalThrottle = synchronized(stateLock) {
            applyDirectionProtectionLocked(requestedThrottle, now)
        }.coerceIn(-Protocol.MAX_THROTTLE_COMMAND, Protocol.MAX_THROTTLE_COMMAND)

        val safeSteering = shapedSteering.coerceIn(-Protocol.MAX_STEERING, Protocol.MAX_STEERING)
        val seq = nextSequence()
        sendRaw(
            Protocol.command(
                session = localSession,
                sequence = seq,
                timestampMs = now,
                steering = safeSteering,
                throttle = finalThrottle,
                motorEnabled = motorEnabled,
            ),
        )
        listener.onCommandSent(now, seq, safeSteering, finalThrottle)
        reportNeutralising(synchronized(stateLock) { neutralising })

        val alive = now - lastStatusAtMs <= 500L
        if (alive != linkReportedConnected) {
            linkReportedConnected = alive
            listener.onLinkChanged(alive, if (alive) "Controller has control" else "No status reply")
        }
    }

    private fun shapeSteering(raw: Float, speedFraction: Float): Int {
        val magnitude = abs(raw).coerceIn(0f, 1f)
        if (magnitude == 0f) return 0
        // Mild exponential at low speed, progressively gentler near centre at high speed.
        // Endpoint stays exactly ±1000, so full steering remains available.
        val exponent = 1.35f + 0.65f * speedFraction.coerceIn(0f, 1f)
        val shaped = magnitude.pow(exponent)
        return (sign(raw) * shaped * Protocol.MAX_STEERING).roundToInt()
    }

    private fun applyDirectionProtectionLocked(target: Int, nowMs: Long): Int {
        val clamped = target.coerceIn(-Protocol.MAX_THROTTLE_COMMAND, Protocol.MAX_THROTTLE_COMMAND)
        if (clamped == 0 || abs(clamped) < 5) {
            pendingDirection = 0
            neutralUntilMs = 0L
            neutralising = false
            currentThrottleCommand = moveTowards(currentThrottleCommand, 0, RELEASE_STEP)
            if (currentThrottleCommand == 0) activeDirection = 0
            return currentThrottleCommand
        }

        val targetDirection = if (clamped > 0) 1 else -1

        if (pendingDirection != 0 && targetDirection == activeDirection) {
            // Driver changed their mind before the reversal completed.
            pendingDirection = 0
            neutralUntilMs = 0L
            neutralising = false
        }

        if (pendingDirection != 0) {
            neutralising = true
            if (currentThrottleCommand != 0) {
                currentThrottleCommand = moveTowards(currentThrottleCommand, 0, REVERSAL_DECEL_STEP)
                return currentThrottleCommand
            }
            if (neutralUntilMs == 0L) neutralUntilMs = nowMs + NEUTRAL_HOLD_MS
            if (nowMs < neutralUntilMs) return 0

            activeDirection = pendingDirection
            pendingDirection = 0
            neutralUntilMs = 0L
            neutralising = false
            currentThrottleCommand = moveTowards(0, clamped, ACCEL_STEP)
            return currentThrottleCommand
        }

        if (activeDirection != 0 && targetDirection != activeDirection) {
            pendingDirection = targetDirection
            neutralUntilMs = 0L
            neutralising = true
            currentThrottleCommand = moveTowards(currentThrottleCommand, 0, REVERSAL_DECEL_STEP)
            return currentThrottleCommand
        }

        activeDirection = targetDirection
        neutralising = false
        currentThrottleCommand = moveTowards(currentThrottleCommand, clamped, ACCEL_STEP)
        return currentThrottleCommand
    }

    private fun moveTowards(current: Int, target: Int, step: Int): Int = when {
        current < target -> minOf(current + step, target)
        current > target -> maxOf(current - step, target)
        else -> current
    }

    private fun reportNeutralising(active: Boolean) {
        if (active == lastNeutralisingReported) return
        lastNeutralisingReported = active
        listener.onNeutralisingChanged(active)
    }

    private fun sendEmergencyBurst(count: Int) {
        val localSocket = socket ?: return
        val target = remoteAddress ?: return
        val localSession = synchronized(stateLock) { sessionId }

        repeat(count) {
            val sequenceNumber = nextSequence()
            val raw = Protocol.emergency(localSession, sequenceNumber, System.currentTimeMillis())
            synchronized(sendLock) {
                runCatching {
                    val bytes = raw.toByteArray(Charsets.US_ASCII)
                    localSocket.send(DatagramPacket(bytes, bytes.size, target))
                }
            }
            if (it < count - 1) Thread.sleep(15L)
        }
    }

    private fun sendRaw(raw: String) {
        val localSocket = socket ?: return
        val target = remoteAddress ?: return
        synchronized(sendLock) {
            runCatching {
                val bytes = raw.toByteArray(Charsets.US_ASCII)
                localSocket.send(DatagramPacket(bytes, bytes.size, target))
            }.onFailure { listener.onError("UDP send failed: ${it.message}") }
        }
    }

    private fun receiveLoop() {
        val buffer = ByteArray(512)
        while (running.get()) {
            val localSocket = socket ?: break
            val packet = DatagramPacket(buffer, buffer.size)
            try {
                localSocket.receive(packet)
                val raw = String(packet.data, packet.offset, packet.length, Charsets.US_ASCII)
                val status = Protocol.parseStatus(raw) ?: continue
                val currentSession = synchronized(stateLock) { sessionId }
                if (status.session != currentSession) continue
                lastStatusAtMs = System.currentTimeMillis()
                listener.onStatus(status)
            } catch (_: SocketTimeoutException) {
                // Expected so the loop can check the running flag.
            } catch (error: Exception) {
                if (running.get()) listener.onError("UDP receive failed: ${error.message}")
            }
        }
    }

    companion object {
        private const val ACCEL_STEP = 100
        private const val RELEASE_STEP = 150
        private const val REVERSAL_DECEL_STEP = 150
        private const val NEUTRAL_HOLD_MS = 200L
    }
}
