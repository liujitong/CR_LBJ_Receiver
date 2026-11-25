/* config.h — libusb 1.0.27 @ Android NDK (bionic, minSdk 26) 手工生成
 * 依据 config.h.in 的检查项，按 bionic API 26 实际能力定义 */
#ifndef LIBUSB_CONFIG_H
#define LIBUSB_CONFIG_H 1

/* 平台 */
#define PLATFORM_POSIX 1
#define DEFAULT_VISIBILITY __attribute__ ((visibility ("default")))
#define PRINTF_FORMAT(a, b) __attribute__ ((__format__ (__printf__, a, b)))
#define _GNU_SOURCE 1

/* 日志 */
#define ENABLE_LOGGING 1
/* #undef ENABLE_DEBUG_LOGGING */
#define USE_SYSTEM_LOGGING_FACILITY 1

/* 头文件 */
#define HAVE_ASM_TYPES_H 1
#define HAVE_DLFCN_H 1
#define HAVE_INTTYPES_H 1
#define HAVE_STDINT_H 1
#define HAVE_STDIO_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRINGS_H 1
#define HAVE_STRING_H 1
#define HAVE_SYS_STAT_H 1
#define HAVE_SYS_TIME_H 1
#define HAVE_SYS_TYPES_H 1
#define HAVE_UNISTD_H 1
#define HAVE_SYSLOG 1

/* 能力 */
#define HAVE_CLOCK_GETTIME 1
#define HAVE_NFDS_T 1
#define HAVE_PIPE 1
#define HAVE_PIPE2 1
#define HAVE_EVENTFD 1
#define HAVE_TIMERFD 1
#define HAVE_PTHREAD_CONDATTR_SETCLOCK 1
#define HAVE_PTHREAD_SETNAME_NP 1
#define HAVE_STRUCT_TIMESPEC 1

/* eventfd/timerfd 标志宏（bionic sys/eventfd.h、sys/timerfd.h 均已提供） */
#define HAVE_DECL_EFD_CLOEXEC 1
#define HAVE_DECL_EFD_NONBLOCK 1
#define HAVE_DECL_TFD_CLOEXEC 1
#define HAVE_DECL_TFD_NONBLOCK 1

/* Linux 后端（netlink 热插拔；不用 udev） */
#define HAVE_LINUX_NETLINK_H 1
/* #undef HAVE_LIBUDEV */
/* #undef USE_UDEV */

#endif /* LIBUSB_CONFIG_H */
