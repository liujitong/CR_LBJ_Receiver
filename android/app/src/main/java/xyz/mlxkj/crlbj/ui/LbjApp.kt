package xyz.mlxkj.crlbj.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Analytics
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import xyz.mlxkj.crlbj.ui.components.DockTab
import xyz.mlxkj.crlbj.ui.components.LbjDock
import xyz.mlxkj.crlbj.ui.pages.DecodePage
import xyz.mlxkj.crlbj.ui.pages.HistoryPage
import xyz.mlxkj.crlbj.ui.pages.MapPage
import xyz.mlxkj.crlbj.ui.pages.QueryPage
import xyz.mlxkj.crlbj.ui.pages.SettingsPage
import xyz.mlxkj.crlbj.ui.pages.StatusPage
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel

private val tabs = listOf(
    DockTab("地图", Icons.Filled.Map),
    DockTab("解码", Icons.Filled.GraphicEq),
    DockTab("历史", Icons.Filled.History),
    DockTab("状态", Icons.Filled.Analytics),
    DockTab("查询", Icons.Filled.Search),
    DockTab("设置", Icons.Filled.Settings),
)

/** 页签索引常量（跨页跳转用） */
private const val TAB_MAP = 0
private const val TAB_DECODE = 1
private const val TAB_HISTORY = 2
private const val TAB_STATUS = 3
private const val TAB_QUERY = 4
private const val TAB_SETTINGS = 5

/**
 * 六页 + 悬浮玻璃胶囊 Dock（v3.0 视觉重做）。
 *
 * 没有 Material NavigationBar / 没有重顶栏：每页自己的「大标题 + 状态胶囊」就是顶栏；
 * 地图页是全屏 WebView，胶囊与浮动按钮直接浮在图上。
 * 默认落在解码页：「一键开始」第一屏可见。
 */
@Composable
fun LbjApp() {
    val vm: ReceiverViewModel = viewModel()
    val p = pal()
    var current by rememberSaveable { mutableIntStateOf(TAB_DECODE) }

    Box(Modifier.fillMaxSize().background(p.bg)) {
        // 地图页要全屏出血（WebView 铺满），其余页让开状态栏
        if (current == TAB_MAP) {
            MapPage(vm)
        } else {
            Box(Modifier.fillMaxSize().statusBarsPadding()) {
                when (current) {
                    TAB_DECODE -> DecodePage(
                        vm = vm,
                        onQueryTrain = { train ->
                            vm.requestTrainQuery(train)
                            current = TAB_QUERY
                        },
                        onQueryLoco = { model, number ->
                            vm.requestLocoQuery(model, number)
                            current = TAB_QUERY
                        },
                    )
                    TAB_HISTORY -> HistoryPage(vm)
                    TAB_STATUS -> StatusPage(vm)
                    TAB_QUERY -> QueryPage(vm)
                    TAB_SETTINGS -> SettingsPage(vm)
                    else -> HistoryPage(vm)
                }
            }
        }

        LbjDock(
            tabs = tabs,
            current = current,
            onSelect = { current = it },
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(bottom = 10.dp),
        )
    }
}
