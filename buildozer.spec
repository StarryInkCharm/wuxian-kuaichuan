[app]
# 应用元信息
title = 无线快传
package.name = wuxiankuaichuan
package.domain = com.wuxian.kuaichuan

# 源码目录 - Kivy 应用的 main.py 入口
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json,txt

# 版本
version = 1.0.0

# 应用权限 - 文件访问、网络、WiFi 状态
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE

# Android API 级别 - 较新以支持 Android 11+ 分区存储
android.api = 33
android.minapi = 24
android.sdk = 33
android.ndk = 25b

# Java / Python 版本
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a

# Python: Kivy 自带 python3
requirements = python3,kivy==2.3.1,aiohttp==3.10.11,Pillow

# 启动入口 - Kivy 应用
orientation = portrait
fullscreen = False

# Kivy 启动方向
p4a.bootstrap = sdl2
# develop 分支支持 AAB，buildozer 1.4.0 需要
p4a.branch = develop

# 图标 / 启动画面（可选）
# icon.filename = %(source.dir)s/assets/icon.png
# presplash.filename = %(source.dir)s/assets/presplash.png

# 调试信息
android.logcat_filters = *:S python:V
android.debug_jni = False

# 构建后清理
no-byte-compile-python = True

[buildozer]
log_level = 2
warn_on_root = 1
