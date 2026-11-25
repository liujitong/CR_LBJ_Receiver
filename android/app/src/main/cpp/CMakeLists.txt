cmake_minimum_required(VERSION 3.22.1)
project(lbj LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O2 -fexceptions -frtti")

# M0：JNI 骨架（init/start/stop/release/readSpectrum/setParams 占位）
# M1：加入 libusb + librtlsdr 源码子目录；M2：加入 dsp/ pocsag/ 解码模块
add_library(lbj SHARED
    lbj_jni.cpp
)

find_library(log-lib log)
target_link_libraries(lbj PRIVATE ${log-lib})
