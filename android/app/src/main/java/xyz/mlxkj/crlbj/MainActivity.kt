package xyz.mlxkj.crlbj

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import xyz.mlxkj.crlbj.ui.LbjApp
import xyz.mlxkj.crlbj.ui.theme.LbjTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            LbjTheme {
                LbjApp()
            }
        }
    }
}
