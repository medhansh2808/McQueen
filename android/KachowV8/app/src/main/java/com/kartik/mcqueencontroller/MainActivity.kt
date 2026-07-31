package com.kartik.mcqueencontroller

import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.text.InputType
import android.text.TextUtils
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Space
import android.widget.TableLayout
import android.widget.TableRow
import android.widget.TextView
import android.widget.Toast
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

class MainActivity : Activity(), UdpController.Listener {

    private lateinit var controller: UdpController
    private lateinit var joystick: JoystickView
    private lateinit var rcSliders: DualRcSliderView
    private lateinit var controlHost: FrameLayout
    private lateinit var logger: CsvLogger
    private lateinit var mirror: TelemetryMirror
    private lateinit var datasetClient: DatasetControlClient
    private lateinit var discoveryClient: DiscoveryClient

    private lateinit var espIpInput: EditText
    private lateinit var hostIpInput: EditText
    private lateinit var connectionText: TextView
    private lateinit var statusInfoText: TextView
    private lateinit var neutralText: TextView
    private lateinit var armButton: Button
    private lateinit var takeControlButton: Button
    private lateinit var logButton: Button
    private lateinit var brakeButton: Button
    private lateinit var cameraButton: Button
    private lateinit var joystickModeButton: Button
    private lateinit var sliderModeButton: Button
    private lateinit var servoBar: TelemetryBarView
    private lateinit var throttleBar: TelemetryBarView
    private lateinit var speedSlider: VerticalSpeedSlider
    private lateinit var cameraWebView: WebView
    private lateinit var cameraPlaceholder: TextView

    private var speedPercent = 75
    private var brakeHeld = false
    private var logStartedAtMs = 0L
    private var cameraEnabled = false
    private var logRequestInFlight = false
    private var controlMode = ControlMode.JOYSTICK

    private val uiHandler = Handler(Looper.getMainLooper())
    private val preferences by lazy {
        getSharedPreferences("kachow_controller", Context.MODE_PRIVATE)
    }

    private val logTicker = object : Runnable {
        override fun run() {
            if (!logger.isLogging) return
            val seconds = ((System.currentTimeMillis() - logStartedAtMs) / 1000L).coerceAtLeast(0L)
            logButton.text = "STOP\n${seconds / 60}:${(seconds % 60).toString().padStart(2, '0')}"
            uiHandler.postDelayed(this, 1000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
                View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            )

        controller = UdpController(this)
        logger = CsvLogger(this)
        mirror = TelemetryMirror()
        datasetClient = DatasetControlClient()
        discoveryClient = DiscoveryClient()
        controlMode = runCatching {
            ControlMode.valueOf(preferences.getString("control_mode", ControlMode.JOYSTICK.name)!!)
        }.getOrDefault(ControlMode.JOYSTICK)

        setContentView(buildInterface())
        showControlMode(controlMode, persist = false)
        uiHandler.postDelayed({ runDiscovery(showToast = false) }, 650L)
    }

    override fun onPause() {
        brakeHeld = false
        controller.setBrake(false)
        controller.releaseControl()
        resetControls()
        servoBar.setValue(0)
        throttleBar.setValue(0)
        stopLogging(showToast = false)
        updateTakeControlButton()
        updateArmButton(forceDisarmed = true)
        super.onPause()
    }

    override fun onDestroy() {
        stopLogging(showToast = false)
        controller.stop(sendEmergency = true)
        mirror.close()
        datasetClient.close()
        discoveryClient.close()
        cameraWebView.destroy()
        super.onDestroy()
    }

    override fun onStatus(status: StatusPacket) {
        runOnUiThread {
            connectionText.text = "CONNECTED  •  ${status.latencyMs} ms"
            connectionText.setTextColor(GREEN)
            statusInfoText.text = "${status.source}  •  ${if (status.failsafe) "FAILSAFE" else "LIVE"}"
            statusInfoText.setTextColor(if (status.failsafe) AMBER else Color.argb(210, 255, 255, 255))
        }
    }

    override fun onCommandSent(timestampMs: Long, sequence: Long, steering: Int, throttle: Int) {
        if (logger.isLogging) logger.append(timestampMs, sequence, throttle, steering)
        mirror.sendTelemetry(timestampMs, sequence, throttle, steering)
        runOnUiThread {
            throttleBar.setValue(throttle)
            servoBar.setValue(steering)
        }
    }

    override fun onLinkChanged(connected: Boolean, detail: String) {
        runOnUiThread {
            connectionText.text = if (connected) "CONNECTED  •  $detail" else "OFFLINE  •  $detail"
            connectionText.setTextColor(if (connected) GREEN else RED)
            updateTakeControlButton()
        }
    }

    override fun onNeutralisingChanged(active: Boolean) {
        runOnUiThread {
            neutralText.visibility = if (active) View.VISIBLE else View.INVISIBLE
            if (active) neutralText.text = "NEUTRALISING  •  200 ms DIRECTION GUARD"
        }
    }

    override fun onError(message: String) {
        runOnUiThread { toast(message) }
    }

    private fun buildInterface(): View {
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }

        cameraWebView = WebView(this).apply {
            setBackgroundColor(Color.BLACK)
            webViewClient = WebViewClient()
            webChromeClient = WebChromeClient()
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.cacheMode = WebSettings.LOAD_NO_CACHE
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            visibility = View.GONE
        }
        root.addView(cameraWebView, FrameLayout.LayoutParams(-1, -1))

        cameraPlaceholder = TextView(this).apply {
            text = "OAK-D CAMERA OFF\nTAP CAM TO CONNECT"
            textSize = 17f
            letterSpacing = 0.18f
            setTextColor(Color.argb(68, 255, 255, 255))
            gravity = Gravity.CENTER
        }
        root.addView(cameraPlaceholder, FrameLayout.LayoutParams(-1, -1))

        root.addView(View(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(Color.argb(190, 0, 0, 0), Color.argb(18, 0, 0, 0), Color.argb(150, 0, 0, 0)),
            )
        }, FrameLayout.LayoutParams(-1, -1))

        val overlay = FrameLayout(this)
        root.addView(overlay, FrameLayout.LayoutParams(-1, -1))
        overlay.addView(buildTopBar())
        overlay.addView(buildBody())
        return root
    }

    private fun buildTopBar(): View {
        val topBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(9), dp(5), dp(9), dp(5))
            background = panelBackground(alpha = 205)
            layoutParams = FrameLayout.LayoutParams(-1, dp(70), Gravity.TOP).apply {
                setMargins(dp(9), dp(7), dp(9), 0)
            }
        }

        topBar.addView(TextView(this).apply {
            text = "KACHOW"
            textSize = 20f
            letterSpacing = 0.11f
            gravity = Gravity.CENTER_VERTICAL
            setTypeface(Typeface.DEFAULT, Typeface.BOLD_ITALIC)
            setTextColor(Color.WHITE)
        }, LinearLayout.LayoutParams(dp(122), -1))

        val status = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
        }
        connectionText = TextView(this).apply {
            text = "OFFLINE"
            textSize = 11.5f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(RED)
            maxLines = 1
        }
        statusInfoText = TextView(this).apply {
            text = "AUTO DISCOVERY READY"
            textSize = 9.5f
            letterSpacing = 0.04f
            setTextColor(Color.argb(185, 255, 255, 255))
            maxLines = 1
        }
        status.addView(connectionText)
        status.addView(statusInfoText)
        topBar.addView(status, LinearLayout.LayoutParams(0, -1, 1f))

        val modeGroup = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            background = compactPanelBackground()
            setPadding(dp(3), dp(3), dp(3), dp(3))
        }
        joystickModeButton = modeButton("JOYSTICK") { requestMode(ControlMode.JOYSTICK) }
        sliderModeButton = modeButton("RC SLIDERS") { requestMode(ControlMode.RC_SLIDERS) }
        modeGroup.addView(joystickModeButton, LinearLayout.LayoutParams(0, dp(40), 1f))
        modeGroup.addView(sliderModeButton, LinearLayout.LayoutParams(0, dp(40), 1f))
        topBar.addView(modeGroup, LinearLayout.LayoutParams(dp(180), dp(46)).apply {
            marginStart = dp(6)
            marginEnd = dp(7)
        })

        takeControlButton = actionButton("TAKE") { toggleTakeControl() }
        armButton = actionButton("ARM") { toggleArm() }
        cameraButton = actionButton("CAM") { loadCameraFeed() }
        logButton = actionButton("LOG") { if (logger.isLogging) stopLogging(true) else startLogging() }
        val settingsButton = actionButton("SET") { showSettingsDialog() }

        listOf(takeControlButton, armButton, cameraButton, logButton, settingsButton).forEach {
            topBar.addView(it, LinearLayout.LayoutParams(dp(57), dp(43)).apply { marginStart = dp(4) })
        }
        return topBar
    }

    private fun buildBody(): View {
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = FrameLayout.LayoutParams(-1, -1).apply {
                topMargin = dp(83)
                bottomMargin = dp(12)
                leftMargin = dp(12)
                rightMargin = dp(12)
            }
        }

        controlHost = FrameLayout(this).apply {
            background = panelBackground(105)
            layoutParams = LinearLayout.LayoutParams(0, -1, 1.48f).apply { marginEnd = dp(10) }
        }
        joystick = JoystickView(this).apply {
            listener = JoystickView.Listener { steering, throttle -> controller.setControl(steering, throttle) }
        }
        rcSliders = DualRcSliderView(this).apply {
            listener = DualRcSliderView.Listener { steering, throttle -> controller.setControl(steering, throttle) }
        }
        controlHost.addView(joystick, FrameLayout.LayoutParams(-1, -1))
        controlHost.addView(rcSliders, FrameLayout.LayoutParams(-1, -1))
        body.addView(controlHost)

        val telemetryPanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.BOTTOM
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = panelBackground(180)
            layoutParams = LinearLayout.LayoutParams(0, -1, 0.78f).apply { marginEnd = dp(10) }
        }
        telemetryPanel.addView(TextView(this).apply {
            text = "LIVE COMMANDS"
            textSize = 12f
            letterSpacing = 0.11f
            gravity = Gravity.CENTER
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(Color.WHITE)
        })
        telemetryPanel.addView(TextView(this).apply {
            text = "Independent axes • speed-sensitive steering"
            textSize = 9.5f
            gravity = Gravity.CENTER
            setTextColor(Color.argb(165, 255, 255, 255))
        })
        telemetryPanel.addView(Space(this), LinearLayout.LayoutParams(1, 0, 1f))

        throttleBar = TelemetryBarView(this).apply {
            mode = TelemetryBarView.Mode.THROTTLE
            setValue(0)
        }
        servoBar = TelemetryBarView(this).apply {
            mode = TelemetryBarView.Mode.SERVO
            setValue(0)
        }
        telemetryPanel.addView(throttleBar, LinearLayout.LayoutParams(-1, dp(80)))
        telemetryPanel.addView(servoBar, LinearLayout.LayoutParams(-1, dp(80)))

        neutralText = TextView(this).apply {
            text = "NEUTRALISING  •  200 ms DIRECTION GUARD"
            textSize = 10f
            gravity = Gravity.CENTER
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(AMBER)
            visibility = View.INVISIBLE
            setPadding(0, dp(5), 0, dp(2))
        }
        telemetryPanel.addView(neutralText)
        body.addView(telemetryPanel)

        val right = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(dp(126), -1)
        }
        val speedPanel = FrameLayout(this).apply {
            background = panelBackground(180)
            layoutParams = LinearLayout.LayoutParams(-1, 0, 1f).apply { bottomMargin = dp(9) }
        }
        speedSlider = VerticalSpeedSlider(this).apply {
            setPercent(75, notify = false)
            listener = VerticalSpeedSlider.Listener { percent ->
                speedPercent = percent
                controller.setSpeedPercent(percent)
            }
        }
        speedPanel.addView(speedSlider, FrameLayout.LayoutParams(-1, -1))
        right.addView(speedPanel)

        brakeButton = actionButton("HOLD\nBRAKE", AMBER) {}
        brakeButton.textSize = 12f
        brakeButton.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    brakeHeld = true
                    controller.setBrake(true)
                    view.isPressed = true
                    vibrate(45)
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    brakeHeld = false
                    controller.setBrake(false)
                    view.isPressed = false
                    view.performClick()
                    vibrate(18)
                    true
                }
                else -> true
            }
        }
        right.addView(brakeButton, LinearLayout.LayoutParams(-1, dp(90)))
        body.addView(right)
        return body
    }

    private fun toggleTakeControl() {
        if (controller.isRunning()) {
            controller.releaseControl()
            resetControls()
            servoBar.setValue(0)
            throttleBar.setValue(0)
            updateArmButton(forceDisarmed = true)
            updateTakeControlButton()
            vibrate(30)
            return
        }
        val ip = preferences.getString("esp_ip", "192.168.4.1")?.trim().orEmpty()
        if (ip.isBlank()) {
            toast("Open SET and enter the car IP")
            return
        }
        controller.start(ip)
        controller.setSpeedPercent(speedPercent)
        resetControls()
        updateArmButton(forceDisarmed = true)
        updateTakeControlButton()
        vibrate(40)
    }

    private fun toggleArm() {
        if (!controller.isLinkAlive()) {
            toast("Connect to the car first")
            return
        }
        controller.setArmed(!controller.isArmed())
        if (!controller.isArmed()) resetControls()
        updateArmButton()
        vibrate(38)
    }

    private fun requestMode(mode: ControlMode) {
        if (controller.isArmed()) {
            toast("DISARM before changing control mode")
            vibrate(60)
            return
        }
        showControlMode(mode, persist = true)
    }

    private fun showControlMode(mode: ControlMode, persist: Boolean) {
        controlMode = mode
        resetControls()
        joystick.visibility = if (mode == ControlMode.JOYSTICK) View.VISIBLE else View.GONE
        rcSliders.visibility = if (mode == ControlMode.RC_SLIDERS) View.VISIBLE else View.GONE
        joystickModeButton.setTextColor(if (mode == ControlMode.JOYSTICK) Color.WHITE else MUTED)
        sliderModeButton.setTextColor(if (mode == ControlMode.RC_SLIDERS) Color.WHITE else MUTED)
        joystickModeButton.background = modeButtonBackground(mode == ControlMode.JOYSTICK)
        sliderModeButton.background = modeButtonBackground(mode == ControlMode.RC_SLIDERS)
        if (persist) preferences.edit().putString("control_mode", mode.name).apply()
    }

    private fun resetControls() {
        if (::joystick.isInitialized) joystick.reset()
        if (::rcSliders.isInitialized) rcSliders.reset()
        controller.centreControls()
    }

    private fun runDiscovery(showToast: Boolean) {
        if (showToast) toast("Scanning for car and laptop host…")
        connectionText.text = "DISCOVERING…"
        connectionText.setTextColor(AMBER)

        discoveryClient.discover { result ->
            runOnUiThread {
                val found = mutableListOf<String>()
                result.carIp?.let { ip ->
                    preferences.edit().putString("esp_ip", ip).apply()
                    if (::espIpInput.isInitialized) espIpInput.setText(ip)
                    found += "car $ip"
                }
                result.hostIp?.let { ip ->
                    preferences.edit().putString("host_ip", ip).apply()
                    if (::hostIpInput.isInitialized) hostIpInput.setText(ip)
                    mirror.configure(ip)
                    found += "host $ip"
                }
                if (found.isEmpty()) {
                    connectionText.text = "OFFLINE  •  discovery found nothing"
                    connectionText.setTextColor(RED)
                    if (showToast) toast("Nothing found. Keep phone, laptop and car on KACHOW-CAR.", long = true)
                } else {
                    connectionText.text = "FOUND  •  ${found.joinToString("  •  ")}"
                    connectionText.setTextColor(GREEN)
                    if (showToast) toast("Discovered ${found.joinToString(" and ")}")
                }
            }
        }
    }

    private fun loadCameraFeed() {
        if (cameraEnabled) {
            cameraEnabled = false
            cameraWebView.stopLoading()
            cameraWebView.loadUrl("about:blank")
            cameraWebView.visibility = View.GONE
            cameraPlaceholder.visibility = View.VISIBLE
            cameraButton.setTextColor(Color.WHITE)
            toast("Camera feed off")
            return
        }

        val host = preferences.getString("host_ip", "")?.trim().orEmpty()
        if (host.isBlank()) {
            toast("Run AUTO discovery or enter HOST in SET")
            return
        }
        if (!mirror.configure(host)) {
            toast("Invalid laptop IP")
            return
        }
        cameraEnabled = true
        cameraWebView.visibility = View.VISIBLE
        cameraPlaceholder.visibility = View.GONE
        cameraButton.setTextColor(RED_ACCENT)
        cameraWebView.loadUrl("http://$host:8080/")
        toast("OAK-D feed connecting…")
    }

    private fun startLogging() {
        if (logRequestInFlight) return
        val host = preferences.getString("host_ip", "")?.trim().orEmpty()
        if (host.isBlank() || !mirror.configure(host)) {
            toast("Run camera server and set the HOST IP")
            return
        }

        logRequestInFlight = true
        logButton.text = "STARTING"
        datasetClient.start(host) { ok, detail ->
            runOnUiThread {
                logRequestInFlight = false
                if (!ok) {
                    logButton.text = "LOG"
                    toast("Laptop logger did not start: $detail", long = true)
                    return@runOnUiThread
                }
                val file = logger.start()
                logStartedAtMs = System.currentTimeMillis()
                logButton.setTextColor(RED_ACCENT)
                logButton.text = "STOP\n0:00"
                uiHandler.removeCallbacks(logTicker)
                uiHandler.post(logTicker)
                vibrate(48)
                toast("Dataset recording started • ${file.name}")
            }
        }
    }

    private fun stopLogging(showToast: Boolean) {
        if (logRequestInFlight || !logger.isLogging) return
        val host = preferences.getString("host_ip", "")?.trim().orEmpty()
        logRequestInFlight = true
        logButton.text = "STOPPING"
        datasetClient.stop(host) { ok, detail ->
            runOnUiThread {
                logRequestInFlight = false
                uiHandler.removeCallbacks(logTicker)
                val file = logger.stop()
                logButton.text = "LOG"
                logButton.setTextColor(Color.WHITE)
                vibrate(30)
                if (!ok) toast("Local log saved, but laptop stop failed: $detail", long = true)
                else if (showToast && file != null) toast("Dataset stopped • ${file.name}", long = true)
            }
        }
    }

    private fun showSettingsDialog() {
        val dialog = Dialog(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(14))
            background = panelBackground(245)
        }
        container.addView(TextView(this).apply {
            text = "KACHOW SETUP"
            textSize = 19f
            letterSpacing = 0.10f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        })
        container.addView(TextView(this).apply {
            text = "Automatic discovery is preferred. Manual addresses remain as fallback."
            textSize = 10f
            setTextColor(MUTED)
            gravity = Gravity.CENTER
            setPadding(0, dp(4), 0, dp(10))
        })

        espIpInput = settingsInput(preferences.getString("esp_ip", "192.168.4.1") ?: "192.168.4.1", "CAR IP")
        hostIpInput = settingsInput(preferences.getString("host_ip", "") ?: "", "LAPTOP / OAK HOST IP")
        container.addView(label("CAR IP"))
        container.addView(espIpInput)
        container.addView(label("HOST IP"))
        container.addView(hostIpInput)

        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row.addView(actionButton("AUTO") { runDiscovery(showToast = true) }, LinearLayout.LayoutParams(0, dp(44), 1f))
        row.addView(actionButton("TABLE") { showLogTable() }, LinearLayout.LayoutParams(0, dp(44), 1f).apply { marginStart = dp(6) })
        row.addView(actionButton("SAVE") {
            val car = espIpInput.text.toString().trim()
            val host = hostIpInput.text.toString().trim()
            preferences.edit().putString("esp_ip", car).putString("host_ip", host).apply()
            if (host.isNotBlank()) mirror.configure(host)
            dialog.dismiss()
            toast("Addresses saved")
        }, LinearLayout.LayoutParams(0, dp(44), 1f).apply { marginStart = dp(6) })
        container.addView(row, LinearLayout.LayoutParams(-1, dp(44)).apply { topMargin = dp(12) })

        dialog.setContentView(container)
        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)
        dialog.show()
        dialog.window?.setLayout((resources.displayMetrics.widthPixels * .70f).roundToInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    private fun showLogTable() {
        val dialog = Dialog(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
            background = panelBackground(245)
        }
        container.addView(TextView(this).apply {
            text = "KACHOW TRAINING LOG"
            textSize = 19f
            letterSpacing = 0.08f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        })
        container.addView(TextView(this).apply {
            text = logger.currentFile()?.absolutePath ?: "No session created yet"
            textSize = 9.5f
            setTextColor(MUTED)
            gravity = Gravity.CENTER
            setPadding(dp(6), dp(3), dp(6), dp(7))
            setSingleLine(true)
            ellipsize = TextUtils.TruncateAt.MIDDLE
        })
        val table = TableLayout(this).apply { isStretchAllColumns = false; addView(logHeaderRow()) }
        val rows = logger.rows()
        if (rows.isEmpty()) table.addView(TableRow(this).apply { addView(tableCell("No commands logged yet", 4f, false)) })
        else rows.forEach { table.addView(logDataRow(it)) }
        container.addView(ScrollView(this).apply { isFillViewport = true; addView(table) }, LinearLayout.LayoutParams(-1, 0, 1f))
        container.addView(actionButton("CLOSE") { dialog.dismiss() }, LinearLayout.LayoutParams(-1, dp(42)).apply { topMargin = dp(8) })
        dialog.setContentView(container)
        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)
        dialog.show()
        dialog.window?.setLayout((resources.displayMetrics.widthPixels * .96f).roundToInt(), (resources.displayMetrics.heightPixels * .88f).roundToInt())
    }

    private fun logHeaderRow() = TableRow(this).apply {
        addView(tableCell("TIME", 1.0f, true))
        addView(tableCell("THROTTLE\nSENT", 1.25f, true))
        addView(tableCell("SERVO\nSENT", 1.15f, true))
        addView(tableCell("SNAPSHOT", 1.0f, true))
    }

    private fun logDataRow(row: CsvLogger.Row) = TableRow(this).apply {
        addView(tableCell(formatTime(row.timestamp), 1.0f, false))
        addView(tableCell(row.throttleSent.toString(), 1.25f, false))
        addView(tableCell(row.servoSent.toString(), 1.15f, false))
        addView(tableCell(if (row.imagePath.isBlank()) "—" else row.imagePath, 1.0f, false))
    }

    private fun formatTime(ms: Long) = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(ms))

    private fun tableCell(value: String, weight: Float, header: Boolean) = TextView(this).apply {
        text = value
        textSize = if (header) 10f else 10.5f
        setTypeface(Typeface.DEFAULT, if (header) Typeface.BOLD else Typeface.NORMAL)
        setTextColor(if (header) RED_ACCENT else Color.WHITE)
        gravity = Gravity.CENTER
        maxLines = if (header) 2 else 1
        ellipsize = TextUtils.TruncateAt.END
        setPadding(dp(4), dp(7), dp(4), dp(7))
        background = GradientDrawable().apply {
            setColor(Color.argb(if (header) 70 else 32, 255, 255, 255))
            setStroke(dp(1), Color.argb(50, 255, 255, 255))
        }
        layoutParams = TableRow.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, weight)
    }

    private fun updateTakeControlButton() {
        takeControlButton.text = if (controller.isRunning()) "RELEASE" else "TAKE"
        takeControlButton.setTextColor(if (controller.isRunning()) RED_ACCENT else Color.WHITE)
    }

    private fun updateArmButton(forceDisarmed: Boolean = false) {
        if (forceDisarmed) controller.setArmed(false)
        armButton.text = if (controller.isArmed()) "DISARM" else "ARM"
        armButton.setTextColor(if (controller.isArmed()) GREEN else Color.WHITE)
    }

    private fun settingsInput(value: String, hintText: String) = EditText(this).apply {
        setText(value)
        hint = hintText
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        setTextColor(Color.WHITE)
        setHintTextColor(Color.argb(105, 255, 255, 255))
        textSize = 13f
        setSingleLine(true)
        setPadding(dp(10), 0, dp(10), 0)
        background = compactPanelBackground()
        layoutParams = LinearLayout.LayoutParams(-1, dp(42)).apply { bottomMargin = dp(8) }
    }

    private fun label(textValue: String) = TextView(this).apply {
        text = textValue
        textSize = 9.5f
        setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        setTextColor(MUTED)
        setPadding(dp(4), dp(4), 0, dp(3))
    }

    private fun actionButton(textValue: String, accent: Int = Color.WHITE, action: () -> Unit) = Button(this).apply {
        text = textValue
        setAllCaps(false)
        textSize = 9.5f
        minWidth = 0
        minimumWidth = 0
        minHeight = 0
        minimumHeight = 0
        maxLines = 2
        gravity = Gravity.CENTER
        setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        setTextColor(Color.WHITE)
        setPadding(dp(4), 0, dp(4), 0)
        backgroundTintList = ColorStateList.valueOf(Color.TRANSPARENT)
        background = buttonBackground(accent)
        setOnClickListener { action() }
    }

    private fun modeButton(textValue: String, action: () -> Unit) = Button(this).apply {
        text = textValue
        setAllCaps(false)
        textSize = 8.8f
        minWidth = 0
        minimumWidth = 0
        minHeight = 0
        minimumHeight = 0
        setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        setTextColor(MUTED)
        backgroundTintList = ColorStateList.valueOf(Color.TRANSPARENT)
        background = modeButtonBackground(false)
        setOnClickListener { action() }
    }

    private fun panelBackground(alpha: Int) = GradientDrawable().apply {
        setColor(Color.argb(alpha, 9, 11, 16))
        cornerRadius = dp(18).toFloat()
        setStroke(dp(1), Color.argb(86, 255, 255, 255))
    }

    private fun compactPanelBackground() = GradientDrawable().apply {
        setColor(Color.argb(165, 18, 20, 27))
        cornerRadius = dp(12).toFloat()
        setStroke(dp(1), Color.argb(84, 255, 255, 255))
    }

    private fun buttonBackground(accent: Int) = GradientDrawable().apply {
        setColor(Color.argb(72, Color.red(accent), Color.green(accent), Color.blue(accent)))
        cornerRadius = dp(13).toFloat()
        setStroke(dp(1), Color.argb(155, Color.red(accent), Color.green(accent), Color.blue(accent)))
    }

    private fun modeButtonBackground(selected: Boolean) = GradientDrawable().apply {
        setColor(if (selected) Color.rgb(180, 20, 25) else Color.TRANSPARENT)
        cornerRadius = dp(10).toFloat()
        if (selected) setStroke(dp(1), Color.rgb(245, 62, 62))
    }

    private fun vibrate(ms: Long) {
        val vibrator = getSystemService(Vibrator::class.java) ?: return
        if (vibrator.hasVibrator()) {
            vibrator.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
        }
    }

    private fun toast(text: String, long: Boolean = false) =
        Toast.makeText(this, text, if (long) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()

    private fun dp(value: Int) = (value * resources.displayMetrics.density).roundToInt()

    companion object {
        private val RED = Color.rgb(255, 105, 105)
        private val RED_ACCENT = Color.rgb(244, 60, 60)
        private val GREEN = Color.rgb(115, 242, 160)
        private val AMBER = Color.rgb(255, 190, 70)
        private val MUTED = Color.argb(165, 255, 255, 255)
    }
}
