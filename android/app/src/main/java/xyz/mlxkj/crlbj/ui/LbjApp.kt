package xyz.mlxkj.crlbj.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Analytics
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Map
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
import xyz.mlxkj.crlbj.ui.pages.InfoPage
import xyz.mlxkj.crlbj.ui.pages.MapPage
import xyz.mlxkj.crlbj.ui.pages.SettingsPage
import xyz.mlxkj.crlbj.ui.pages.StatusPage
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel

private val tabs = listOf(
    DockTab("地图", Icons.Filled.Map),
    DockTab("解码", Icons.Filled.GraphicEq),
    DockTab("信息", Icons.Filled.Info),
    DockTab("状态", Icons.Filled.Analytics),
    DockTab("设置", Icons.Filled.Settings),
)

/** 页签索引常量（跨页跳转用） */
private const val TAB_MAP = 0
private const val TAB_DECODE = 1
private const val TAB_INFO = 2
private const val TAB_STATUS = 3
private const val TAB_SETTINGS = 4

/**
 * 五页 + 悬浮玻璃胶囊 Dock。
 *
 * 没有 Material NavigationBar / 没有重顶栏：每页自己的「大标题 + 状态胶囊」就是顶栏；
 * 地图页是全屏 WebView，胶囊与浮动按钮直接浮在图上。
 * 默认落在解码页：「一键开始」第一屏可见。
 * 手动查询并入设置页「查询·数据」分组：解码卡点「车次/机车」→ 预填请求 + 跳设置页。
 */
@Composable
fun LbjApp() {
    val vm: ReceiverViewModel = viewModel()
    val p = pal()
    var current by rememberSaveable { mutableIntStateOf(TAB_DECODE) }
    // v3.2.6：记住上一个标签页。设置页是二级页面——按返回应回到设置菜单、
    // 再按一次回上一个标签页，而不是直接退出 App（用户反馈这样太反人类）。
    var lastTab by rememberSaveable { mutableIntStateOf(TAB_DECODE) }
    fun switchTo(t: Int) {
        if (t != current) lastTab = current
        current = t
    }

    Box(Modifier.fillMaxSize().background(p.bg)) {
        // 地图页要全屏出血（WebView 铺满），浮层的避让由 MapPage 自己处理；
        // 其余页统一让开状态栏/刘海（safeDrawing = 状态栏 + 挖孔 + 导航栏 + IME）
        if (current == TAB_MAP) {
            MapPage(vm)
        } else {
            Box(
                Modifier
                    .fillMaxSize()
                    .windowInsetsPadding(
                        WindowInsets.safeDrawing.only(
                            WindowInsetsSides.Top + WindowInsetsSides.Horizontal)
                    )
            ) {
                when (current) {
                    TAB_DECODE -> DecodePage(
                        vm = vm,
                        onQueryTrain = { train ->
                            vm.requestTrainQuery(train)
                            switchTo(TAB_SETTINGS)
                        },
                        onQueryLoco = { model, number ->
                            vm.requestLocoQuery(model, number)
                            switchTo(TAB_SETTINGS)
                        },
                    )
                    TAB_INFO -> InfoPage(vm)
                    TAB_STATUS -> StatusPage(vm)
                    TAB_SETTINGS -> SettingsPage(vm, onBack = { switchTo(lastTab) })
                    else -> InfoPage(vm)
                }
            }
        }

        LbjDock(
            tabs = tabs,
            current = current,
            onSelect = { switchTo(it) },
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .windowInsetsPadding(
                    WindowInsets.safeDrawing.only(
                        WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal)
                )
                .padding(bottom = 10.dp),
        )
    }
}
