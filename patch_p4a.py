import os
import sys

# p4a / buildozer РґРѕ СЃРёС… РїРѕСЂ РёРЅРѕРіРґР° РїР°РґР°СЋС‚ РЅР° pip>=24 РёР·-Р·Р° СѓРґР°Р»С‘РЅРЅС‹С…
# РїСЂРёРІР°С‚РЅС‹С… API (capture_logging, BuildDependencyInstallError). РЎС‚Р°РІРёРј
# СЃРѕРІРјРµСЃС‚РёРјС‹Рµ РІРµСЂСЃРёРё Рё РїР°С‚С‡РёРј РѕСЃС‚Р°С‚РєРё РІ p4a, С‡С‚РѕР±С‹ РЅРµ С‚СЂРѕРіР°С‚СЊ С‡СѓР¶РѕР№ pip.

base = sys.argv[1] if len(sys.argv) > 1 else "."
found = []

for root, dirs, files in os.walk(base):
    if ".git" in root:
        continue
    for fn in files:
        if not fn.endswith(".py"):
            continue
        p = os.path.join(root, fn)
        try:
            with open(p, encoding="utf-8") as f:
                s = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        orig = s

        # 1) BuildDependencyInstallError РјРѕР¶РµС‚ РѕС‚СЃСѓС‚СЃС‚РІРѕРІР°С‚СЊ РІ РЅРѕРІС‹С… pip
        s = s.replace(
            "from pip._internal.exceptions import BuildDependencyInstallError",
            "import pip._internal.exceptions as _pie; "
            "BuildDependencyInstallError = getattr(_pie, "
            "'BuildDependencyInstallError', Exception)")

        # 2) capture_logging СѓРґР°Р»С‘РЅ РІ pip>=24. Р”Р°С‘Рј Р·Р°РіР»СѓС€РєСѓ.
        s = s.replace(
            "from pip._internal.utils.logging import VERBOSE, capture_logging",
            "import pip._internal.utils.logging as _l; "
            "VERBOSE = getattr(_l, 'VERBOSE', None); "
            "capture_logging = getattr(_l, 'capture_logging', "
            "lambda *a, **k: (lambda f: f))")

        if s != orig:
            with open(p, "w", encoding="utf-8") as f:
                f.write(s)
            found.append(p)

print("patched:", found)