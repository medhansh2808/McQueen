package com.kartik.mcqueencontroller

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs

/** Two independent spring-return RC controls with true multi-touch. */
class DualRcSliderView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    fun interface Listener {
        fun onMove(steering: Float, throttle: Float)
    }

    var listener: Listener? = null

    private val panelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(150, 9, 11, 16) }
    private val trackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(135, 255, 255, 255) }
    private val centrePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(225, 38, 38) }
    private val knobPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(232, 50, 50) }
    private val knobBorder = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        color = Color.argb(220, 255, 255, 255)
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(190, 255, 255, 255)
        textSize = 25f
        textAlign = Paint.Align.CENTER
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }
    private val valuePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 31f
        textAlign = Paint.Align.CENTER
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }

    private var throttlePointerId = MotionEvent.INVALID_POINTER_ID
    private var steeringPointerId = MotionEvent.INVALID_POINTER_ID
    private var throttle = 0f
    private var steering = 0f
    private var previousThrottleSign = 0
    private var previousSteeringSign = 0

    private val deadZone = 0.055f

    init {
        isClickable = true
        contentDescription = "RC throttle and steering sliders"
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val divider = width * 0.50f
        val padding = width * 0.035f
        val top = height * 0.10f
        val bottom = height * 0.90f

        val leftPanel = RectF(padding, top, divider - padding, bottom)
        val rightPanel = RectF(divider + padding, top, width - padding, bottom)
        canvas.drawRoundRect(leftPanel, 34f, 34f, panelPaint)
        canvas.drawRoundRect(rightPanel, 34f, 34f, panelPaint)

        val throttleX = width * 0.25f
        val throttleCentreY = height * 0.52f
        val throttleTravel = height * 0.31f
        val steeringCentreX = width * 0.75f
        val steeringY = height * 0.52f
        val steeringTravel = width * 0.18f

        canvas.drawRoundRect(
            RectF(throttleX - 10f, throttleCentreY - throttleTravel, throttleX + 10f, throttleCentreY + throttleTravel),
            10f,
            10f,
            trackPaint,
        )
        canvas.drawRoundRect(
            RectF(steeringCentreX - steeringTravel, steeringY - 10f, steeringCentreX + steeringTravel, steeringY + 10f),
            10f,
            10f,
            trackPaint,
        )
        canvas.drawRect(throttleX - 30f, throttleCentreY - 2f, throttleX + 30f, throttleCentreY + 2f, centrePaint)
        canvas.drawRect(steeringCentreX - 2f, steeringY - 30f, steeringCentreX + 2f, steeringY + 30f, centrePaint)

        val throttleKnobY = throttleCentreY - throttle * throttleTravel
        val steeringKnobX = steeringCentreX + steering * steeringTravel
        canvas.drawRoundRect(RectF(throttleX - 46f, throttleKnobY - 26f, throttleX + 46f, throttleKnobY + 26f), 18f, 18f, knobPaint)
        canvas.drawRoundRect(RectF(throttleX - 46f, throttleKnobY - 26f, throttleX + 46f, throttleKnobY + 26f), 18f, 18f, knobBorder)
        canvas.drawRoundRect(RectF(steeringKnobX - 26f, steeringY - 46f, steeringKnobX + 26f, steeringY + 46f), 18f, 18f, knobPaint)
        canvas.drawRoundRect(RectF(steeringKnobX - 26f, steeringY - 46f, steeringKnobX + 26f, steeringY + 46f), 18f, 18f, knobBorder)

        canvas.drawText("FWD", throttleX, throttleCentreY - throttleTravel - 22f, labelPaint)
        canvas.drawText("REV", throttleX, throttleCentreY + throttleTravel + 42f, labelPaint)
        canvas.drawText("THROTTLE", throttleX, top + 38f, labelPaint)
        canvas.drawText("${(throttle * 1000).toInt()}", throttleX, bottom - 24f, valuePaint)

        canvas.drawText("LEFT", steeringCentreX - steeringTravel, steeringY - 32f, labelPaint)
        canvas.drawText("RIGHT", steeringCentreX + steeringTravel, steeringY - 32f, labelPaint)
        canvas.drawText("STEERING", steeringCentreX, top + 38f, labelPaint)
        canvas.drawText("${(steering * 1000).toInt()}", steeringCentreX, bottom - 24f, valuePaint)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        parent?.requestDisallowInterceptTouchEvent(true)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_POINTER_DOWN,
            -> {
                val index = event.actionIndex
                val id = event.getPointerId(index)
                if (event.getX(index) < width * 0.50f && throttlePointerId == MotionEvent.INVALID_POINTER_ID) {
                    throttlePointerId = id
                    updateThrottle(event.getY(index))
                } else if (steeringPointerId == MotionEvent.INVALID_POINTER_ID) {
                    steeringPointerId = id
                    updateSteering(event.getX(index))
                }
                emit()
                return true
            }

            MotionEvent.ACTION_MOVE -> {
                if (throttlePointerId != MotionEvent.INVALID_POINTER_ID) {
                    val index = event.findPointerIndex(throttlePointerId)
                    if (index >= 0) updateThrottle(event.getY(index))
                }
                if (steeringPointerId != MotionEvent.INVALID_POINTER_ID) {
                    val index = event.findPointerIndex(steeringPointerId)
                    if (index >= 0) updateSteering(event.getX(index))
                }
                emit()
                return true
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_POINTER_UP,
            MotionEvent.ACTION_CANCEL,
            -> {
                val id = event.getPointerId(event.actionIndex)
                if (id == throttlePointerId || event.actionMasked == MotionEvent.ACTION_CANCEL) {
                    throttlePointerId = MotionEvent.INVALID_POINTER_ID
                    throttle = 0f
                }
                if (id == steeringPointerId || event.actionMasked == MotionEvent.ACTION_CANCEL) {
                    steeringPointerId = MotionEvent.INVALID_POINTER_ID
                    steering = 0f
                }
                emit()
                if (event.actionMasked == MotionEvent.ACTION_UP) performClick()
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
        throttlePointerId = MotionEvent.INVALID_POINTER_ID
        steeringPointerId = MotionEvent.INVALID_POINTER_ID
        throttle = 0f
        steering = 0f
        previousThrottleSign = 0
        previousSteeringSign = 0
        emit()
    }

    private fun updateThrottle(y: Float) {
        val centre = height * 0.52f
        val travel = height * 0.31f
        throttle = applyDeadZone(((centre - y) / travel).coerceIn(-1f, 1f))
        val sign = throttle.compareTo(0f)
        if (previousThrottleSign != 0 && sign != previousThrottleSign) {
            performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        }
        previousThrottleSign = sign
    }

    private fun updateSteering(x: Float) {
        val centre = width * 0.75f
        val travel = width * 0.18f
        steering = applyDeadZone(((x - centre) / travel).coerceIn(-1f, 1f))
        val sign = steering.compareTo(0f)
        if (previousSteeringSign != 0 && sign != previousSteeringSign) {
            performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        }
        previousSteeringSign = sign
    }

    private fun applyDeadZone(value: Float): Float {
        val magnitude = abs(value)
        if (magnitude <= deadZone) return 0f
        val scaled = (magnitude - deadZone) / (1f - deadZone)
        return if (value < 0f) -scaled else scaled
    }

    private fun emit() {
        listener?.onMove(steering, throttle)
        invalidate()
    }
}
