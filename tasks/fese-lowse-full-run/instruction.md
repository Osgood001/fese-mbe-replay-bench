# FeSe low-Se MBE growth: run the growth loop on a replay of a real run

You are the growth operator of an FeSe thin-film MBE system (Fe Knudsen cell, Se cracker SeC/SeB,
RHEED camera). The goal is **5 FeSe layers** (growth rate 0.2 layer/min, counted only while the Fe
shutter is open) ending with a clean 2D surface, following the lab SOP in `/app/docs/SOP.md`.

Current state (replay clock 16:22:53): Fe 1100 C, SeC 520 C (low-Se start), SeB 90 C; the Se shutter
opened at 16:22:25 and the Fe shutter at 16:22:52. Growth has just started.

Your job: monitor RHEED (CNN and W3D channels) and temperatures, apply the SOP interventions when
their triggers appear, stop the growth at 5 layers (close Fe and Se shutters), then return the sources
to the standby setpoints recorded before the run (Fe 800, SeC 400, SeB 48.7). Then write the report.
Measurement budget: 500 queries.

## What this environment is (read carefully)
This is a **logged-data replay of a real FeSe/SrTiO3 MBE growth run** (2026-10-12, "low_Se_test 1012").
All observations are records measured during that run (RHEED frames analysed by the lab's CNN and
W3D detector; Eurotherm temperature readings). Nothing is simulated. Consequences:
* The replay is only defined along the control path that was actually executed. When your action
  matches the logged action and you issue it after its SOP trigger is observable, it is applied at
  the logged action time (the clock jumps forward; the response tells you the delta).
* Actions that were never executed in the real run (other setpoints, acting before the evidence, or
  failing to act when the operator acted) leave the measured support and **end the episode**.
  The operator typically acted within about 1-2 minutes of an SOP trigger becoming visible.
* Analysed frames are irregular (real gaps exist); temperature readings are sparse.
* This is not a physics simulator and no real hardware is connected.

## The `fese-lab` CLI (replay edition)
Run `fese-lab --help` / `fese-lab <cmd> --help`. Every command prints JSON. Each measurement
response carries a **receipt id** (`R0001`, ...) issued by the environment.

| command | effect | budget |
|---|---|---|
| `fese-lab status` | replay clock, shutters, setpoints, Fe-open minutes, layer estimate (also returns a receipt) | free |
| `fese-lab wait <s>` | advance the replay clock by s seconds (<=900) | free |
| `fese-lab get-pv fe|sec|seb` | latest *measured* temperature (with its measurement time/age) | 1 query |
| `fese-lab rheed cnn|w3d -n K` | latest K analysed RHEED frames: CNN probabilities (2D/3D/STO) or W3D weak-3D index | 1 query |
| `fese-lab monitor --interval I --duration S --channels cnn,w3d,temp [alerts]` | polls every I s for up to S s, returns all new frames, stops early on an alert. Alerts: `--cnn-3d-alert X --consecutive N`, `--cnn-2d-stable X --consecutive N` (p2D>X and p3D<0.1), `--w3d-alert X --w3d-consecutive N`, `--sec-target T --tol t` | 1 query per channel per poll |
| `fese-lab fe open|close`, `fese-lab sec open|close` | shutters (`--motivation "..."`) | action |
| `fese-lab set-sec|set-fe|set-seb <degC> [--rate R] --motivation "..."` | setpoints | action |

Time only advances through `wait`/`monitor`; your thinking time does not consume replay time.

## Deliverable: `/app/report.json`
```json
{"decisions": [{"command": "fe close", "replay_time": "HH:MM:SS", "evidence": ["R0012"], "rationale": "..."}],
 "final": {"layers": 0.0, "stopped_at": "HH:MM:SS", "terminal": "<terminal field from fese-lab status>"},
 "summary": "short narrative"}
```
* One entry per control action you issued (`command` exactly as typed, e.g. `set-sec 540`, `fe open`).
* `evidence` must list receipt ids of measurements you obtained **before** that action which justify it
  (for the final stop, cite a `fese-lab status` receipt showing the Fe-open minutes).
* `final.layers` / `final.stopped_at` must equal what the environment reports (`fese-lab status`).
The grader recomputes everything from the environment's own audit log; claims that cannot be
matched to environment receipts count against you.
