# FeSe MBE logged-data replay benchmark (Harbor tasks)

Three [Harbor](https://github.com/harbor-framework/harbor) tasks built from **one real FeSe/SrTiO₃ molecular-beam-epitaxy growth run**: the low-Se run "low_Se_test 1012" of 2026-10-12, which an AI agent operated on real hardware. An agent works through a lab-style `fese-lab` CLI. It watches RHEED-derived signals and temperatures, decides when and how to intervene, and is scored on the outcome and on the process separately.

## What is real and what is not

- **Measured:** 159 RHEED frames with CNN probabilities (2D/3D/STO), 242 frames with the W3D weak-3D index, 173 temperature readings and 15 hardware actions with acknowledgements. All of them were extracted verbatim from the session export of the real run. That export has sha256 `e05e8fed3b1edbb5db7e59d5869bb12c5b02c93ba48998ba051268dbdc0e0e60` and is not included here.
- **Not available:** the raw RHEED images, the lab-PC logs and any ex-situ film characterisation. CNN and W3D values are software features computed from the real images.
- **Derived:** the decision windows (SOP thresholds applied to the measured series) and the nominal thickness (0.2 layer/min × Fe-open time). See `derived/lineage_manifest.json`.
- **No simulation.** The environment is a *logged-data replay*. An action that matches the logged one and comes after its SOP trigger is visible in the data is applied at the logged time. Any other action ends the episode: as out-of-support, or as unevaluable when the action is SOP-valid but was never run. The replay tests monitoring, timing and evidence discipline. It makes no physical counterfactual claims.

## Tasks

| task | start / budget | decisions | tests |
|---|---|---|---|
| `tasks/fese-lowse-full-run` (hard) | 16:22:53, 500 queries | D1–D5 | strong-3D intervention, staged Se ramp, reopening Fe, weak-3D detection, stopping at 5 layers, cooldown |
| `tasks/fese-lowse-weak3d` (medium) | 16:36:12, 300 queries | D4, D5 | the weak-3D phase the CNN misses (CNN reports 2D while W3D > 0.10) |
| `tasks/fese-lowse-diagnose` (medium) | archive, 16 queries | – | 8 questions, each answer citing receipts from budgeted archive queries |

Each task has two containers:

- **`main`:** the agent's container, with only the CLI and the SOP.
- **`replay` sidecar:** holds the data, the private decision windows and a hash-chained audit log.

The verifier in `tests/` reads the audit log with a token and cross-checks `/app/report.json`. It writes `reward = outcome × evidence gate`; the components are in `details.json`. `solution/` holds a deterministic SOP policy that uses only the public CLI.

> Note: the decision windows and targets ship inside `environment/replay/` and `tests/`, as in any public Harbor task. Do not give the agent access to this repository during an evaluation.

## Results so far

All of these come from the files in `results/`.

- **Local controls:** 18 deterministic controls behave as expected, covering the oracle, a CNN-only baseline, forged receipts, a tampered claim, a forged audit file, skipped measurement, a privileged blind schedule, premature and out-of-domain actions, and token-less audit probes. One deliberate exploit probe **passes** with reward 0.997: it follows the leaked schedule and cites four cheap queries. The evidence gate is therefore a plausibility check only (`results/controls_results.json`).
- **Harbor docker:** the oracle scores 1.0 / 0.9999 / 0.9999 and `nop` scores 0 (`results/harbor_checks.json`).
- **DeepSeek-v4-pro + Claude Code 2.1.292**, 5 trials, one stack, not a model comparison (`results/agent_trials_summary.json`):
  - diagnose: 1.0;
  - weak3d, twice: unevaluable both times. The agent detected the weak-3D event on time but chose SeC 565 (SOP "+5"), while the operator ran 570;
  - full-run, twice: both handled D1 and then missed D2 while waiting too long for 2D recovery.

## Known limitations and exploit surface

- One run gives one path, so SOP-valid alternatives cannot be scored. The D2 window opens about 2 minutes earlier than the SOP's judgement rule implies. The evidence gate checks single records only.
- In trial t03 the agent ran `env`, which printed its API key into its own transcript; that key has been redacted. It also probed the Docker host gateway, where its POSTs were rejected. Keep model credentials outside the task container and isolate the task network from the host.
- The replay server does not log GET requests.

Details are in the reports, in English and Chinese: `report/`.

## Run

```bash
python3 bench/run_controls.py /tmp/controls          # 19 local cases, no Docker
python3 bench/build_tasks.py tasks/                  # rebuild tasks (regenerates verifier tokens)
harbor run -p tasks/fese-lowse-weak3d -a oracle -e docker
DEEPSEEK_API_KEY=... HARBOR=harbor bench/run_trial.sh fese-lowse-weak3d t01   # real agent trial
```

`viewer/fese-growth-chamber.html` is a single-file browser game and replay viewer. It uses a JS port of the replay engine, checked against the Python engine on 303 recorded events. A human can play the same tasks with the same commands and compare against the agent runs.

CLI and devices: the `fese-lab` interface follows the lab's own CLI (Eurotherm 3500 temperature controllers, CL57R shutters). This repository contains no device drivers, and nothing here controls real hardware.
