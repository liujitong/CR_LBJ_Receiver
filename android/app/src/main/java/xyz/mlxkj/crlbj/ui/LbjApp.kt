package xyz.mlxkj.crlbj.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.viewmodel.compose.viewModel
import xyz.mlxkj.crlbj.ui.pages.DecodePage
import xyz.mlxkj.crlbj.ui.pages.HistoryPage
import xyz.mlxkj.crlbj.ui.pages.MapPage
import xyz.mlxkj.crlbj.ui.pages.SettingsPage
import xyz.mlxkj.crlbj.ui.pages.StatusPage
import xyz.mlxkj.crlbj.vm.ReceiverViewModel

private data class Tab(
    val title: String,
    val icon: androidx.compose.ui.graphics.vector.ImageVector,
)

private val tabs = listOf(
    Tab("地图", Icons.Filled.Map),
    Tab("解码", Icons.Filled.GraphicEq),
    Tab("历史", Icons.Filled.History),
    Tab("状态", Icons.Filled.Info),
    Tab("设置", Icons.Filled.Settings),
)

/**
 * 五页底部导航（竖屏为主），Material 理念按手机端习惯重排——
 * 不搬桌面版 Qt 布局。默认落在解码页："一键开始"第一屏可见。
 */
@Composable
fun LbjApp() {
    val vm: ReceiverViewModel = viewModel()
    var current by remember { mutableIntStateOf(1) } // 默认解码页

    Scaffold(
        bottomBar = {
            NavigationBar {
                tabs.forEachIndexed { i, tab ->
                    NavigationBarItem(
                        selected = current == i,
                        onClick = { current = i },
                        icon = { Icon(tab.icon, contentDescription = tab.title) },
                        label = { Text(tab.title) },
                    )
                }
            }
        }
    ) { _padding ->
        when (current) {
            0 -> MapPage()
            1 -> DecodePage(vm)
            2 -> HistoryPage()
            3 -> StatusPage(vm)
            4 -> SettingsPage(vm)
        }
    }
}
