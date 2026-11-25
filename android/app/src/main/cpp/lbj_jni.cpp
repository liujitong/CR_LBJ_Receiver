/**
 * lbj_jni.cpp — JNI 契约骨架（M0）
 *
 * 契约（严格 6 个 native 方法，见 LbjNative.kt）：
 *   nativeInit(paramsJson) / nativeStart(sourceFd, mode, freqHz, sampleRate, gainCentiDb, ppm)
 *   nativeStop() / nativeRelease() / nativeReadSpectrum(bb) / nativeSetParams(paramsJson)
 *
 * 回调（native→Kotlin）只有 2 个：onDecodeEventFromNative(json)、onLogFromNative(msg)。
 *
 * M0：占位实现——init 建引擎桩并回 "native init ok"，start 返回"未接数据源"，
 *     readSpectrum 返回 0（无新帧）。M1 起补 Reader/RingBuffer/DSP 线程。
 */
#include <jni.h>
#include <android/log.h>
#include <string>
#include <mutex>

#define LOG_TAG "LBJ"
#define ALOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define ALOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace {

std::mutex g_mutex;        // 引擎生命周期串行化
bool g_inited = false;

// 反向回调：拿到 LbjNative 单例的 onDecodeEventFromNative / onLogFromNative 方法
jmethodID g_logMid = nullptr;
jmethodID g_decodeMid = nullptr;

void callLog(JNIEnv* env, jobject thiz, const std::string& msg) {
    if (g_logMid && env) {
        jstring jmsg = env->NewStringUTF(msg.c_str());
        env->CallVoidMethod(thiz, g_logMid, jmsg);
        env->DeleteLocalRef(jmsg);
    }
}

} // namespace

extern "C" {

JNIEXPORT jint JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeInit(JNIEnv* env, jobject thiz, jstring paramsJson) {
    std::lock_guard<std::mutex> lock(g_mutex);
    // 缓存回调方法 ID（LbjNative 单例生命周期与应用进程一致）
    jclass cls = env->GetObjectClass(thiz);
    g_logMid = env->GetMethodID(cls, "onLogFromNative", "(Ljava/lang/String;)V");
    g_decodeMid = env->GetMethodID(cls, "onDecodeEventFromNative", "(Ljava/lang/String;)V");
    env->DeleteLocalRef(cls);

    const char* p = paramsJson ? env->GetStringUTFChars(paramsJson, nullptr) : "{}";
    ALOGI("nativeInit params=%s", p);
    if (paramsJson) env->ReleaseStringUTFChars(paramsJson, p);

    g_inited = true;
    ALOGI("native init ok");
    callLog(env, thiz, "native init ok");
    return 0;
}

JNIEXPORT jint JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeStart(JNIEnv* env, jobject thiz,
        jint sourceFd, jint mode, jlong freqHz, jint sampleRate,
        jint gainCentiDb, jint ppm) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_inited) {
        ALOGE("nativeStart before init");
        return -1;
    }
    ALOGI("nativeStart fd=%d mode=%d freqHz=%lld sr=%d gain=%d.%02ddB ppm=%d",
          sourceFd, mode, (long long)freqHz, sampleRate, gainCentiDb / 100, gainCentiDb % 100, ppm);
    // M0：读线程与 DSP 线程在 M1/M2 接入；返回 -2 表示"数据源通路未实现"
    callLog(env, thiz, "nativeStart: 数据源通路未实现（M1）");
    return -2;
}

JNIEXPORT void JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeStop(JNIEnv* env, jobject thiz) {
    std::lock_guard<std::mutex> lock(g_mutex);
    ALOGI("nativeStop");
}

JNIEXPORT void JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeRelease(JNIEnv* env, jobject thiz) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_inited = false;
    ALOGI("nativeRelease");
}

JNIEXPORT jint JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeReadSpectrum(JNIEnv* env, jobject thiz,
        jobject buffer) {
    // M0：无 StatusFrame 生产者，直接返回 0（UI 侧按 seq 不更新处理）
    return 0;
}

JNIEXPORT void JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeSetParams(JNIEnv* env, jobject thiz,
        jstring paramsJson) {
    const char* p = paramsJson ? env->GetStringUTFChars(paramsJson, nullptr) : "{}";
    ALOGI("nativeSetParams params=%s", p);
    if (paramsJson) env->ReleaseStringUTFChars(paramsJson, p);
}

} // extern "C"
