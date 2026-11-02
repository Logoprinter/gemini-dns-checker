[app]
title = DNS Checker
package.name = dnschecker
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = 0
android.private_storage = 1
android.add_src = false
# В docker-образе kivy/buildozer SDK/NDK/лицензии уже предустановлены и
# совместимы с p4a; явные пути не задаём — buildozer возьмёт свои.

[buildozer]
log_level = 2
warn_on_root = 1