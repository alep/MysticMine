# Plan: Blank Screen Debugging — pygbag Browser Port

## Context

The pygbag WASM build launches and shows the click-to-start prompt, but after clicking nothing renders. The most recent console error was `Unsupported device pixel ratio 2` (now patched via `devicePixelRatio` override). The new symptom is a completely blank canvas despite the loader completing. This plan lists the hypotheses in likelihood order and the concrete fix for each.

---

## Hypotheses (most → least likely)

### H1 — `NameError: languages` at module import time ← **most likely**

**File:** `monorail/monorail.py` lines 47–51

```python
lc, encoding = locale.getdefaultlocale()   # returns (None, None) in WASM
if lc:
    languages = [lc]          # skipped — lc is None
languages += DEFAULT_LANGUAGES # NameError: 'languages' not defined
```

In WASM/Emscripten there is no locale set, so `locale.getdefaultlocale()` returns `(None, None)`. `lc` is falsy so `languages` is never initialized, then the `+=` on the next line raises `NameError`. This crashes the `from monorail.monorail import async_main` import inside `main.py`. The error is caught by `main.py`'s try/except and `print()`-ed, but in pygbag that print goes to the `pyconsole` div which is small and easy to miss.

**Fix:** Initialize `languages = []` before the conditional.

```python
try:
    lc, encoding = locale.getdefaultlocale()
except Exception:
    lc = None
languages = [lc] if lc else []
languages += DEFAULT_LANGUAGES
```

---

### H2 — `gui_divider: 2` splits viewport 50/50 with terminal

**File:** `build/web-cache/27613e24ba16d44f2a5c88150c6d64e5.tmpl` line 151

```javascript
gui_divider : 2,   // hardcoded, not a template variable
gui_debug   : 2,   // hardcoded, not a template variable
```

`gui_divider: 2` tells pygbag to split the viewport between the game canvas (top half) and the Python terminal (bottom half). Even if the game renders correctly, the canvas may be scaled to only half the visible height and the terminal below it may show Python error tracebacks. `gui_debug: 2` keeps the terminal visible.

**Fix:** Set both to 1/0 in the template once debugging is complete. For now, keep `gui_debug: 2` so errors are visible — the terminal is the best debug tool we have.

```javascript
gui_divider : 1,   // game takes full viewport
gui_debug   : 0,   // hide terminal in production
```

---

### H3 — Exception inside `Monorail.__init__` / `before_gameloop`

**File:** `monorail/monorail.py` line 98

```python
def before_gameloop(self):
    resman.read("data/resources.cfg")
```

After `os.chdir(script_dir)` in `async_main()`, the CWD is `/data/data/mysticmine/assets/monorail/`. `resman.read("data/resources.cfg")` therefore resolves to `monorail/data/resources.cfg`. Since `build_web.sh` copies `data/800x600/` to `monorail/data/` before packing, this file should exist. **Low risk**, but if the path is wrong the game silently fails to load any sprites and renders nothing.

**Fix:** No change needed if H1 is confirmed. If still blank after H1 fix, add a print before/after `resman.read()`.

---

### H4 — `pygame.display.set_mode((800, 600))` doesn't update the canvas DOM element

In pygbag, SDL2 targets the `<canvas id="canvas">` element. If `set_mode()` fails silently, `pygame.display.get_surface()` returns `None` and `surface.blit()` throws an `AttributeError`. This is caught by the `except:` block in `_run_async`, `deinit_pygame()` is called, and the error is printed to the terminal.

**Fix:** Diagnosed automatically once H1 is fixed and errors become visible.

---

### H5 — `snd.pre_init()` called before `pygame.init()` stalls in WASM

`mixer.pre_init(22050, -16, 2, 2048)` is called in `init_pygame()` before `pygame.init()`. In some WASM environments this is a no-op; in others it may throw. Already guarded by `_SilentSound`, so sound failures don't crash the game — but `pre_init` itself could throw before the guard is in effect.

**Fix:** Wrap `snd.pre_init()` in try/except if H1 doesn't explain the blank screen.

---

## Implementation Plan

### Step 1 — Fix the `languages` NameError (H1) ✓ done

**`monorail/monorail.py`** lines 47–51:

```python
try:
    lc, encoding = locale.getdefaultlocale()
except Exception:
    lc = None
languages = [lc] if lc else []
languages += DEFAULT_LANGUAGES
```

### Step 2 — Fix `gui_divider` in the template (H2) ✓ done

**`build/web-cache/27613e24ba16d44f2a5c88150c6d64e5.tmpl`** line 151 — `gui_divider : 1`.  
Keep `gui_debug : 2` for now so the Python terminal remains visible for error inspection.

### Step 3 — Rebuild and test

```bash
bash build_web.sh
cd build/web && python3 -m http.server 8000
```

Open `http://localhost:8000` in Chrome. After clicking, look at:
- The canvas (should show the game menu)
- The Python terminal at the bottom (should show any remaining tracebacks)
- Chrome DevTools console (any JS errors)

---

## Verification

1. The game menu renders in the canvas after clicking.
2. Chrome DevTools console shows no 404s and no JS errors.
3. Desktop still works: `poetry run python MysticMine` launches normally.
4. Once the game renders, set `gui_debug : 0` in the template and rebuild to get a clean full-screen layout.
