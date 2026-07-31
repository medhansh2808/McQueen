package com.kartik.mcqueencontroller

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/** Shows the exact steering/throttle value transmitted in the latest UDP command. */
class TelemetryBarView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    enum class Mode { SERVO, THROTTLE }

    var mode: Mode = Mode.SERVO
    private var sent = 0

    private val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }
    private val valuePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 205, 95)
        textAlign = Paint.Align.RIGHT
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }
    private val endPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(145, 255, 255, 255)
    }
    private val trackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(62, 255, 255, 255)
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 177, 42)
    }
    private val centrePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(190, 255, 255, 255)
        strokeWidth = 2f
    }

    fun setValue(sentValue: Int) {
        sent = sentValue
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val left = width * 0.04f
        val right = width * 0.96f
        val centre = (left + right) / 2f
        val title = if (mode == Mode.THROTTLE) "THROTTLE SENT" else "SERVO SENT"
        val negative = if (mode == Mode.THROTTLE) "REV" else "LEFT"
        val positive = if (mode == Mode.THROTTLE) "FWD" else "RIGHT"

        titlePaint.textSize = height * 0.20f
        valuePaint.textSize = height * 0.23f
        endPaint.textSize = height * 0.13f

        canvas.drawText(title, left, height * 0.25f, titlePaint)
        canvas.drawText(if (sent >= 0) "+$sent" else sent.toString(), right, height * 0.27f, valuePaint)

        val trackTop = height * 0.43f
        val trackBottom = height * 0.68f
        val radius = (trackBottom - trackTop) / 2f
        canvas.drawRoundRect(RectF(left, trackTop, right, trackBottom), radius, radius, trackPaint)
        canvas.drawLine(centre, trackTop - 4f, centre, trackBottom + 4f, centrePaint)

        val norm = when (mode) {
            Mode.SERVO -> sent.coerceIn(-1000, 1000) / 1000f
            Mode.THROTTLE -> sent.coerceIn(-1000, 1000) / 1000f
        }
        val x = centre + norm * (right - left) / 2f
        if (kotlin.math.abs(x - centre) > 1f) {
            canvas.drawRoundRect(RectF(minOf(centre, x), trackTop, maxOf(centre, x), trackBottom), radius, radius, fillPaint)
        }

        canvas.drawText(negative, left, height * 0.91f, endPaint)
        endPaint.textAlign = Paint.Align.CENTER
        canvas.drawText("0", centre, height * 0.91f, endPaint)
        endPaint.textAlign = Paint.Align.RIGHT
        canvas.drawText(positive, right, height * 0.91f, endPaint)
        endPaint.textAlign = Paint.Align.LEFT
    }
}
