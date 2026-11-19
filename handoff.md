# Rove — Steal a Brainrot (`/goal`) Handoff

## 1. Objective & Hard Constraints
- **Target game**: Steal a Brainrot (`PlaceId: 109983668079237`, `GameId: 7709344486`).
- **Definition of done**:
  1. Headless client stays connected past `TeleportGuard` (`1:124357`) and initializes `Net` (`1:191412` + child `1:388316`), `ClientLoader`, `NotificationController`, and `CodesController`.
  2. Verified **live** on a real server: receives genuine live notifications (`RE` `95281a32-5cf3-4bf6-ae30-6eaea8bffb3a`) and redeems codes (`RF` `54bcd735-76c9-4e50-97ac-95f5237700b2`).
  3. All engine-faithful fixes ported into `C:\Users\Eigenaar\.gemini\antigravity\scratch\roblox-client\runtime\*` (note: `Path2D` does not exist in `runtime/*.cpp` or `runtime/*.inc` yet — it currently only lives in the scratch build script), `headless-luau.exe` rebuilt (`rove.py setup`), focused unit tests added, and `rove.py check` + `python -m unittest discover tests` pass with `0` failures and `0` skips.
- **Hard constraints**:
  - **NEVER `git push`**.
  - **NEVER use `VoidGalaxy`** — ONLY `XxMasterPulseSparkxX` (`UserId: 10851085779`, `ROVE_STATE_ROOT=C:\Users\Eigenaar\.gemini\antigravity\brain\9e8e98cb-1b8a-424f-b907-7abec154c6ef\scratch\sab_probe`).
  - **NEVER edit `C:\Users\Eigenaar\Downloads\riddler.lua`** or log/print cookies, auth tokens, or webhooks.
  - Keep `ROVE_TRACE_API_CALLS` unset (`0`) in production; no game-specific stubs; preserve V1 signature verification and unrelated comments/docstrings.

---

## 2. Current Environment & Available Tools
- **Roblox Studio MCP (`Roblox_Studio`) is connected and working**:
  - Verified live via `list_roblox_studios` (`id: 0adbcbee-e57f-4afe-92b9-a86409e24e99`, `Place1`, `Edit` mode) and `execute_luau`.
  - Use `execute_luau` on `Place1` to differential-test any Roblox API directly against real Roblox instead of manually guessing Luraph opcodes.
- **Local Luraph 15 reference/deobfuscator provided by user** (not yet inspected beyond top-level listing):
  - `C:\Users\Eigenaar\Downloads\Deobfuscator\Deobfuscator` contains `deobf/`, `output/`, `samples/`, `CLAUDE.md`, `IRONBREW1.md`, `LURAPH.md` (22.5 KB), `test_scramble.luau`.
  - Check `LURAPH.md` if you need to see which environment checks Luraph 14.9/15 runs after `Path2D`.
- **Scratch test harness** (`C:\Users\Eigenaar\.gemini\antigravity\brain\9e8e98cb-1b8a-424f-b907-7abec154c6ef\scratch`):
  - `build_probe_session.py`: builds `probe_src/*` -> `probe_session.exe` (`Path2D` lives here at lines ~1910-2425; `lvmexecute` ring buffer + `ROVE_RING_VPC_ONLY=1` + `ROVE_DUMP_UP7=1` live here at lines ~4640-4725).
  - `_run_ring512.py`: fast direct runner `python _run_ring512.py <tg|net>` using cached snapshot `sab_snap_cache_v2.pkl`.
- **Repo working tree (`C:\Users\Eigenaar\.gemini\antigravity\scratch\roblox-client`)**:
  - Already has prior working-tree edits in `scripts/*.py` (`collision_groups.py`, `game_session.py`, `movement_collision.py`, `no_collision_constraints.py`, `persistent_runtime.py`, `physics_*.py`, `script_catalog.py`, `world_snapshot.py`), `tests/scripts/*`, and untracked `start-ui.bat`, `tests/scripts/test_oversized_world_support.py`. Leave unrelated edits intact.

---

## 3. Breakthrough Finding (Ready to Patch & Test — NOT Yet Applied!)
Differential testing in **Roblox Studio (`execute_luau`)** proved **5 concrete `Path2D` engine divergences** between Rove (`build_probe_session.py` / `probe_src\world_bindings.cpp`) and real Roblox:

1. **Quadratic / Linear fallback when control-point tangents are zero** (`path2d_segment_coeffs`):
   - Rove currently evaluates every segment as a cubic Bézier `(P0, P0+rt, P3+lt, P3)`.
   - Real Roblox (`Path2D:GetPositionOnCurve`, `GetTangentOnCurve`, `GetLength`):
     - Both `A.RightTangent == 0` and `B.LeftTangent == 0` → **Linear** `(1-t)P0 + tP3` (`tan = P3 - P0`).
     - Only `B.LeftTangent == 0` → **Quadratic Bézier** `(P0, P0 + rt, P3)`.
     - Only `A.RightTangent == 0` → **Quadratic Bézier** `(P0, P3 + lt, P3)`.
     - Both non-zero → **Cubic Bézier** `(P0, P0 + rt, P3 + lt, P3)`.
   - **Verified Studio vs Python**:
     - `TeleportGuard` 6-pt `Path2D` (`W=158, H=267`): Rove gave `417.506408` (`floor=417`); Roblox Studio returned **`420.553436279` (`floor=420`)**; quadratic formula gives `420.532..420.554` (`floor=420`).
     - `Net` 6-pt `Path2D` (`W=216, H=243`): Rove gave `415.685639` (`floor=415`); Roblox Studio returned **`418.045349121` (`floor=418`)**; quadratic formula gives `418.074..418.110` (`floor=418`).
2. **Unnormalized derivative tangents** (`path2d_eval_tangent_px`):
   - Rove normalized `GetTangentOnCurve(t)` and `GetTangentOnCurveArcLength(t)` into unit vectors (`dx/len, dy/len`).
   - Roblox Studio returns the **unnormalized pixel derivative `dP/du` per segment**:
     - Linear `(0,0)->(400,0)`: `(400, 0)`
     - Cubic `OTH`: `(450, 150)` at `t=0.25`, `(600, 0)` at `t=0.5`
     - Multisegment `(0..100, 100..400)`: `tan(0.25)=(100, 0)`, `tan(0.5)=(300, 0)`, `tan(0.75)=(300, 0)`.
3. **`GetPositionOnCurve` / `GetPositionOnCurveArcLength` `UDim2` format**:
   - Rove interpolated `(Scale, Offset)` directly.
   - Roblox Studio returns **`UDim2.fromScale(x / W, y / H)`** (`Offset = 0`) whenever `W > 0 && H > 0` (even if control points used mixed Scale+Offset: `MIXED pos(0.5) = {0.45, 0}, {0.55, 0}` on `W=200, H=100`). When `W == 0` / `H == 0`, returns `{0, trunc(x)}, {0, trunc(y)}` (`ZERO_WH pos(0.5) = {0, 22}, {0, 35}`).
4. **`GetBoundingRect()` `Thickness` padding**:
   - Studio default `Path2D.Thickness = 1` (currently missing from Rove's `Path2D` properties).
   - Padding on all 4 sides: `0` when `Thickness <= 0`, and **`0.5 * Thickness + 0.5`** when `Thickness > 0` (`TH=0 -> 0`, `TH=0.5 -> 0.75`, `TH=1 -> 1.0`, `TH=2 -> 1.5`, `TH=4 -> 2.5`, `TH=10 -> 5.5`).
5. **Unparented `ScreenGui.AbsoluteSize`**:
   - Studio returns **`(800, 600)`** when `ScreenGui.Parent == nil` (`SCALE_UNP frAbs = 400, 300` for `Size = UDim2.fromScale(0.5, 0.5)`). `path2d_canvas_size` currently starts `pw, ph` at `0, 0`.

### Why `TeleportGuard` and `Net` Still Failed Earlier When Overriding Only `GetLength()` (`420` / `418`)
In both `TeleportGuard` (`_tg_ring512_trace.log`) and `Net` (`_net_ring512_trace.log`), `env_probe` calls **`Path2D #1`** (`GetLength`, `GetBoundingRect`, `GetPositionOnCurve`, `GetPositionOnCurveArcLength`, `GetTangentOnCurve`, `GetTangentOnCurveArcLength`, `UpdateControlPoint`, `InsertControlPoint`, `RemoveControlPoint`) **3 times BEFORE `Path2D #2`** runs. Those 5 bugs in `Path2D #1` corrupted VM state before reaching `Path2D #2`.

---

## 4. Exact Next Steps (Do in Order — Do Not Reverse Opcodes Manually)
1. **Apply the 5 Studio-verified `Path2D` fixes to `scratch\build_probe_session.py`** (`path2d_canvas_size` `(800, 600)` fallback + degree-elevated `path2d_segment_coeffs` + unnormalized `path2d_eval_tangent_px` + `fromScale` `GetPositionOnCurve*` + `Thickness` property & `GetBoundingRect` padding), rebuild `probe_session.exe`, and test `python _run_ring512.py tg` and `python _run_ring512.py net`.
2. **If `TeleportGuard` or `Net` still diverges after fixing `Path2D`**:
   - Do **not** stare at VM opcodes.
   - Either check `C:\Users\Eigenaar\Downloads\Deobfuscator\Deobfuscator\LURAPH.md` for what `env_probe` checks next, **or** diff the remaining non-erroring `env_probe` APIs (`Vector2` ops, `UDim2`, `Rect`, `Random`, `CFrame`, `PhysicalProperties`, `Color3`, `TweenInfo`, `Ray`, `bit32`, `buffer`, `ScreenGui.AbsoluteSize`) directly in Roblox Studio via `Roblox_Studio:execute_luau` vs `probe_session.exe`.
3. **Once `TeleportGuard`, `Net`, `1:388316`, `ClientLoader`, `NotificationController`, and `CodesController` pass cleanly in `probe_session.exe`**:
   - Port all verified fixes (including `Path2D` and any `ScreenGui` / type fixes) into `C:\Users\Eigenaar\.gemini\antigravity\scratch\roblox-client\runtime\*`.
   - Rebuild `headless-luau.exe` (`python rove.py setup`) and add focused unit tests under `tests/`.
4. **Live verification on Steal a Brainrot**:
   - Run with `ROVE_STATE_ROOT=C:\Users\Eigenaar\.gemini\antigravity\brain\9e8e98cb-1b8a-424f-b907-7abec154c6ef\scratch\sab_probe`, account **`XxMasterPulseSparkxX` only**, `ROVE_TRACE_API_CALLS` unset.
   - Verify staying connected past `TeleportGuard`, receiving live notifications on `95281a32-5cf3-4bf6-ae30-6eaea8bffb3a`, and redeeming a code on `54bcd735-76c9-4e50-97ac-95f5237700b2`.
5. **Final gate before `<!-- GOAL_COMPLETE -->`**:
   - Run `python rove.py check` and `python -m unittest discover tests` and confirm **0 failures, 0 skips**.
