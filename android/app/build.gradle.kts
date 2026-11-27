import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
}
// 注意：AGP 9 内置 Kotlin 支持，不另应用 org.jetbrains.kotlin.android（与 cw2 一致）

// release 签名材料放 android/keystore.properties（已 gitignore）；缺失时 release 保持未签名，
// assembleDebug 与日常开发不受影响（做法与 cw2 一致）。
val keystorePropertiesFile = rootProject.file("keystore.properties")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.exists()) {
        keystorePropertiesFile.inputStream().use { load(it) }
    }
}

/* ---------------------------------------------------------------------------
 * Ninja 版本预检（v3.0 新增）
 *
 * 由来：AGP 会把 ninja 以 -DCMAKE_MAKE_PROGRAM=<绝对路径> 传给 CMake。若它挑中
 * SDK 3.22.1 自带的 ninja 1.10.2，而本仓库物理路径含中文（…\预警器\…），
 * ninja 1.10 会用 ANSI 代码页解释 build.ninja 里的路径，直接报
 *   ninja: error: FindFirstFileExA(e:/预警器/…/cpp): 文件名、目录名或卷标语法不正确
 * CMake 本身没问题（pip 版 4.4.5，见 local.properties 的 cmake.dir）。
 * ninja 1.12 起按 UTF-8 处理路径。因此：把高于 1.12 的 ninja.exe 放到
 * <cmake.dir>/bin/ 下，AGP 会优先使用同目录的 ninja（tools/fix_ninja.ps1 就是干这个的）。
 * 这里只做「缺失就提醒」，不阻断配置——ASCII 路径下用旧 ninja 也能构建。
 * ------------------------------------------------------------------------- */
fun readCmakeDir(): File? {
    val localProps = rootProject.file("local.properties")
    val props = Properties().apply {
        if (localProps.exists()) localProps.inputStream().use { load(it) }
    }
    return props.getProperty("cmake.dir")?.takeIf { it.isNotBlank() }?.let { File(it) }
}

val cmakeDir = readCmakeDir()
val ninjaBesideCmake = cmakeDir?.resolve("bin")?.resolve("ninja.exe")
if (cmakeDir != null && (ninjaBesideCmake == null || !ninjaBesideCmake.isFile)) {
    logger.warn(
        "[lbj] 提醒：${cmakeDir}/bin/ninja.exe 不存在。" +
            "若源码路径含中文（如 …\\预警器\\…），AGP 会退回 SDK 里的旧 ninja 1.10，" +
            "导致 native 构建报 FindFirstFileExA 失败。运行 tools/fix_ninja.ps1 修复。"
    )
}

android {
    namespace = "xyz.mlxkj.crlbj"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "xyz.mlxkj.crlbj"
        minSdk = 26
        targetSdk = 35
        // 用户指定 NDK r27
        ndkVersion = "27.2.12479018"
        // v3.2.11：跟随语义定稿（任何新信号都追）+ 解码对拍复核；versionCode 331
        versionCode = 331
        versionName = "3.2.11"
    }

    signingConfigs {
        if (keystorePropertiesFile.exists()) {
            create("release") {
                storeFile = rootProject.file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            // debug 保留全部 ABI：x86_64/x86 供模拟器验证（做法与 cw2 一致）
            ndk { abiFilters += setOf("arm64-v8a", "armeabi-v7a", "x86_64", "x86") }
        }
        release {
            isMinifyEnabled = false
            // release 只打 arm：arm64 覆盖现代手机，v7a 兜底老机器
            ndk { abiFilters += setOf("arm64-v8a", "armeabi-v7a") }
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (keystorePropertiesFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    kotlin {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_11)
        }
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }

    // ---- 共享资源（与桌面端逐字同一份）----
    // android/ 是 app 模块的 rootProject，所以 ../shared = CR_LBJ_Receiver/shared。
    // 作为 assets 根目录后，APK 内路径为 assets/web/railmap.html 与 assets/data/*.csv
    // （Kotlin 侧对应 file:///android_asset/web/railmap.html）。
    sourceSets.getByName("main") {
        assets.directories.add(rootProject.file("../shared").absolutePath)
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            // 不写死 version：AGP 会优先用 local.properties 的 cmake.dir。
            // 本机 Android SDK 自带的 CMake 3.22.1 / 3.31.6 二进制在此 Windows 版本上
            // 配置阶段必然崩溃（C++ 编译器识别时 0xC0000409），pip 版 CMake 4.4.5 正常，
            // 详见 docs/安卓构建与环境.md。需要固定 SDK 版本时用 -PcmakeVersion=3.22.1。
            (project.findProperty("cmakeVersion") as String?)?.let { version = it }
        }
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }

    // JVM 单元测试：纯解析逻辑（号段表/车次 JSON/数据校验）不该依赖模拟器。
    // returnDefaultValues 让误调 android.* 的桩方法返回默认值而不是直接抛异常。
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

/*
 * AGP 9「内置 Kotlin」的单元测试产物补丁
 *
 * 现象：`:app:testDebugUnitTest` 报
 *   ClassNotFoundException: xyz.mlxkj.crlbj.data.LocoRosterTest
 * 原因：内置 Kotlin 把测试 class 编译到
 *   build/intermediates/built_in_kotlinc/debugUnitTest/compileDebugUnitTestKotlin/classes
 * 但 Test 任务的 testClassesDirs / classpath 里没有这个目录（AGP 9.3.x 已知问题）。
 * 这里按任务名反推目录补进去；纯 JVM 逻辑测试（解析/校验）依赖它。
 */
tasks.withType<Test>().configureEach {
    val variantFolder = name.removePrefix("test").removeSuffix("UnitTest")
    if (variantFolder.isNotEmpty()) {
        val lower = variantFolder.replaceFirstChar { it.lowercaseChar() } + "UnitTest"
        val classesDir = layout.buildDirectory.dir(
            "intermediates/built_in_kotlinc/$lower/compile${variantFolder}UnitTestKotlin/classes"
        )
        testClassesDirs = testClassesDirs + files(classesDir)
        classpath = classpath + files(classesDir)
    }
}

dependencies {    // Compose BOM（与 cw2 同版本）
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.extended)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)

    // Compose Fluent：FluentTheme / Mica 背景 / 部分基础控件；业务卡片、频谱条、状态块自绘
    implementation(libs.compose.fluent)

    // Core & Lifecycle
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)

    // Coroutines
    implementation(libs.kotlinx.coroutines.android)

    // JSON（配置文件与桌面版 lbj_config.json 互导）
    implementation(libs.org.json)

    // 地图瓦片离线缓存（v3.1：cacheDir/tile_cache，300MB LRU）
    implementation("com.jakewharton:disklrucache:2.0.2")

    // Room 历史库
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)

    // Testing
    testImplementation(libs.junit)
    testImplementation(libs.org.json)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
