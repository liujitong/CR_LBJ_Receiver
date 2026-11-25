cmake_minimum_required(VERSION 3.22.1)
project(lbj LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -O2 -ffp-contract=off")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O2 -fexceptions -frtti -ffp-contract=off")

set(THIRDPARTY ${CMAKE_CURRENT_SOURCE_DIR}/thirdparty)

# ---- libusb 1.0.27（源码直编，官方 android/jni/libusb.mk 文件清单）----
add_library(usb1 STATIC
    ${THIRDPARTY}/libusb/libusb/core.c
    ${THIRDPARTY}/libusb/libusb/descriptor.c
    ${THIRDPARTY}/libusb/libusb/hotplug.c
    ${THIRDPARTY}/libusb/libusb/io.c
    ${THIRDPARTY}/libusb/libusb/sync.c
    ${THIRDPARTY}/libusb/libusb/strerror.c
    ${THIRDPARTY}/libusb/libusb/os/linux_usbfs.c
    ${THIRDPARTY}/libusb/libusb/os/events_posix.c
    ${THIRDPARTY}/libusb/libusb/os/threads_posix.c
    ${THIRDPARTY}/libusb/libusb/os/linux_netlink.c
)
target_include_directories(usb1 PRIVATE
    ${THIRDPARTY}/libusb-android
    ${THIRDPARTY}/libusb
    ${THIRDPARTY}/libusb/libusb
    ${THIRDPARTY}/libusb/libusb/os
)
target_compile_definitions(usb1 PRIVATE _GNU_SOURCE)
find_library(log-lib log)
target_link_libraries(usb1 PRIVATE ${log-lib})

# ---- librtlsdr 0.9（含 rtlsdr_open_fd 补丁：fd 直连，绕过设备枚举）----
add_library(rtlsdr STATIC
    ${THIRDPARTY}/librtlsdr/src/librtlsdr.c
    ${THIRDPARTY}/librtlsdr/src/tuner_e4k.c
    ${THIRDPARTY}/librtlsdr/src/tuner_fc0012.c
    ${THIRDPARTY}/librtlsdr/src/tuner_fc0013.c
    ${THIRDPARTY}/librtlsdr/src/tuner_fc2580.c
    ${THIRDPARTY}/librtlsdr/src/tuner_r82xx.c
    ${THIRDPARTY}/librtlsdr/src/rtlsdr_rpc.c
    ${THIRDPARTY}/librtlsdr/src/rtlsdr_rpc_msg.c
)
target_include_directories(rtlsdr PRIVATE
    ${THIRDPARTY}/librtlsdr/include
    ${THIRDPARTY}/librtlsdr/src
    ${THIRDPARTY}/libusb/libusb
)
target_link_libraries(rtlsdr PRIVATE usb1 ${log-lib})

# ---- 核心源（引擎与对拍 CLI 共用）----
set(LBJ_CORE_SOURCES
    core/dsp_math.cpp
    core/gbk_decode.cpp
    core/result_json.cpp
)

# ---- 主 JNI 库 ----
add_library(lbj SHARED
    lbj_jni.cpp
    core/engine.cpp
    ${LBJ_CORE_SOURCES}
)
target_include_directories(lbj PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/core
    ${THIRDPARTY}/librtlsdr/include
)
target_link_libraries(lbj PRIVATE rtlsdr usb1 ${log-lib})

# 16 KB 页对齐（Android 15+ 设备与新版模拟器的兼容要求）
target_link_options(lbj PRIVATE "-Wl,-z,max-page-size=16384")

# ---- 对拍 CLI（可执行文件，不进 APK；从 .cxx 产物目录 adb push 到模拟器运行）----
add_executable(lbj_cli
    cli/lbj_cli.cpp
    ${LBJ_CORE_SOURCES}
)
target_include_directories(lbj_cli PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/core
)
# bionic 动态链接器兼容：显式双 hash + 16KB 页对齐（模拟器镜像要求）
target_link_options(lbj_cli PRIVATE "-Wl,--hash-style=both" "-Wl,-z,max-page-size=16384")
