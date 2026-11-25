import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
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
        // 手机端代际 v3：versionName 从 3.0 起算（桌面版 v2.x 体系独立）
        versionCode = 1
        versionName = "3.0"
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
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // Compose BOM（与 cw2 同版本）
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

    // Testing
    testImplementation(libs.junit)
    testImplementation(libs.org.json)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
