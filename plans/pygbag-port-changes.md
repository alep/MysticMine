# pygbag / HTML5 Port — Change Report

All changes required to make MysticMine run in the browser via pygbag 0.9.3 (CPython 3.12 → WASM via Emscripten).

---

## New files

### `main.py` (project root)
pygbag entry point. Must be named `main.py` at the project root.
- Adds project root to `sys.path`
- Creates a `pygame.locals` shim: pygbag's WASM build omits the pure-Python `pygame/locals.py` re-export file; the shim injects a synthetic module into `sys.modules` containing only the uppercase constants and `K_` key codes from `pygame` (not classes, to avoid shadowing game-code names like `koon.input.Joystick`)
- Wraps `async_main()` in try/except; on failure writes the traceback to the page's `#infobox` div as a visible red overlay so errors aren't silently swallowed

### `pygbag.ini`
Controls what pygbag packs into the WASM archive:
- `ignoreDirs` — excludes `build/`, `plans/`, `assets/`, `installer/`, `.git/`, etc., and `/data` (root-level data dir; game data is packed as `monorail/data/` instead)
- `ignoreFiles` — excludes the native Cython `.so` (`ai.cpython-313-darwin.so`), all `.wav` files (sound intentionally disabled in browser — see below), and build/tooling scripts

### `build_web.sh`
One-command build script. Handles several WASM-specific problems automatically:

1. **Symlink expansion** — `monorail/data` is a symlink to `../data/800x600/`; `os.walk()` (used by pygbag's packer) does not follow symlinks. The script replaces the symlink with a real directory copy before building and restores it on exit.
2. **`--build` flag** — runs `pygbag --build` (build-only, no dev server) so the script can continue running after pygbag finishes.
3. **BrowserFS** — pygbag 0.9.3 references `browserfs.min.js` at a CDN URL that returns 404. Downloaded once from jsDelivr and served locally.
4. **pygame-ce wheel** — the package index uses a relative URL for the pygame wheel, so it must be served by the local dev server. Downloaded once from the pygame-web CDN into `build/web/cdn/cp312/`.

---

## Modified files

### `monorail/koon/app.py`
- **Async game loop** — `run()` becomes a thin wrapper around `_run_async()`. The loop calls `await asyncio.sleep(0)` once per frame to yield control back to the browser JS event loop (required by pygbag).
- **Fullscreen guard** — `pygame.FULLSCREEN` wrapped in `sys.platform != "emscripten"` check; the flag errors in WASM.
- **Font path** — FPS debug font changed from `None` (system font, unavailable in WASM) to `"data/edmunds.ttf"`.

### `monorail/monorail.py`
- **`async_main()` added** — browser entry point called from `main.py`; sets CWD, loads config, creates game, awaits `_run_async()`.
- **Locale fix** — `locale.getdefaultlocale()` returns `(None, None)` in WASM (no locale set). The original code left `languages` undefined when `lc` was falsy, causing `NameError` at import time. Fixed by initialising `languages = []` before the conditional.
- **Fullscreen guard** — same `sys.platform != "emscripten"` guard on the maximize button handler.

### `monorail/koon/snd.py`
- **`_SILENT` flag** — `sys.platform == "emscripten"` guard at module level; `pre_init()`, `init()`, and `deinit()` are all no-ops in WASM. `mixer.pre_init()` called before `pygame.init()` was blocking/stalling in the WASM audio context.
- **`_SilentSound` / `_SilentChannel` stubs** — `Music.load()` and `Sound.load()` wrap `mixer.Sound()` in try/except and fall back to a stub that silently ignores all calls. WAV files are excluded from the build (see `pygbag.ini`) because the JS audio plugin fails on them; the stubs prevent crashes.

### `monorail/settings.py`
- **`Configuration.save()` guard** — returns immediately on `emscripten`; there is no writable home directory in WASM. Game starts with defaults each session.

### `monorail/menu.py`
- **Fullscreen guard** — `pygame.FULLSCREEN` wrapped in `sys.platform != "emscripten"` check in the Options screen toggle handler.

### `monorail/koon/gfx.py`
- **Removed numpy** — `from numpy import array` removed. The only usage was in `Surface.get_blended()` to scale per-pixel alpha values. Replaced with `pygame.BLEND_RGBA_MULT`:
  ```python
  result.pysurf.fill((255, 255, 255, int(alpha * 255)),
                     special_flags=pygame.BLEND_RGBA_MULT)
  ```
  Equivalent result, no external dependency.

---

## HTML template patches (`build/web-cache/27613e24ba16d44f2a5c88150c6d64e5.tmpl`)

Pygbag generates `build/web/index.html` from a cached template. These patches live in the template so they survive rebuilds.

| Patch | Reason |
|---|---|
| `<script src="browserfs.min.js">` | CDN URL for BrowserFS returns 404 in pygbag 0.9.3 |
| `Object.defineProperty(window, 'devicePixelRatio', {get: () => 1})` | pygbag 0.9.3 throws "Unsupported device pixel ratio 2" on Retina/HiDPI screens |
| Click listener → `window.MM.UME = true` | `MM_play` (the AudioContext unlock) always fails when no audio files are present; the listener forces `MM.UME` true on first click so the Python UME wait-loop exits |
| `gui_divider : 1` | Default of 2 splits viewport 50/50 between game canvas and terminal; 1 gives full screen to the game |
| `fb_width : "800"`, `fb_height : "600"`, `fb_ar : 1.333` | Default framebuffer was 1280×720; game renders at 800×600 |

---

## What was NOT changed

- `monorail/ai.pyx` — the Cython module. A pure-Python `monorail/ai.py` was added alongside it (created in a prior session). `pygbag.ini` excludes `ai.cpython-313-darwin.so` so Python finds `ai.py` first.
- Game logic, level files, graphics, or any gameplay code.
- The desktop entry point (`MysticMine` script) — still works unchanged.

---

## Build & run

```bash
bash build_web.sh               # build once
cd build/web
poetry run python -m http.server 8000   # serve
# open http://localhost:8000 in Chrome
```

`build_web.sh` is idempotent — BrowserFS and the pygame wheel are only downloaded if not already present.
