/**
 * lbj_jni.cpp — JNI 契约实现（严格 6 个 native 方法，见 LbjNative.kt）
 *
 *   nativeInit(paramsJson) / nativeStart(sourceFd, mode, freqHz, sampleRate, gainCentiDb, ppm)
 *   nativeStop() / nativeRelease() / nativeReadSpectrum(bb) / nativeSetParams(paramsJson)
 *
 * 回调（native→Kotlin）只有 2 个：onDecodeEventFromNative(json)、onLogFromNative(msg)。
 * 回调可能来自 USB 读线程 / DSP 线程：内部 AttachCurrentThread，Kotlin 对象持全局引用。
 *
 * mode: 0 = USB（fd 来自 UsbDeviceConnection.getFileDescriptor()，librtlsdr 直连）
 *       1 = pipe（fd 为 socketpair/管道读端，RtlTcp/Owrx 网络源经 Kotlin 桥接写入）
 */
#include <jni.h>
#include <android/log.h>
#include <cstring>
#include <mutex>
#include "core/engine.h"

#define LOG_TAG "LBJ"
#define ALOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define ALOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace {

JavaVM* g_vm = nullptr;
jobject g_cbObj = nullptr;      // LbjNative 单例的全局引用
jmethodID g_logMid = nullptr;
jmethodID g_decodeMid = nullptr;
std::mutex g_mutex;             // 引擎生命周期串行化

JNIEnv* attachEnv() {
    JNIEnv* env = nullptr;
    if (!g_vm) return nullptr;
    if (g_vm->GetEnv((void**)&env, JNI_VERSION_1_6) == JNI_OK) return env;
    if (g_vm->AttachCurrentThread(&env, nullptr) == JNI_OK) return env;
    return nullptr;
}

// native 线程 → Kotlin 日志
void nativeLogCb(const char* msg) {
    JNIEnv* env = attachEnv();
    if (!env || !g_cbObj || !g_logMid) return;
    jstring jmsg = env->NewStringUTF(msg ? msg : "");
    if (jmsg) {
        env->CallVoidMethod(g_cbObj, g_logMid, jmsg);
        env->DeleteLocalRef(jmsg);
    }
    if (env->ExceptionCheck()) env->ExceptionClear();
}

// native 线程 → Kotlin 解码事件（JSON 与桌面版 DecodeResult.toDict() 字段同名）
void nativeDecodeCb(const char* json) {
    JNIEnv* env = attachEnv();
    if (!env || !g_cbObj || !g_decodeMid) return;
    jstring jjson = env->NewStringUTF(json ? json : "{}");
    if (jjson) {
        env->CallVoidMethod(g_cbObj, g_decodeMid, jjson);
        env->DeleteLocalRef(jjson);
    }
    if (env->ExceptionCheck()) env->ExceptionClear();
}

} // namespace

extern "C" {

JNIEXPORT jint JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeInit(JNIEnv* env, jobject thiz, jstring paramsJson) {
    std::lock_guard<std::mutex> lock(g_mutex);

    // 缓存 VM 与回调（LbjNative 单例生命周期与应用进程一致）
    if (!g_vm) env->GetJavaVM(&g_vm);
    if (!g_cbObj) g_cbObj = env->NewGlobalRef(thiz);
    if (!g_logMid || !g_decodeMid) {
        jclass cls = env->GetObjectClass(thiz);
        g_logMid = env->GetMethodID(cls, "onLogFromNative", "(Ljava/lang/String;)V");
        g_decodeMid = env->GetMethodID(cls, "onDecodeEventFromNative", "(Ljava/lang/String;)V");
        env->DeleteLocalRef(cls);
    }

    auto& eng = lbj::LbjEngine::instance();
    eng.logFn = &nativeLogCb;
    eng.decodeFn = &nativeDecodeCb;

    const char* p = paramsJson ? env->GetStringUTFChars(paramsJson, nullptr) : "{}";
    ALOGI("nativeInit params=%s", p);
    int rc = eng.init(p);
    if (paramsJson) env->ReleaseStringUTFChars(paramsJson, p);

    if (rc == 0) {
        ALOGI("native init ok");
        nativeLogCb("native init ok");
    }
    return rc;
}

JNIEXPORT jint JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeStart(JNIEnv* env, jobject thiz,
        jint sourceFd, jint mode, jlong freqHz, jint sampleRate,
        jint gainCentiDb, jint ppm) {
    std::lock_guard<std::mutex> lock(g_mutex);
    ALOGI("nativeStart fd=%d mode=%d freqHz=%lld sr=%d gain=%d.%02ddB ppm=%d",
          sourceFd, mode, (long long)freqHz, sampleRate, gainCentiDb / 100, gainCentiDb % 100, ppm);
    auto& eng = lbj::LbjEngine::instance();
    if (!eng.inited()) {
        ALOGE("nativeStart before init");
        return -1;
    }
    int rc = eng.start(mode, sourceFd, freqHz, sampleRate, gainCentiDb, ppm);
    if (rc != 0) {
        char buf[96];
        snprintf(buf, sizeof(buf), "nativeStart 失败 rc=%d", rc);
        nativeLogCb(buf);
    }
    return rc;
}

JNIEXPORT void JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeStop(JNIEnv* env, jobject thiz) {
    std::lock_guard<std::mutex> lock(g_mutex);
    ALOGI("nativeStop");
    lbj::LbjEngine::instance().stop();
}

JNIEXPORT void JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeRelease(JNIEnv* env, jobject thiz) {
    std::lock_guard<std::mutex> lock(g_mutex);
    lbj::LbjEngine::instance().release();
    ALOGI("nativeRelease");
    // 不删除全局引用：单例对象与进程同生命周期，避免回调竞态
}

JNIEXPORT jint JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeReadSpectrum(JNIEnv* env, jobject thiz,
        jobject buffer) {
    // buffer 为 direct ByteBuffer（≥ 208 字节），由 Kotlin StatusFramePoller 轮询
    auto* addr = static_cast<int32_t*>(env->GetDirectBufferAddress(buffer));
    if (!addr) return 0;
    return lbj::LbjEngine::instance().readSpectrum(addr);
}

JNIEXPORT void JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeSetParams(JNIEnv* env, jobject thiz,
        jstring paramsJson) {
    const char* p = paramsJson ? env->GetStringUTFChars(paramsJson, nullptr) : "{}";
    ALOGI("nativeSetParams params=%s", p);
    lbj::LbjEngine::instance().setParams(p);
    if (paramsJson) env->ReleaseStringUTFChars(paramsJson, p);
}

extern "C" JNIEXPORT jstring JNICALL
Java_xyz_mlxkj_crlbj_engine_LbjNative_nativeProbeTuner(JNIEnv* env, jobject /*thiz*/,
                                                       jint fd) {
    std::string json = lbj::LbjEngine::probeTuner((int)fd);
    return env->NewStringUTF(json.c_str());
}


} // extern "C"
