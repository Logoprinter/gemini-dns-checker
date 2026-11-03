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

# p4a: С„РёРєСЃРёСЂСѓРµРј СЃС‚Р°Р±РёР»СЊРЅСѓСЋ РІРµСЂСЃРёСЋ (python3.11), РіРґРµ pip<24 СЃРѕС…СЂР°РЅСЏРµС‚
# capture_logging Рё СЃРѕР±РёСЂР°СЋС‚СЃСЏ recipes РёР· РёСЃС…РѕРґРЅРёРєРѕРІ Р±РµР· android-wheel РїСЂРѕР±Р»РµРј.
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 0