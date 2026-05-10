# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

```bash
make              # Compile Cython AI module and build package
make clean        # Remove bytecode, compiled files, and temp assets
make rebuild-all  # Full rebuild including asset regeneration from Blender sources
./MysticMine      # Run the game (after building)
```

The Cython module `monorail/ai.pyx` must be compiled before running — `make` handles this via Pyrex/Cython. Dependencies: `pygame`, `numpy`, `pyrex`.

## Tests

Tests live in `monorail/koon/tests/` and cover the engine library (geometry, input, GUI, config, graphics, sound, resources):

```bash
pytest monorail/koon/tests/
# or a single file:
pytest monorail/koon/tests/test_geo.py
```

No test configuration files exist; pytest discovers them automatically. The codebase targets Python 2.

## Architecture

MysticMine is a 2D single-switch puzzle game where players steer gold mine carts to collect items. The codebase has two layers:

**Koon** (`monorail/koon/`) — a reusable engine library:
- `app.py` — game loop and `Game` base class
- `gfx.py` — sprite/rendering wrappers over Pygame
- `geo.py` — 2D/3D geometry primitives (`Vec2D`, `Vec3D`, `Rectangle`)
- `input.py` — keyboard, mouse, and joystick abstraction
- `gui.py` — UI widgets
- `cfg.py` — INI-style config parsing
- `res.py` — resource loading via `data/800x600/resources.cfg`

**Monorail** (`monorail/`) — game-specific logic built on Koon:
- `monorail.py` — top-level game entry; initialises scenes
- `settings.py` — global singletons: `GameData` (player state/scores) and `Configuration` (user prefs)
- `world.py` — board/level loading and management
- `tiles.py` — tile grid, directional trail system, and movement logic
- `player.py` — `GoldCar` class; physics, input dispatch, collision
- `scenarios.py` — 14+ scenario types (`CoinCollect`, `DiamondCollect`, `Blowup`, `Pacman`, …) each defining win/lose conditions
- `control.py` — `HumanController` and `AIController` wrappers
- `ai.pyx` — Cython module; compiled to `ai.so`/`ai.pyd`; path-finding for AI players
- `pickups.py` — collectible items and power-ups
- `hud.py` — in-game HUD and overlay rendering
- `menu.py` — main menu screens
- `event.py` — game events (explosions, animations)
- `sndman.py` — sound/music manager

**Data flow:** `MysticMine` (entry script) → `monorail.py` → `koon/app.py` game loop → active scene (menu or in-game) → `world.py` + `scenarios.py` + `player.py` each frame.

**Levels** are `.lvl` files under `data/800x600/levels/` (185+ levels). Sprites are pre-rendered PNGs in `data/800x600/gfx/`, originally exported from Blender `.blend` files in `assets/3d/` via `build.py`.

**Localization** uses gettext; `.mo` files are in `data/800x600/locale/` (English, German, Russian).
