package com.liuzhidu.andyouchat

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.liuzhidu.andyouchat.ui.AppRoot
import com.liuzhidu.andyouchat.ui.theme.AndYouTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val container = (application as AndYouApp).container
        setContent {
            AndYouTheme {
                AppRoot(container)
            }
        }
    }
}
