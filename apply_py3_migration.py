#!/usr/bin/env python3
"""
Apply the MysticMine Python 2 → 3 migration.
Run from the repo root: python3 apply_py3_migration.py
"""
import glob
import os
import re
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.abspath(__file__))


def write(path, content):
    full = os.path.join(ROOT, path)
    with open(full, "w") as f:
        f.write(content)
    print(f"  wrote {path}")


def read(path):
    full = os.path.join(ROOT, path)
    with open(full) as f:
        return f.read()


def patch(path, old, new, count=0):
    full = os.path.join(ROOT, path)
    src = read(path)
    if old not in src:
        print(f"  WARN: pattern not found in {path}: {old!r:.60}")
        return
    result = src.replace(old, new, count or 0) if count else src.replace(old, new)
    with open(full, "w") as f:
        f.write(result)
    print(f"  patched {path}")


def re_patch(path, pattern, replacement, flags=0):
    full = os.path.join(ROOT, path)
    src = read(path)
    result, n = re.subn(pattern, replacement, src, flags=flags)
    if n == 0:
        print(f"  WARN: regex not found in {path}: {pattern!r:.60}")
        return
    with open(full, "w") as f:
        f.write(result)
    print(f"  patched {path} ({n} replacement(s))")

# ── Step 1: New files ────────────────────────────────────────────────────────


print("\n[1] Creating new files")

write("pyproject.toml", textwrap.dedent("""\
    [build-system]
    requires = ["setuptools>=68", "cython>=3.0", "wheel"]
    build-backend = "setuptools.build_meta"

    [project]
    name = "mysticmine"
    version = "1.2.0"
    description = "A fun and addictive single-switch mining game"
    requires-python = ">=3.13"
    dependencies = [
        "pygame>=2.5",
        "numpy>=1.26",
        "cython>=3.0",
        "pillow>=10.0",
    ]

    [project.optional-dependencies]
    dev = ["pytest>=7.4"]

    [tool.pytest.ini_options]
    testpaths = ["monorail/tests", "monorail/koon/tests"]
"""))

write("setup.py", textwrap.dedent("""\
    from setuptools import setup, Extension
    from Cython.Build import cythonize

    ext = Extension("monorail.ai", ["monorail/ai.pyx"])
    setup(ext_modules=cythonize([ext], language_level=3))
"""))

# ── Step 2: 2to3 ─────────────────────────────────────────────────────────────

print("\n[2] Running 2to3")
# lib2to3 was removed from the Python 3.13 stdlib. Find 2to3 from a pyenv 3.11/3.12 install.
pyenv_root = os.path.expanduser("~/.pyenv/versions")
candidates = sorted(
    glob.glob(os.path.join(pyenv_root, "3.1[12]*", "bin", "2to3")), reverse=True
)
if not candidates:
    sys.exit("No Python with 2to3 found in pyenv. Run: pyenv install 3.12.x")
two_to_three = candidates[0]
print(f"  using {two_to_three}")
result = subprocess.run(
    [two_to_three, "-w", "-n", "monorail/", "build.py"],
    cwd=ROOT, capture_output=True, text=True
)
if result.returncode != 0:
    print(result.stderr[-2000:])
    sys.exit("2to3 failed")
print("  done")

# ── Step 3: Fix invalid koon imports produced by 2to3 ────────────────────────

print("\n[3] Fixing invalid 'from . import koon.X' imports")
replacements = [
    ("from . import koon.gfx as gfx", "from .koon import gfx"),
    ("from . import koon.input as input", "from .koon import input"),
    ("from . import koon.snd as snd", "from .koon import snd"),
    ("from . import koon.geo as geo", "from .koon import geo"),
    ("from . import koon.gui as gui", "from .koon import gui"),
    ("from . import koon.app", "from .koon import app"),
]
for dirpath, _, filenames in os.walk(os.path.join(ROOT, "monorail")):
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        fpath = os.path.join(dirpath, fn)
        src = open(fpath).read()
        changed = src
        for old, new in replacements:
            changed = changed.replace(old, new)
        if changed != src:
            open(fpath, "w").write(changed)
            print(f"  fixed {os.path.relpath(fpath, ROOT)}")

# ── Step 4: Fix 2to3 false-positive: event.unicode (pygame attr) ─────────────

print("\n[4] Fixing event.str → event.unicode in koon/app.py")
patch("monorail/koon/app.py", "event.str", "event.unicode")

# ── Step 5: Manual fixes not covered by 2to3 ─────────────────────────────────

print("\n[5] Manual fixes")

# geo.py: __div__ → __truediv__
patch("monorail/koon/geo.py",
      "def __div__(self, factor):\n        return Vec3D",
      "def __truediv__(self, factor):\n        return Vec3D")
patch("monorail/koon/geo.py",
      "def __div__(self, factor):\n        return Vec2D",
      "def __truediv__(self, factor):\n        return Vec2D")

# world.py: add functools import and fix sort
src = read("monorail/world.py")
if "import functools" not in src:
    src = src.replace("import random\n", "import random\nimport functools\n", 1)
    open(os.path.join(ROOT, "monorail/world.py"), "w").write(src)
    print("  added functools import to world.py")
patch("monorail/world.py",
      "self.tiles.sort( tilesort )",
      "self.tiles.sort(key=functools.cmp_to_key(tilesort))")

# settings.py: cmp() sort lambda
patch("monorail/settings.py",
      "single_ranking.sort( lambda a, b: cmp( b.score, a.score ) )",
      "single_ranking.sort(key=lambda a: a.score, reverse=True)")

# monorail/monorail.py: remove gettext.install(True, ...) line
re_patch("monorail/monorail.py",
         r"gettext\.install\s*\(True.*?\)\n", "")

# koon/build.py: Pillow API + integer division
patch("monorail/koon/build.py", "Image.ANTIALIAS", "Image.Resampling.LANCZOS")
patch("monorail/koon/build.py",
      "((len(images)-1) / 10 + 1)",
      "((len(images)-1) // 10 + 1)")
patch("monorail/koon/build.py",
      "(len(images) / 10) + 1",
      "(len(images) // 10) + 1")

# ai.pyx: bare imports, <>, print, integer //
pyx = read("monorail/ai.pyx")
pyx = pyx.replace("import tiles\nimport pickups",
                  "from monorail import tiles, pickups", 1)
pyx = pyx.replace("<>", "!=")
pyx = pyx.replace('print "playfieldstate shouldn\'t be None in real game"',
                  'print("playfieldstate shouldn\'t be None in real game")')
pyx = pyx.replace("CYCLES_PER_UPDATE*2/3", "CYCLES_PER_UPDATE*2//3")
pyx = pyx.replace("CYCLES_PER_UPDATE*1/3", "CYCLES_PER_UPDATE*1//3")
open(os.path.join(ROOT, "monorail/ai.pyx"), "w").write(pyx)
print("  patched monorail/ai.pyx")

# MysticMine entry script: shebang + print
patch("MysticMine",
      "#!/usr/bin/env python2",
      "#!/usr/bin/env python3", 1)
patch("MysticMine",
      'print "Error: ai module not present. Run \'make\' first!"',
      'print("Error: ai module not present. Run \'make\' first!")')

# Makefile
mf = read("Makefile")
mf = mf.replace("@python2 setup.py build_ext --inplace",
                "@poetry run python setup.py build_ext --inplace")
mf = mf.replace("@python2 setup.py clean\n\t", "")
mf = mf.replace("@python2 setup.py install", "poetry install")
mf = mf.replace("@python2 setup.py sdist", "@poetry run python setup.py sdist")
mf = mf.replace("rebuild-all: clean\n\t@python2 setup.py build_ext --inplace\n\t@python2 build.py",
                "rebuild-all: clean all\n\t@poetry run python build.py")
open(os.path.join(ROOT, "Makefile"), "w").write(mf)
print("  patched Makefile")

if not os.path.exists(os.path.join(ROOT, ".python-version")):
    write(".python-version", "3.13.3\n")

print("\nDone. Review changes with: git diff")
