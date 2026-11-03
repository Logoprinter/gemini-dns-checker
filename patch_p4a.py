import os
import re
import sys

base = sys.argv[1] if len(sys.argv) > 1 else "."
found = []

def patch_file(p, old, new):
    try:
        with open(p, encoding="utf-8") as f:
            s = f.read()
    except (OSError, UnicodeDecodeError):
        return False
    if old in s:
        with open(p, "w", encoding="utf-8") as f:
            f.write(s.replace(old, new))
        return True
    return False


# 1) p4a: BuildDependencyInstallError РјРѕР¶РµС‚ РѕС‚СЃСѓС‚СЃС‚РІРѕРІР°С‚СЊ РІ РЅРѕРІС‹С… pip
old1 = "from pip._internal.exceptions import BuildDependencyInstallError"
new1 = ("import pip._internal.exceptions as _pie; "
        "BuildDependencyInstallError = getattr(_pie, "
        "'BuildDependencyInstallError', Exception)")

# 2) pip СЃР°Рј (installer.py) РІ pip>=24 РёРјРїРѕСЂС‚РёСЂСѓРµС‚ СѓРґР°Р»С‘РЅРЅС‹Р№ capture_logging
old2 = "from pip._internal.utils.logging import VERBOSE, capture_logging"
new2 = ("import pip._internal.utils.logging as _l; "
        "VERBOSE = getattr(_l, 'VERBOSE', None); "
        "capture_logging = getattr(_l, 'capture_logging', "
        "lambda *a, **k: (lambda f: f))")

for root, dirs, files in os.walk(base):
    if ".git" in root or "/.buildozer/" in root + "/":
        continue
    for fn in files:
        if not fn.endswith(".py"):
            continue
        p = os.path.join(root, fn)
        before = None
        try:
            with open(p, encoding="utf-8") as f:
                before = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        a = patch_file(p, old1, new1)
        b = patch_file(p, old2, new2)
        if a or b:
            found.append(p)

print("patched:", found)