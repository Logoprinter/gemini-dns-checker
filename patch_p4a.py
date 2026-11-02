import os
import sys

old = "from pip._internal.exceptions import BuildDependencyInstallError"
new = ("import pip._internal.exceptions as _pie; "
       "BuildDependencyInstallError = getattr(_pie, "
       "'BuildDependencyInstallError', Exception)")

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
        if old in s:
            with open(p, "w", encoding="utf-8") as f:
                f.write(s.replace(old, new))
            found.append(p)
print("patched:", found)