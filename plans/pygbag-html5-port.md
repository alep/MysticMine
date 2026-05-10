# Plan: pygbag / HTML5 Port

## Context

MysticMine runs on Python 3 + pygame 2 on the desktop. The goal is to make it run in a browser tab using [pygbag](https://pygame-web.github.io/), which compiles CPython + SDL2 to WebAssembly via Emscripten. Once the browser port works, network multiplayer via WebSockets can be layered on top.

The two structural blockers are:
1. The blocking `while` game loop — browsers have no blocking thread; every frame must yield back to the JS event loop.
2. The Cython `ai.pyx` — Cython produces native `.so` code which cannot run in WASM.

Everything else (pygame 2, numpy, binary file I/O, fonts, sound) is either supported by pygbag or trivially fixed.

---

## Step 1 — Convert `monorail/ai.pyx` → `monorail/ai.py`

All Cython syntax in `ai.pyx` is purely for type hints and performance — there are no C arrays, malloc calls, or C stdlib imports. The conversion is mechanical.

**Rules:**
- `cdef class Foo:` → `class Foo:`
- `cdef int/float/char/void/object varname` inside method bodies → delete the line
- `cdef` member variables in class body → delete the `cdef type` prefix, keep any `readonly`/`public` markers as comments if desired (they have no Python meaning)
- `cdef` methods → `def` methods
- `cdef enum:\n    CYCLES_PER_UPDATE = 1024` → module-level constant `CYCLES_PER_UPDATE = 1024`
- Remove the forward declaration line `cdef class AiNode #forward declaration`
- Fix import: `from monorail import tiles, pickups` → `from . import tiles, pickups` (relative import, consistent with rest of package)

**Output:** `monorail/ai.py` (new file). Keep `ai.pyx` in place for now — it can be removed later.

**Update entry script** `MysticMine`: remove the `try: import monorail.ai / except ImportError` guard; the module is now always importable.

---

## Step 2 — Async game loop in `monorail/koon/app.py`

pygbag requires the game loop to be an `async def` that calls `await asyncio.sleep(0)` once per frame. This yields control back to the browser's JS event loop without stopping the game.

**Changes to `koon/app.py`:**

```python
import asyncio

# existing run() becomes a thin wrapper:
def run(self):
    asyncio.run(self._run_async())

async def _run_async(self):
    try:
        self.init_pygame()
        self.before_gameloop()

        self.fps = 0
        frame_count = 0
        next_game_tick = pygame.time.get_ticks()
        next_half_second = pygame.time.get_ticks()

        self.game_is_done = False
        while not self.game_is_done:
            self.handle_events()

            loop_count = 0
            while pygame.time.get_ticks() > next_game_tick and loop_count < 4:
                x, y = pygame.mouse.get_pos()
                self.userinput.mouse.feed_pos(Vec2D(x, y))
                self.do_tick(self.userinput)
                self.userinput.update()
                next_game_tick += GAMETICKS
                loop_count += 1

            if loop_count >= 4:
                next_game_tick = pygame.time.get_ticks()

            time_sec = pygame.time.get_ticks() * 0.001
            interpol = 1 - ((next_game_tick - pygame.time.get_ticks()) / float(GAMETICKS))
            self.render(pygame.display.get_surface(), interpol, time_sec)
            pygame.display.flip()

            frame_count += 1
            if pygame.time.get_ticks() > next_half_second:
                self.fps = 2 * frame_count
                frame_count = 0
                next_half_second += 500

            await asyncio.sleep(0)   # ← the single required change

        self.after_gameloop()
        self.deinit_pygame()

    except:
        self.deinit_pygame()
        raise
```

`asyncio.run()` works identically on desktop and in pygbag — no separate desktop/browser code path needed.

---

## Step 3 — Create `main.py` at project root

pygbag's build tool looks for `main.py` in the directory you point it at. This file replaces the `MysticMine` entry script for the web build (the original `MysticMine` script stays for desktop).

```python
# main.py  (project root)
import sys, os

# pygbag sets CWD to the package root; monorail expects CWD = monorail/
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.join(os.path.dirname(__file__), "monorail"))

import monorail.monorail
import asyncio

asyncio.run(monorail.monorail.async_main())
```

**Also add `async_main()` to `monorail/monorail.py`** alongside the existing `main()`:

```python
async def async_main():
    configuration = Configuration.get_instance()
    SingleSwitch.is_enabled = configuration.one_switch
    SingleSwitch.scan_timeout = configuration.scan_speed
    app.set_game_speed(configuration.game_speed)
    game = Monorail(configuration)
    await game._run_async()          # calls the new async loop from Step 2
    configuration.save()
```

The existing `main()` remains untouched for desktop use.

---

## Step 4 — Disable fullscreen for browser

`pygame.FULLSCREEN` in a pygbag build either does nothing or causes errors — the browser handles full-screen via its own UI. Wrap the flag so it's only used on desktop.

**`monorail/koon/app.py`** `init_pygame()`:
```python
import sys
# ...
flags = pygame.FULLSCREEN if (self.config.is_fullscreen and sys.platform != "emscripten") else 0
pygame.display.set_mode(self.config.resolution, flags)
```

Same guard in **`monorail/menu.py`** (the Options dialog toggles fullscreen at runtime, lines 500–502).

---

## Step 5 — Fix system font fallbacks

Two places use `pygame.font.Font(None, size)` (the pygame built-in system font), which is unavailable in WASM:

| File | Line | Fix |
|------|------|-----|
| `monorail/koon/app.py` | 132 | Replace `None` with `"data/edmunds.ttf"` — used only for FPS debug display |
| `monorail/monorail.py` | 474 | Replace `None` with `"data/edmunds.ttf"` — used for a debug overlay |

These are both debug/dev displays, so an alternative is to guard them with `if sys.platform != "emscripten"` and skip rendering entirely in the browser.

---

## Step 6 — Stub configuration persistence

`Configuration` saves to `~/.mysticmine` (a pickle file in the user's home directory). The browser has no home directory.

**`monorail/settings.py`** — wrap the `save()` and `load()` methods in `Configuration`:

```python
import sys

def save(self):
    if sys.platform == "emscripten":
        return          # no filesystem persistence in browser
    # ... existing pickle save code ...

def _load(self):
    if sys.platform == "emscripten":
        return          # start with defaults
    # ... existing pickle load code ...
```

Same treatment for `QuestStatistics` (saves to `other_stats/`) and highscores (`highscores.dic`). For the initial port, defaults are fine — localStorage persistence can be added later.

---

## Step 7 — Install pygbag and build

```bash
# Install pygbag into the Poetry venv
poetry run pip install pygbag

# Build and serve locally (opens browser automatically)
poetry run pygbag --PYBUILD 3.11 --ume_block 0 monorail

# Or point at project root with main.py
poetry run pygbag .
```

pygbag bundles CPython 3.11 internally. The `--PYBUILD 3.11` flag is needed if the system has a newer Python. The game logic is compatible — no 3.13-specific APIs are used.

---

## Files Changed

| File | Change |
|------|--------|
| `monorail/ai.py` | NEW — pure-Python version of `ai.pyx` |
| `main.py` | NEW — pygbag entry point |
| `monorail/koon/app.py` | Add async loop; fix system font; guard fullscreen flag |
| `monorail/monorail.py` | Add `async_main()`; fix system font |
| `monorail/menu.py` | Guard fullscreen toggle |
| `monorail/settings.py` | Stub save/load when `sys.platform == "emscripten"` |
| `MysticMine` | Remove `import monorail.ai` check |

`monorail/ai.pyx` and `monorail/koon/snd.py` are **not changed** — sound is supported by pygbag (stub files will remain silent as on desktop).

---

## Verification

1. **Desktop still works** — `poetry run python MysticMine` must launch the game normally after all changes. The `asyncio.run()` loop is fully compatible with desktop Python.
2. **ai.py unit smoke test** — `poetry run python -c "from monorail import ai; t = ai.PredictionTree(); print('ok')"` must print `ok`.
3. **Browser build** — `poetry run pygbag .` should open a browser tab at `localhost:8000` and show the game menu.
4. **Gameplay check** — start a single-player level, steer the cart through a junction, collect a coin. Verify no JS console errors.
