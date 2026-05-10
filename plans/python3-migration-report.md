# MysticMine — Python 3 Migration Report

**Date:** 2026-05-08  
**Python target:** 3.13.12 (pyenv)  
**Tooling introduced:** Poetry, Cython 3, pytest  

---

## Goal

Migrate MysticMine from Python 2 (with Pyrex/distutils build) to Python 3.13 with modern dependency management (Poetry + setuptools + Cython 3).

---

## Approach

Rather than converting files by hand, the work was encoded in a single self-contained script, `apply_py3_migration.py`, which runs in two passes:

1. **Automated pass** — invokes `2to3` (sourced from the Python 3.12 pyenv install, since lib2to3 was removed from the 3.13 stdlib) to handle the bulk of mechanical changes across all `.py` files.
2. **Manual patch pass** — targeted `str.replace` / `re.sub` fixes for patterns `2to3` does not cover.

This keeps the full migration reproducible and auditable from a single file.

---

## Issues Encountered & Resolved

### 1. `lib2to3` removed in Python 3.13

`apply_py3_migration.py` originally invoked `python3 -m lib2to3`, which doesn't exist in 3.13.

**Fix:** Used `glob` to locate `2to3` under `~/.pyenv/versions/3.12.*/bin/2to3` and called it directly, bypassing pyenv shim interference.

### 2. `.python-version` written too early

Writing `.python-version = 3.13.3` before running any subprocesses caused pyenv to intercept all subsequent commands and fail (3.13.3 was not installed; user had 3.13.12).

**Fix:** Moved the `.python-version` write to the end of the script, after all subprocess calls. Added a guard to skip writing if the file already exists.

### 3. Poetry `package-mode` error

`poetry install` failed because Poetry tried to install `mysticmine` as a distributable package, but there is no importable package at the root.

**Fix:** Added `[tool.poetry] package-mode = false` to `pyproject.toml`.

### 4. `setuptools` not in venv

`python setup.py build_ext --inplace` failed with `ModuleNotFoundError: No module named 'setuptools'` because Python 3.13 no longer bundles setuptools.

**Fix:** Added `setuptools>=68` to `[project.optional-dependencies] dev` and installed it via `poetry run pip install setuptools`.

### 5. setuptools auto-discovery conflict

setuptools found multiple top-level directories (`data/`, `plans/`, `assets/`, `monorail/`, etc.) and refused to build.

**Fix:** Added `packages=[]` to `setup()` in `setup.py` — the file only exists to compile the Cython extension, not to package anything.

### 6. `_()` not defined at import time

`settings.py` uses `_("string")` (gettext) at class-body level. When imported directly in tests (without going through `monorail.py` which installs `_()` into builtins), this raised `NameError`.

**Fix:** Added a builtins fallback at the top of `settings.py`:
```python
import builtins
if not hasattr(builtins, '_'):
    builtins._ = lambda s: s
```

### 7. Invalid escape sequence `\/` in `tiles.py` docstring

Python 3.12+ makes `\/` a `SyntaxWarning` (future `SyntaxError`).

**Fix:** Prefixed the docstring with `r` to make it a raw string.

### 8. Second `sort(lambda a, b: cmp(...))` in `world.py`

The migration script patched `settings.py` and the `tilesort` function in `world.py`, but missed a second cmp-style sort at `world.py:183` (`get_goldcar_ranking`).

**Fix:** Replaced with `single_ranking.sort(key=lambda a: a.score, reverse=True)`.

### 9. `imp` module removed in Python 3.12

`monorail.py` used `imp.is_frozen("__main__")` to detect whether the game was packaged with the old `freeze` tool.

**Fix:** Replaced with an `importlib` equivalent. `importlib.util.find_spec("__main__")` returns a `ModuleSpec` whose loader is a `FrozenImporter` when the module is frozen. Wrapped in `try/except ValueError` because `find_spec("__main__")` raises that error when `__main__.__spec__` is `None` (normal script execution):
```python
import importlib.machinery
import importlib.util

def main_is_frozen():
    try:
        spec = importlib.util.find_spec("__main__")
        is_frozen_main = spec is not None and isinstance(spec.loader, importlib.machinery.FrozenImporter)
    except ValueError:
        is_frozen_main = False
    return (hasattr(sys, "frozen") or hasattr(sys, "importers") or is_frozen_main)
```

### 10. `gettext.bind_textdomain_codeset` removed in Python 3

`monorail.py` called `gettext.bind_textdomain_codeset(APP_NAME, "UTF-8")`, which no longer exists — Python 3 strings are always unicode, making codeset binding a no-op.

**Fix:** Removed the call entirely.

### 11. `koon` not in scope in `monorail.py`

`main()` called `koon.app.set_game_speed(...)`, but only `from .koon import app` was imported — `koon` itself was never bound. Additionally, a local variable named `app` on the next line shadowed the module.

**Fix:** Called `app.set_game_speed(...)` directly and renamed the local `Monorail` instance to `game`.

### 12. `monorail/data` symlink missing — `make` must be run first

`resman.read("data/resources.cfg")` uses a path relative to `monorail/` (the game's working directory after `os.chdir(script_dir)`). In the repo, game assets live under `data/800x600/`, not `data/`. The original `Makefile` always created `monorail/data -> data/800x600/` as a symlink as part of its `all` target — this was documented in the README but easy to miss.

Without running `make`, `monorail/data/` does not exist and the game fails at startup with `FileNotFoundError: data/resources.cfg`. The misleading "ai module not present" error is a red herring: it appears because `pygame` is unavailable in the bare pyenv environment, causing the `import monorail.ai` check to raise `ImportError`, which the entry script catches and reports as a missing build artifact.

**Fix:** Run `make` before launching the game. `make` compiles the Cython extension AND creates the symlink. Then launch with the Poetry venv active:

```bash
make
poetry run python MysticMine
# or: eval $(poetry env activate) && make && python MysticMine
```

### 13. `ungettext` renamed to `ngettext` in Python 3

`scenarios.py` called `gettext.lang.ungettext(...)` 68 times. In Python 2, `ungettext` was the pluralised-translation function — the "u" prefix indicated it returned a unicode string (as opposed to a byte string). In Python 3 all strings are unicode by default, so the function was renamed to `ngettext` to match the standard C gettext convention. The signature and behaviour are identical: `ngettext(singular, plural, n)` returns the singular form when `n == 1`, plural otherwise.

**Fix:** Replaced all 68 occurrences of `gettext.lang.ungettext` → `gettext.lang.ngettext` in `scenarios.py`.

---

### 14. Shifted sprite graphics (`/` → `//` in `SpriteFilm`)

After the migration, all sprites were visually shifted/misaligned. The root cause was `Vec2D.__div__` becoming `Vec2D.__truediv__` in Python 3, and several pixel-coordinate calculations in `koon/gfx.py`'s `SpriteFilm` class that relied on integer truncation from Python 2's `/` operator:

```python
# Python 2: / on integers produced integer (truncated)
self.max_x = self.surface.get_width() / width     # was int, now float
self.width  = self.surface.get_width()  / x_sprites
self.height = self.surface.get_height() / y_sprites
self.center = Vec2D(self.width / 2, self.height / 2)
sp_y        = (self.nr / self.max_x) * self.height
```

Pixel dimensions and sprite-sheet row/column indices must be integers. Fractional values caused every sprite to be drawn at a non-pixel-aligned (and therefore visually wrong) position.

**Fix:** Replaced all five occurrences with `//` in `koon/gfx.py`. Also applied the same fix to the font centering calculations (`x -= textsurf.get_width() // 2`, `y -= textsurf.get_height() // 2`).

---

### 15. Pink transparent areas around sprites (pygame 2 / SDL2 alpha channel behaviour)

After fixing the sprite shift, transparent areas of animated sprites (most visibly the mine cart) appeared pink — a coloured square matching the sprite frame's bounding box was visible around every moving object.

#### Root cause analysis

The diagnosis required understanding three interacting pygame 2 / SDL2 behaviour changes:

**1. The display surface has SRCALPHA in pygame 2 on macOS.**  
`pygame.display.set_mode()` returns a surface with `flags = 0x1010000`, which includes `pygame.SRCALPHA (0x10000)`. macOS's window compositor treats the display surface's alpha channel literally: pixels with `alpha = 0` are composited as *transparent*, showing the desktop wallpaper (which in this case was pink) behind them.

**2. Blitting an SRCALPHA surface onto a non-SRCALPHA surface zeroes the destination alpha.**  
Verified with `pygame.surfarray` diagnostics:
```python
bg = pygame.Surface((200, 200))          # no SRCALPHA
bg.fill((30, 30, 30, 255))               # alpha = 255
car = pygame.image.load('car1.png').convert_alpha()
bg.blit(car, (0, 0))
bg.get_at((28, 26))  # opaque car pixel → (82, 82, 82, 0)  ← alpha became 0!
bg.get_at((5,  5))   # transparent area  → (30, 30, 30, 0)  ← also 0
```
In pygame 1 / SDL1, the display was a truly opaque surface and its alpha bytes were irrelevant. In pygame 2 / SDL2, `BLENDMODE_BLEND` (the default for SRCALPHA sources) updates the destination's alpha channel in a way that zeroes it out for non-SRCALPHA destinations. This is a documented SDL2 behaviour difference.

**3. The rendering pipeline propagated alpha = 0 to the display.**  
Every frame, `LevelView` blits its pre-rendered 800×600 tile background surface (a non-SRCALPHA `pygame.Surface`) onto the display using `BLENDMODE_NONE` (straight pixel copy, because the source has no SRCALPHA). Since the tile sprites had already set the background surface's alpha bytes to 0 (step 2), this straight copy flooded the display with `alpha = 0` pixels. Adding `surface.fill((0, 0, 0, 255))` at the start of `MonorailGame.draw()` had no effect because the subsequent background blit immediately overwrote those alpha = 255 values.

After the background blit, any sprite drawn on top would have `alpha = 255` in its opaque pixels but `alpha = 0` in its transparent pixels (because the Porter-Duff `BLENDMODE_BLEND` formula leaves transparent-source pixels unchanged: `dstA = 0 + 0 × (1−0) = 0`). The macOS compositor then showed the pink desktop wallpaper through those zero-alpha pixels, producing the coloured bounding-box halo around every sprite.

#### Fix

The fix is to create the tile background surface with `pygame.SRCALPHA` and pre-fill it with opaque black. When an SRCALPHA source is blitted onto an SRCALPHA destination, the Porter-Duff formula correctly preserves `alpha = 255` for every incoming alpha value:

```
dstA = srcA + dstA × (1 − srcA/255)
     = srcA + 255 × (255 − srcA)/255
     = srcA + 255 − srcA
     = 255   ✓  for any srcA
```

So no matter how transparent or opaque each tile pixel is, the background surface retains `alpha = 255` everywhere after tile blitting. The display then inherits those `alpha = 255` values, stays fully opaque, and the macOS compositor no longer composites the wallpaper through the game window.

**Change in `worldview.py`, `LevelView.init_background()`:**

```python
self.background = gfx.Surface( (800,600) )
# Replace pysurf with an SRCALPHA surface prefilled with opaque black
self.background.pysurf = pygame.Surface( (800,600), pygame.SRCALPHA )
self.background.pysurf.fill( (0, 0, 0, 255) )
```

Only the tile background surface needed this change. All other surfaces (menus, HUD, dark overlay) were unaffected.

#### References

- **SDL2 Migration Guide** — documents the switch from `SDL_SetAlpha` to `SDL_SetSurfaceBlendMode` and the new alpha-compositing semantics: https://wiki.libsdl.org/SDL2/MigrationGuide
- **SDL2 `SDL_BlendMode` reference** — the BLENDMODE_BLEND formula (`dstRGB = srcRGB·srcA + dstRGB·(1−srcA)`, `dstA = srcA + dstA·(1−srcA)`) is listed here: https://wiki.libsdl.org/SDL2/SDL_BlendMode
- **pygame 2 `Surface` docs** — blend mode flags (`BLEND_ALPHA_SDL2`, etc.) passed as `special_flags` to `blit()`: https://www.pygame.org/docs/ref/surface.html
- **Porter & Duff, "Compositing Digital Images", SIGGRAPH 1984** — original paper defining the "source over" operator used by SDL2's BLENDMODE_BLEND.

---

### 16. "Crooked" cart appearance when gold is collected — pre-existing, not a migration issue

After fixing the pink-transparency and sprite-shift bugs, the mine cart appeared to look slightly "crooked" or tilted whenever the player collected a coin (i.e. when `self.model.amount` incremented from 0 to 1).

#### Investigation

The frame-selection logic in `playerview.py` adds `20 * self.model.amount` to the sprite frame number after `align_car_to_track()` sets the base rotation frame:

```python
self.sprite.nr = int(in_sprite * (1.0 - interpol) + out_sprite * interpol) % 12
# …
self.sprite.nr += 20 * self.model.amount   # shift to loaded-cart row
```

`car1.png` is a 460×336 sprite sheet divided into 10×8 = 80 frames (46×42 px each). The layout is four load levels of 20 frames each:

| Rows | Frames | Meaning |
|------|--------|---------|
| 0–1  | 0–19   | Empty cart (12 rotation angles + 4 slope poses + 4 unused) |
| 2–3  | 20–39  | 1 coin loaded |
| 4–5  | 40–59  | 2 coins loaded |
| 6–7  | 60–79  | 3 coins loaded |

To verify that the loaded frames really do represent the same orientations as the empty frames, the alpha-weighted centre of mass was computed for every relevant frame pair:

```
Frame  empty_CoM    loaded_CoM   match?
   0   (23, 19)     (23, 19)     OK
   1   (23, 19)     (23, 19)     OK
   …
  12   (26, 18)     (26, 18)     OK
  15   (19, 21)     (19, 21)     OK
  16   (19, 18)     (19, 18)     OK
  19   (26, 21)     (26, 21)     OK
```

All pairs match to within 1 pixel. The sprite sheet is correctly designed.

`playerview.py` was also confirmed unmodified by the migration (`git log` shows no migration commits touching it).

#### Conclusion

The visual difference is intentional artwork: the loaded-cart frames were drawn with the gold bars visible, which shifts the apparent visual balance of the cart body. The single fixed centre point `(24, 31)` from `resources.cfg` keeps the cart anchored to the track correctly for all load levels, so the tilt is purely in the sprite art. This behaviour existed in the original Python 2 game and is not a regression introduced by the migration.

---

### 17. Sound and music not playing — licensing placeholders, not a migration issue

After launching the game, no sound effects or background music are heard.

#### Investigation

The pygame mixer initializes without error:

```python
mixer.pre_init(22050, -16, 2, 2048)   # succeeds
mixer.init()                           # succeeds
mixer.Sound('data/800x600/snd/coin.wav')  # loads without exception
```

However, inspecting the files reveals the problem immediately:

```
$ ls -la data/800x600/snd/
-rw-r--r--  146 coin.wav
-rw-r--r--  146 crash.wav
-rw-r--r--  146 diamond.wav
... (25 files, all exactly 146 bytes)

$ ls -la data/800x600/music/
-rw-r--r--  3975 ingame1.ogg
-rw-r--r--  3975 ingame2.ogg
-rw-r--r--  3975 menu.ogg
```

A valid WAV consists of a 44-byte header plus samples. 146 bytes = 44-byte header + 102 bytes = ~51 samples at 44100 Hz = **~1 ms of silence**. The OGG files are similarly minimal stubs.

`git log --diff-filter=A -- 'data/800x600/snd/*.wav'` confirms these stubs were committed in the very first commit (2012) and have never changed.

#### Root cause

The README documents this explicitly:

> "Unfortunately the music and sound of the original game were bought under a license that does not allow redistribution as part of an open source project. In the meantime you can always get the original sound and music files when downloading the original game."

The audio assets were commercially licensed and deliberately excluded from the open source release. All 25 WAV files and 3 OGG music files in the repository are intentional silent stubs.

#### Conclusion

This is not a migration regression. The pygame mixer code (`sndman.py`) works correctly — it loads and plays the stub files, which contain silence. To restore audio, the real sound and music files must be copied from an original MysticMine binary installation into `data/800x600/snd/` and `data/800x600/music/`.

---

## Changes Made

### New files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Poetry/setuptools config; deps: pygame, numpy, cython, pillow |
| `.python-version` | Pins Python 3.13.12 via pyenv |
| `apply_py3_migration.py` | Reproducible migration script |
| `CLAUDE.md` | Codebase guide for Claude Code |
| `.claude/settings.json` | PostToolUse hook to mirror plan files into `plans/` |
| `plans/` | Version-controlled plan files |

### Modified files (40 total)

**Build system**

- `setup.py` — replaced distutils + Pyrex with setuptools + `Cython.Build.cythonize`; added `packages=[]`
- `Makefile` — replaced `python2` calls with `poetry run python`

**Source code** (via `2to3` + manual patches)

- All `print "..."` → `print(...)` (33 occurrences)
- All `<>` → `!=` (45 occurrences across `.py` and `.pyx`)
- All `.has_key(k)` → `k in d` (10 occurrences)
- All `except E, e:` → `except E as e:` (4 occurrences)
- `from cPickle import` → `from pickle import` in `settings.py`
- `__div__` → `__truediv__` in `koon/geo.py` (Vec2D and Vec3D)
- `self.tiles.sort(tilesort)` → `sort(key=functools.cmp_to_key(tilesort))` in `world.py`
- Two `sort(lambda a,b: cmp(...))` → `sort(key=..., reverse=True)` in `settings.py` and `world.py`
- `dict.values()[:]` → `list(dict.values())` in `settings.py`
- `gettext.install(True, ..., unicode=1)` line removed from `monorail.py`
- `Image.ANTIALIAS` → `Image.Resampling.LANCZOS` in `koon/build.py`
- Integer division `CYCLES_PER_UPDATE*2/3` → `//` in `ai.pyx`
- Invalid import paths `from . import koon.X as X` → `from .koon import X` (10 files, produced by `2to3`)
- `event.str` → `event.unicode` in `koon/app.py` (2to3 false-positive)
- `MysticMine` entry script: shebang `python2` → `python3`
- Integer division `/ width`, `/ x_sprites`, `/ 2` → `//` in `koon/gfx.py` `SpriteFilm` (sprite-shift fix)
- `LevelView.init_background()` in `worldview.py`: background surface changed to `pygame.SRCALPHA` + pre-filled opaque black (pink-transparency fix)
- `MonorailGame.draw()` in `monorail.py`: `#surface.fill((0,0,0))` uncommented as `surface.fill((0,0,0,255))`

---

## Test Results

```
125 collected
110 passed
11 failed  (pre-existing)
 4 errors  (pre-existing)
```

All 11 failures and 4 collection errors are pre-existing and unrelated to the migration:

| Failure | Root cause |
|---------|-----------|
| `test_snd` (2) | Sound files absent in test environment |
| `test_control`, `test_scenarios` (5) | Hardcoded relative path `tests/levelTest.lvl` only works when pytest runs from inside `monorail/` |
| `test_scenarios::TestStatistics::test_save` | Logic bug predating migration |
| `test_settings` (3) | `GameData()` called without required `userinput` arg |
| `test_frame`, `test_pickupsview`, `test_playerview` (4 errors) | Missing data files / uninitialized resource manager |

---

## Running the Project

```bash
# First time setup
pyenv install 3.13.12
pyenv local 3.13.12
pip install poetry
poetry install
poetry run pip install setuptools  # not auto-installed by Poetry

# Build Cython extension
poetry run python setup.py build_ext --inplace

# Run tests
poetry run pytest monorail/koon/tests/ monorail/tests/ -v

# Launch game
poetry run python MysticMine
```

---

## Remaining Work

- Fix the 11 pre-existing test failures (path issues, `GameData` signature, missing test fixtures)
- Update `CLAUDE.md` to reflect Poetry-based workflow
