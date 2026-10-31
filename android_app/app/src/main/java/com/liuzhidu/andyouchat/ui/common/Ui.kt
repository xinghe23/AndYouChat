package com.liuzhidu.andyouchat.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.liuzhidu.andyouchat.core.Fmt
import com.liuzhidu.andyouchat.ui.theme.Brand
import com.liuzhidu.andyouchat.ui.theme.BrandSoft
import com.liuzhidu.andyouchat.ui.theme.DangerRed
import com.liuzhidu.andyouchat.ui.theme.TextMuted

/** 圆形首字头像（对齐网页版 .avatar） */
@Composable
fun Avatar(name: String?, size: Dp = 34.dp) {
    Box(
        modifier = Modifier.size(size).background(BrandSoft, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = Fmt.initial(name),
            color = Brand,
            fontWeight = FontWeight.SemiBold,
            fontSize = (size.value * 0.38f).sp,
        )
    }
}

/** 红点未读角标（对齐 .badge） */
@Composable
fun UnreadBadge(count: Int) {
    if (count <= 0) return
    Box(
        modifier = Modifier
            .background(DangerRed, RoundedCornerShape(50))
            .padding(horizontal = 4.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = if (count > 99) "99+" else count.toString(),
            color = Color.White,
            fontSize = 10.sp,
            lineHeight = 14.sp,
        )
    }
}

/** 空态提示 */
@Composable
fun EmptyHint(text: String, modifier: Modifier = Modifier) {
    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Text(text = text, color = TextMuted, fontSize = 13.sp, lineHeight = 20.sp)
    }
}
