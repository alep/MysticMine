# MysticMine — Engine & Game Architecture

---

## Overview

MysticMine has two layers. **Koon** (`monorail/koon/`) is a self-contained game framework built on pygame — it provides a game loop, input abstraction, graphics primitives, and a resource manager. **Monorail** (`monorail/`) is the game itself, built entirely on top of Koon. Game code never calls pygame directly; everything goes through Koon.

---

## Part 1 — The Koon Engine

### 1. The Game Loop (`koon/app.py`)

The loop in `Game.run()` uses the **fixed-timestep** pattern: game logic runs at a fixed 25 ticks/second (one tick every 40 ms), while rendering runs as fast as the CPU allows.

Each frame does three things in order:

1. **Events** — drain the pygame event queue and feed raw events into the input layer.
2. **Logic ticks** — an inner `while` loop catches up on any missed logic ticks, capped at 4 to avoid a spiral-of-death on slow machines.
3. **Render** — draw once, passing an `interpol` value (0.0–1.0) that says how far the current moment sits between the last two logic ticks. Views use this to smooth animation between discrete positions.

```python
# koon/app.py:77–95
while pygame.time.get_ticks() > next_game_tick and loop_count < 4:
    self.do_tick( self.userinput )
    next_game_tick += GAMETICKS          # advance by 40 ms

interpol = 1 - ((next_game_tick - pygame.time.get_ticks()) / float(GAMETICKS))
self.render( pygame.display.get_surface(), interpol, time_sec )
pygame.display.flip()
```

The simulation is deterministic and frame-rate independent. Cart physics always runs at exactly 25 Hz regardless of screen refresh rate.

**The 40 ms timestep.** 25 ticks/second means 1000 ms ÷ 25 = 40 ms per tick. Every 40 ms the simulation advances one step — carts move, pickups are checked, AI thinks, scores update. The renderer draws as fast as it can in between, but the physics only actually update on those 25 fixed beats.

**The spiral-of-death.** The cap of 4 ticks per frame guards against a specific failure mode. If the frame takes 50 ms but each tick takes less than 40 ms to compute, the accumulator just carries a small remainder forward with no problem:

```
50 ms elapsed → run 1 tick → 10 ms carried to next frame  ✓
```

The spiral only starts when the **tick computation itself** takes longer than 40 ms — meaning the CPU cannot keep up even one step at a time:

```
Tick takes 60 ms to compute, timestep is 40 ms:

After tick 1: ran 60 ms, advanced 40 ms → 20 ms behind
After tick 2: ran 60 ms, advanced 40 ms → 40 ms behind
After tick 3: ran 60 ms, advanced 40 ms → 60 ms behind
→ now needs 2 ticks to catch up, which takes 120 ms → deeper in debt...
```

The cap stops this from looping forever. When hit, the clock is also reset:

```python
if loop_count >= 4:
    next_game_tick = pygame.time.get_ticks()  # abandon the debt, stop chasing
```

Without that reset the game would keep trying to catch up on accumulated debt. With it, the game accepts the lag and moves on — the user sees slow motion rather than a freeze. In practice MysticMine's logic is lightweight enough that this never triggers during normal play; the cap mainly protects against OS-level pauses (window drag, process suspension) that cause a large burst of elapsed time all at once.

### 2. Input (`koon/input.py`)

`ButtonLogger` is the shared base for all input devices. It tracks three sets:

| Set | Meaning |
|-----|---------|
| `went_down_buttons` | pressed this tick (cleared each tick) |
| `went_up_buttons` | released this tick (cleared each tick) |
| `down_buttons` | currently held |

After each tick, `update()` clears the went-down/went-up sets. This means `key.went_down(K_SPACE)` is true for exactly the one tick the key was pressed, not for every tick it is held — which makes input handling in game logic clean and explicit.

`UserInput` bundles a `Keyboard`, `Mouse`, and list of `Joystick` objects. A `Button` object is a (device, key) pair that can be stored and compared, used in `settings.py` to let the player remap controls.

### 3. Graphics (`koon/gfx.py`)

Three core types:

**`Surface`** — wraps a `pygame.Surface`. Created from a filename, a pygame surface, or a `(width, height)` size. Blitting handles both pygame surface and `Surface` targets.

**`SpriteFilm`** — a sprite sheet divided into a grid of equal-size frames. `nr` selects the current frame. `draw()` computes the source rectangle:

```python
sp_x = (nr % max_x) * width
sp_y = (nr // max_x) * height
```

Then blits that rectangle offset by the sprite's `center` point so the sprite is anchored consistently regardless of frame. `car1.png`, for example, is 460×336 divided 10×8 = 80 frames of 46×42 px.

**`SubSurf`** — a named rectangular region of a larger surface (e.g. one HUD element cut from an atlas), with an optional draw offset.

Animation timers (`LoopAnimationTimer`, `PingPongTimer`) are separate objects that compute a frame number from `time_sec` but hold no surface reference — they're pure time math.

### 4. Resources (`koon/res.py`)

`ResourceManager` (singleton `resman`) reads `data/800x600/resources.cfg` once at startup, then lazily constructs typed objects on first access by name:

```python
resman.get("game.car1_sprite")   # → SpriteFilm
resman.get("game.coin_surf")     # → Surface
resman.get("game.tile0_surf")    # → Surface
```

The config maps string keys to typed constructors (`Surface`, `SpriteFilm`, `SubSurf`, `Sound`, `Music`, `Vec2D`, `Rectangle`). All asset paths live in one file, not scattered through code, and objects are constructed once and cached — no matter how many systems request the same resource.

---

## Part 2 — The MysticMine Game

### 5. Scene / State Machine (`monorail.py`)

`Monorail` subclasses `Game` and overrides `do_tick` and `render` to simply delegate to whichever scene is active:

```
Monorail
  ├── self.menu       (MenuScreen)
  ├── self.game       (MonorailGame)
  └── self.editor     (MonorailEditor)
        ↑
    self.state points to the active scene
```

`MonorailGame` has its own nested state machine (an integer enum) that sequences the full round lifecycle:

```
STATE_INTRO → STATE_BEGIN → STATE_GAME → STATE_STATS → STATE_TOTAL → STATE_DONE
```

Transitions happen inside `do_tick` when conditions are met (timer expired, win condition triggered, player presses escape, etc.).

### 6. Model / View Separation (`frame.py`)

Every game object (`GoldCar`, `Tile`, `Diamond`, …) is a **model** — pure state and logic, no drawing code. A parallel set of `*View` classes handle drawing. The model never knows it has a view.

`Frame` is the bridge. It holds the pygame surface, `time_sec`, and `interpol`. Its `get_views(model)` acts as a view factory, caching the created views on the model as `model.views`:

```python
# frame.py:31–89
def get_views( self, model ):
    if isinstance( model, GoldCar ):   return [GoldCarView( model )]
    if isinstance( model, Tile ):      return [TileView( model )]
    if isinstance( model, Enterance ): return [EnteranceView(model), EnteranceTopView(model)]
    ...
```

`Enterance` gets *two* views — the bottom arch drawn early in z-order, the top arch drawn late — a clean way to split one model across two rendering layers without any special-casing in the sort loop.

### 7. The Isometric World and Z-Sorting

Tiles live on a 2D grid of `(x, y)` integer coordinates. The isometric projection to screen pixels is:

```python
screen_x = tile.pos.x * 32 + tile.pos.y * 32 + X_OFFSET
screen_y = -tile.pos.x * 16 + tile.pos.y * 16 + Y_OFFSET
```

This maps the grid to a 2:1 diamond shape (32 px wide, 16 px tall per cell). The north/south axis becomes the screen's x-axis; the east/west axis becomes the screen's y-axis, halved in height to create the foreshortened perspective.

For correct occlusion, sprites are drawn back-to-front using the **painter's algorithm**. Each view exposes a `z` property — a single number used for sorting:

```python
# TileView
z = -tile.pos.x * 16 + tile.pos.y * 16 - 28
```

`frame.draw_z(models)` collects all views from all models (including submodels), sorts by `z` ascending (most negative = furthest back), then draws in that order. Because `z` equals the screen-y of the tile's grid position, objects deeper into the scene are always drawn first and correctly covered by nearer ones.

### 8. The Trail System — How Carts Move

Carts do not move freely in 2D space. They are constrained to a **graph of trail nodes** defined by the tile layout.

Each `Tile` has a `Trail` with a type (`NS`, `EW`, `SE`, `SW`, `NW`, `NE`, `HILL`) that describes the curve through it. A `TrailPosition` is a `(tile, progress)` pair where `progress` is a float from 0 to `tile.get_length()`. Each tick, the cart's speed is added to `progress`; when it exceeds the tile length, `TrailPosition` advances to the neighboring tile in the exit direction.

Junctions — tiles with three or more connections — are **switches**: they toggle their `Trail.type` on each pass, routing the cart left or right. The AI looks ahead through this graph to plan future routes. `trail.may_switch = False` while a cart occupies a tile, preventing a switch from flipping mid-tile under a moving cart.

Speed physics runs in `GoldCar.game_tick()`:

- Flat tiles have a minimum speed to prevent stalls.
- Downhill slope → accelerate; uphill slope → decelerate.
- Speed reaches zero → reverse direction.
- Modifier pickups (`Oiler`, `Balloon`, `Ghost`) alter the speed constants.

### 9. The AI (`ai.pyx`)

**What is beam search?**

A full tree search would explore every possible future route to every possible depth — exhaustive but exponentially expensive. Beam search instead keeps only the most promising N candidates at each depth level (the "beam") and discards the rest.

```
Depth 0:  [current position]
Depth 1:  [left turn, right turn]       ← both kept, beam still narrow
Depth 2:  [LL, LR, RL, RR]             ← kept if under MAX_NODES
Depth 3:  prune weakest → only high-scoring routes go deeper
```

The key property for a real-time game is that it is **anytime**: the tree is built incrementally across many ticks, so the AI always has *some* answer ready — it just gets more accurate the longer it has been running. When the cart reaches a junction, it reads whatever the best-scored path is at that moment. The trade-off is that beam search can miss the globally optimal path if it was pruned early; for a game like MysticMine that's acceptable.

**Implementation**

The AI runs a beam search over the trail graph, spread across frames to avoid per-frame spikes.

`PredictionTree` maintains a tree of `Node` objects, each wrapping an `AiNode` (one possible future cart position and state). Each tick, `update()` spends a budget of `CYCLES_PER_UPDATE` cycles: two-thirds expanding leaf nodes (growing the tree deeper), one-third re-scoring nodes that haven't been evaluated yet.

`AiNode._calc_score()` returns a weighted sum of what the cart would encounter at that position:

| Pickup | Score |
|--------|-------|
| Coin | +1 |
| Diamond | +2 |
| Lamp | +5 |
| Axe | +2 |
| Rock | −1 |
| Leprechaun | −2 |
| Dynamite | −8 |

Proximity to other carts carrying good/bad items adds ±5/distance. `set_root()` reuses existing tree branches when the AI's new position matches a child of the previous root, avoiding a full rebuild every tick.

**What the AI actually does**

The AI only acts at **switch points** (junctions). `AiController.do_tick()` does nothing on straight track. When the cart approaches a junction, it walks the prediction tree to find the node matching that junction, reads the best-scoring child branch, and calls `keydown()` to flip the switch if the current track direction isn't the best one.

The `iq` parameter (0.0–1.0) is a probability of making the smart move vs. a random one:

```python
if random.random() < self.iq:   # Smart move — use the tree
    ...
else:                            # Stupid move — random occasional flip
    if random.randint(0, 32) == 0:
        self.goldcar.keydown()
```

**Prediction trees for human players**

Prediction trees are built for *all* carts — including human-controlled ones — whenever any AI is present. The human's tree is not used to control the human; it is used by `_calc_other_cars()` so that the AI can predict where the human is likely to be and factor that into its own scoring.

**AI in adventure (Quest) mode**

The main campaign (`QuestManager.MAIN_QUEST`) is a fixed sequence of levels each annotated with a list of `opponent_iqs`. The first levels have no AI opponents at all — they are pure solo tutorials:

```python
# scenarios.py:1084-1086  (ai_count=0 means no opponents)
self.add( quest, ScenarioCoinCollect, 0, 0, [] )  # Learn coins and switch
self.add( quest, ScenarioCoinCollect, 1, 0, [] )  # Learn larger playfield
self.add( quest, ScenarioCoinCollect, 2, 0, [] )  # Learn slopes
```

From level 5 ("Learn opponent") onwards, AI opponents are added with `iq=0.5` — meaning they make the smart move only 50% of the time, making them deliberately beatable:

```python
self.add( quest, ScenarioCoinCollect, 4, 1, [] )  # 1 AI opponent at iq=0.5
...
self.add( quest, ScenarioBlowup,      6, 1, [] )  # 1 AI opponent
self.add( quest, ScenarioDiamondCollect, 8, 2, [] )  # 2 AI opponents
```

Later levels scale up to 2–3 AI opponents. The AI `iq` is fixed at 0.5 throughout the campaign; difficulty is instead varied by increasing the goal score or tightening the timeout, which `Quest.create_scenario()` scales based on the player's measured skill from previous attempts.

### 10. Scenarios — Game Modes (`scenarios.py`)

`Scenario` subclasses define win/lose conditions. Each scenario declares which pickup classes to spawn, at what rate, and implements `is_won(playfield)` / `is_lost(playfield)` checked each tick by `MonorailGame`.

| Scenario | Win condition |
|----------|--------------|
| `CoinCollect` | Collect N coins before timeout |
| `DiamondCollect` | Pick up a diamond and deliver it through the portal |
| `Pacman` | All cars become hostile; survive / eliminate |
| `Blowup` | Avoid dynamite chains |
| `GoldRush` | Collect the most gold in a time limit |
| … (14+ total) | … |

The scenario system is what makes the 185 levels feel different despite running on the same engine.

---

## Sources

### [Fix Your Timestep! — Glenn Fiedler (Gaffer on Games)](https://gafferongames.com/post/fix_your_timestep/)

Glenn Fiedler argues that physics simulations require careful control over timestep management to maintain stability and correctness. Variable timesteps cause unpredictable and non-reproducible behavior across machines with different frame rates. He advocates a decoupled approach: an accumulator collects elapsed real time and the simulation consumes it in fixed-size chunks, with any remainder carried to the next frame. The renderer interpolates between the two most recent physics states using the leftover fraction, eliminating visual stutter. This gives both a deterministic simulation and a variable display frame rate with no trade-off.

### [MVC in Game Development — Game Developer](https://www.gamedeveloper.com/programming/mvc-in-game-development)

The article argues that adopting Model-View-Controller architecture prevents game codebases from becoming unmanageable "spaghetti code." MVC separates game logic (Model), display (View), and input handling (Controller) into independent layers. Because Model classes hold no rendering code, they are portable and independently testable. The primary advantage is modularity: new features can be added to one layer without rewriting others. The main cost is the upfront planning required before coding begins.

### [Painter's Algorithm — Wikipedia](https://en.wikipedia.org/wiki/Painter%27s_algorithm)

The painter's algorithm determines visible surfaces in a 3D scene by sorting all polygons by depth and rendering them back-to-front, so nearer objects paint over farther ones — the same way a traditional painter works. It is simple to implement and works well for scenes with no cyclic overlap. Its main limitations are that it must render every polygon in the visible set even if later occluded (inefficient), and it fails entirely when polygons cyclically overlap or intersect, requiring those polygons to be manually cut. These shortcomings led to Z-buffering, which resolves depth conflicts per pixel instead of per polygon.

### [Drawing Isometric Boxes in the Correct Order — Shaun LeBron](https://shaunlebron.github.io/IsometricBlocks/)

This article addresses the problem of rendering isometric 3D boxes in the correct visual order when they overlap on screen. The solution works in three steps: convert each box's 3D silhouette to a 2D hexagon and test whether two boxes' hexagons intersect (to determine if ordering matters); find the axis along which their ranges don't overlap (to determine which is in front); and run a topological sort on the resulting dependency graph to produce the final draw order. The approach handles arbitrary box sizes correctly but breaks down for cyclically intertwined boxes, which require clipping or segmentation to resolve.

### [Isometric Depth Sorting — Mazebert](https://mazebert.com/forum/news/isometric-depth-sorting--id775/)

This post describes a practical two-stage approach to isometric depth sorting in a live mobile game. A naive `sprite.isoX + sprite.isoY` sort fails as soon as objects of different sizes move between tiles. The solution uses axis-aligned bounding boxes (AABBs) to compare every pair of sprites and build a dependency graph of which object is behind which (O(n²) comparisons). A depth-first search over that graph produces a correct topological render order. The author reports this sustains 60 fps on mobile while correctly handling semi-transparent textures.
