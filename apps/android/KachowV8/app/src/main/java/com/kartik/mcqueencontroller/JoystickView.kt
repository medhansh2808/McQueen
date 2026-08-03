package com.kartik.mcqueencontroller

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.util.AttributeSet
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs

/**
 * Floating independent-axis joystick.
 *
 * Unlike a circular vector joystick, X and Y are clamped independently. This
 * means full top-right can simultaneously request full throttle and full right
 * steering instead of sacrificing throttle as steering increases.
 */
class JoystickView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    fun interface Listener {
        fun onMove(steering: Float, throttle: Float)
    }

    var listener: Listener? = null

    private val basePaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        color = Color.argb(180, 255, 255, 255)
    }
    private val axisPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 2f
        color = Color.argb(58, 255, 255, 255)
    }
    private val redAxisPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 3f
        color = Color.argb(130, 225, 35, 35)
    }
    private val knobPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(145, 255, 255, 255)
        textAlign = Paint.Align.CENTER
        textSize = 25f
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }

    private var centreX = 0f
    private var centreY = 0f
    private var defaultCentreX = 0f
    private var defaultCentreY = 0f
    private var travel = 0f
    private var knobRadius = 0f
    private var knobX = 0f
    private var knobY = 0f
    private var active = false
    private var lastThrottleSign = 0

    private val deadZone = 0.07f

    init {
        isFocusable = true
        isClickable = true
        contentDescription = "Independent steering and throttle joystick"
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        travel = minOf(w * 0.30f, h * 0.31f)
        knobRadius = travel * 0.27f
        defaultCentreX = w * 0.39f
        defaultCentreY = h * 0.58f
        centreX = defaultCentreX
        centreY = defaultCentreY
        knobX = centreX
        knobY = centreY
        refreshShaders()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val outer = RectF(
            centreX - travel,
            centreY - travel,
            centreX + travel,
            centreY + travel,
        )
        basePaint.alpha = if (active) 242 else 112
        borderPaint.alpha = if (active) 220 else 92
        knobPaint.alpha = if (active) 252 else 132

        canvas.drawRoundRect(outer, travel * 0.32f, travel * 0.32f, basePaint)
        canvas.drawRoundRect(outer, travel * 0.32f, travel * 0.32f, borderPaint)
        canvas.drawLine(centreX - travel, centreY, centreX + travel, centreY, redAxisPaint)
        canvas.drawLine(centreX, centreY - travel, centreX, centreY + travel, axisPaint)

        canvas.drawCircle(knobX, knobY, knobRadius, knobPaint)
        canvas.drawCircle(knobX, knobY, knobRadius, borderPaint)

        canvas.drawText("FWD", centreX, centreY - travel - 19f, labelPaint)
        canvas.drawText("REV", centreX, centreY + travel + 34f, labelPaint)
        canvas.drawText("LEFT", centreX - travel, centreY - 18f, labelPaint)
        canvas.drawText("RIGHT", centreX + travel, centreY - 18f, labelPaint)

        if (!active) {
            canvas.drawText("TOUCH TO DRIVE", centreX, centreY + travel + 72f, labelPaint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                active = true
                moveCentreTo(event.x, event.y)
                updateKnob(event.x, event.y)
                return true
            }

            MotionEvent.ACTION_MOVE -> {
                updateKnob(event.x, event.y)
                return true
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL,
            -> {
                performClick()
                active = false
                knobX = centreX
                knobY = centreY
                lastThrottleSign = 0
                listener?.onMove(0f, 0f)
                invalidate()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    fun reset() {
        active = false
        centreX = defaultCentreX
        centreY = defaultCentreY
        knobX = centreX
        knobY = centreY
        lastThrottleSign = 0
        refreshShaders()
        listener?.onMove(0f, 0f)
        invalidate()
    }

    private fun moveCentreTo(touchX: Float, touchY: Float) {
        val margin = travel + knobRadius * 0.20f
        centreX = touchX.coerceIn(margin, width - margin)
        centreY = touchY.coerceIn(margin, height - margin)
        knobX = centreX
        knobY = centreY
        refreshShaders()
    }

    private fun refreshShaders() {
        if (travel <= 0f) return
        basePaint.shader = RadialGradient(
            centreX - travel * 0.18f,
            centreY - travel * 0.22f,
            travel * 1.75f,
            intArrayOf(
                Color.argb(205, 43, 46, 54),
                Color.argb(185, 14, 16, 21),
                Color.argb(175, 3, 4, 7),
            ),
            floatArrayOf(0f, 0.62f, 1f),
            Shader.TileMode.CLAMP,
        )
        knobPaint.shader = RadialGradient(
            centreX - knobRadius * 0.32f,
            centreY - knobRadius * 0.32f,
            knobRadius * 1.55f,
            intArrayOf(
                Color.rgb(255, 120, 120),
                Color.rgb(224, 40, 40),
                Color.rgb(105, 8, 8),
            ),
            floatArrayOf(0f, 0.58f, 1f),
            Shader.TileMode.CLAMP,
        )
    }

    private fun updateKnob(touchX: Float, touchY: Float) {
        knobX = touchX.coerceIn(centreX - travel, centreX + travel)
        knobY = touchY.coerceIn(centreY - travel, centreY + travel)

        var steering = ((knobX - centreX) / travel).coerceIn(-1f, 1f)
        var throttle = ((centreY - knobY) / travel).coerceIn(-1f, 1f)
        steering = applyDeadZone(steering)
        throttle = applyDeadZone(throttle)

        val sign = when {
            throttle > 0f -> 1
            throttle < 0f -> -1
            else -> 0
        }
        if (sign != lastThrottleSign && lastThrottleSign != 0) {
            performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        }
        lastThrottleSign = sign

        listener?.onMove(steering, throttle)
        invalidate()
    }

    private fun applyDeadZone(value: Float): Float {
        val magnitude = abs(value)
        if (magnitude <= deadZone) return 0f
        val scaled = (magnitude - deadZone) / (1f - deadZone)
        return if (value < 0f) -scaled else scaled
    }
}
