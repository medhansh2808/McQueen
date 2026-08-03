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
import kotlin.math.roundToInt

class VerticalSpeedSlider @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    fun interface Listener {
        fun onChanged(percent: Int)
    }

    var listener: Listener? = null
    var percent: Int = 75
        private set

    private var lastHapticBucket = -1

    private val trackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(90, 255, 255, 255)
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 177, 42)
    }
    private val thumbPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 241, 194)
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textAlign = Paint.Align.CENTER
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }


    fun setPercent(value: Int, notify: Boolean = true) {
        percent = value.coerceIn(10, 100)
        if (notify) listener?.onChanged(percent)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        textPaint.textSize = width * 0.16f
        val trackWidth = width * 0.18f
        val top = height * 0.14f
        val bottom = height * 0.84f
        val left = width / 2f - trackWidth / 2f
        val right = width / 2f + trackWidth / 2f
        val radius = trackWidth / 2f

        canvas.drawRoundRect(RectF(left, top, right, bottom), radius, radius, trackPaint)
        val fillTop = bottom - (bottom - top) * (percent / 100f)
        canvas.drawRoundRect(RectF(left, fillTop, right, bottom), radius, radius, fillPaint)
        canvas.drawCircle(width / 2f, fillTop, width * 0.16f, thumbPaint)
        canvas.drawText("MAX $percent%", width / 2f, height * 0.075f, textPaint)
        canvas.drawText("SPEED", width / 2f, height * 0.95f, textPaint)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_MOVE,
            -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                val top = height * 0.14f
                val bottom = height * 0.84f
                val ratio = ((bottom - event.y) / (bottom - top)).coerceIn(0f, 1f)
                percent = (10 + ratio * 90f).roundToInt().coerceIn(10, 100)
                val bucket = when {
                    percent >= 98 -> 4
                    percent >= 73 -> 3
                    percent >= 48 -> 2
                    percent >= 23 -> 1
                    else -> 0
                }
                if (bucket != lastHapticBucket) {
                    performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
                    lastHapticBucket = bucket
                }
                listener?.onChanged(percent)
                invalidate()
                return true
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL,
            -> {
                performClick()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
}
