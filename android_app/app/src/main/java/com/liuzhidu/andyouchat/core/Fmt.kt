package com.liuzhidu.andyouchat.core

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/** 展示格式化：时间、日期分割、预览、头像首字（对齐网页版 format.js） */
object Fmt {

    fun initial(name: String?): String {
        val t = name?.trim().orEmpty()
        return if (t.isEmpty()) "?" else t.take(1).uppercase(Locale.ROOT)
    }

    /** 会话列表时间：今天 HH:mm / 昨天 HH:mm / M/d HH:mm */
    fun fmtTime(ms: Long?): String {
        if (ms == null || ms <= 0) return ""
        val d = Date(ms)
        val hm = SimpleDateFormat("HH:mm", Locale.getDefault()).format(d)
        val cal = Calendar.getInstance()
        val today = cal.clone() as Calendar
        cal.time = d
        return when {
            sameDay(cal, today) -> hm
            run {
                val y = (today.clone() as Calendar).apply { add(Calendar.DATE, -1) }
                sameDay(cal, y)
            } -> "昨天 $hm"
            cal.get(Calendar.YEAR) == today.get(Calendar.YEAR) ->
                "${cal.get(Calendar.MONTH) + 1}/${cal.get(Calendar.DATE)} $hm"
            else -> SimpleDateFormat("yyyy/M/d HH:mm", Locale.getDefault()).format(d)
        }
    }

    /** 消息流内日期分割：M月d日（跨年带年份） */
    fun fmtDay(ms: Long): String {
        val cal = Calendar.getInstance().apply { timeInMillis = ms }
        val now = Calendar.getInstance()
        val md = "${cal.get(Calendar.MONTH) + 1}月${cal.get(Calendar.DATE)}日"
        return if (cal.get(Calendar.YEAR) == now.get(Calendar.YEAR)) md
        else "${cal.get(Calendar.YEAR)}年$md"
    }

    fun sameDay(ms1: Long, ms2: Long): Boolean {
        val c1 = Calendar.getInstance().apply { timeInMillis = ms1 }
        val c2 = Calendar.getInstance().apply { timeInMillis = ms2 }
        return sameDay(c1, c2)
    }

    private fun sameDay(a: Calendar, b: Calendar): Boolean =
        a.get(Calendar.YEAR) == b.get(Calendar.YEAR) &&
            a.get(Calendar.MONTH) == b.get(Calendar.MONTH) &&
            a.get(Calendar.DATE) == b.get(Calendar.DATE)

    /** 会话列表最后一条消息预览 */
    fun preview(m: MessageOut?): String = when {
        m == null -> ""
        m.revoked -> "[消息已撤回]"
        m.msgType == "image" -> "[图片]"
        else -> m.content
    }
}
