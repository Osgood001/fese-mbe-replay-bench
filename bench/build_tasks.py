"""Assemble Harbor task directories from bench/common + data.  python3 build_tasks.py <out_dir>"""
import json, os, secrets, shutil, sys, hashlib
B = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(B); C = f'{B}/common'
OUT = sys.argv[1] if len(sys.argv) > 1 else f'{B}/tasks'
BASE = os.environ.get('BASE_IMAGE', 'python:3.12-slim')

CLI_DOC = """## The `fese-lab` CLI (replay edition)
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
"""

REPLAY_DOC = """## What this environment is (read carefully)
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
"""

REPORT_CONTROL = """## Deliverable: `/app/report.json`
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
"""

INSTR = {
'fese-lowse-full-run': """# FeSe low-Se MBE growth: run the growth loop on a replay of a real run

You are the growth operator of an FeSe thin-film MBE system (Fe Knudsen cell, Se cracker SeC/SeB,
RHEED camera). The goal is **5 FeSe layers** (growth rate 0.2 layer/min, counted only while the Fe
shutter is open) ending with a clean 2D surface, following the lab SOP in `/app/docs/SOP.md`.

Current state (replay clock 16:22:53): Fe 1100 C, SeC 520 C (low-Se start), SeB 90 C; the Se shutter
opened at 16:22:25 and the Fe shutter at 16:22:52. Growth has just started.

Your job: monitor RHEED (CNN and W3D channels) and temperatures, apply the SOP interventions when
their triggers appear, stop the growth at 5 layers (close Fe and Se shutters), then return the sources
to the standby setpoints recorded before the run (Fe 800, SeC 400, SeB 48.7). Then write the report.
Measurement budget: 500 queries.

{replay}
{cli}
{report}""",
'fese-lowse-weak3d': """# FeSe low-Se MBE growth: second growth period (weak-3D risk) on a replay of a real run

You are the growth operator of an FeSe thin-film MBE system. Target: **5 FeSe layers** (0.2 layer/min,
counted only while the Fe shutter is open) ending with a clean 2D surface, following `/app/docs/SOP.md`.

Current state (replay clock 16:36:12): after a strong-3D episode earlier in this run, the Se cracker was
raised to SeC 560 C, 2D recovered, and the Fe shutter was reopened at 16:36:11. Fe-open time so far:
3.4 min. Fe 1100 C, SeB 90 C, both shutters open.

Your job: keep monitoring, apply SOP interventions when their triggers appear, stop at 5 layers
(close Fe and Se shutters), return the sources to standby (Fe 800, SeC 400, SeB 48.7), and write the
report. Measurement budget: 300 queries.

{replay}
{cli}
{report}""",
'fese-lowse-diagnose': """# FeSe low-Se MBE run: evidence-backed diagnosis under a query budget

A real FeSe MBE growth run (2026-10-12, "low_Se_test 1012", target 5 layers, low-Se start SeC 520 C)
has finished. Its measured records are archived behind `fese-lab archive` (CNN and W3D values of
analysed RHEED frames, temperature readings, and the hardware action log). The protocol the operator
followed is in `/app/docs/SOP.md`.

Query: `fese-lab archive cnn|w3d|temps|actions --from HH:MM:SS --to HH:MM:SS` returns at most 20
records (earliest first; `truncated` tells you whether more exist). **Budget: 16 queries in total.**
Each response has a receipt id. `fese-lab status` is free.

Answer the questions below in `/app/report.json` as
`{{"answers": {{"q1_strong3d_onset_time": {{"value": "HH:MM:SS", "evidence": ["R0003"]}}, ...}}}}`.
Each answer must cite the receipt(s) whose records directly contain the supporting value (for setpoint
questions cite the action-log receipt). Times are frame capture times (HH:MM:SS).

{questions}

Notes: all data are real measurements; analysed frames are irregularly spaced. Do not guess - unsupported
answers score zero.
""",
}

def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()

def write(p, s, mode=None):
    os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(s)
    if mode: os.chmod(p, mode)

def build(name):
    td = f'{OUT}/{name}'; shutil.rmtree(td, ignore_errors=True)
    task = json.load(open(f'{B}/tasks_src/{name}/task.json'))
    targets = json.load(open(f'{B}/tasks_src/{name}/targets.json'))
    token = secrets.token_hex(24)
    # --- instruction
    if name == 'fese-lowse-diagnose':
        qs = '\n'.join(f"{i}. `{k}` - {v['text']}" for i, (k, v) in enumerate(targets['questions'].items(), 1))
        instr = INSTR[name].format(questions=qs)
    else:
        instr = INSTR[name].format(replay=REPLAY_DOC, cli=CLI_DOC, report=REPORT_CONTROL)
    write(f'{td}/instruction.md', instr)
    # --- environment: main container (agent side) has only the CLI + SOP doc
    env = f'{td}/environment'
    os.makedirs(env, exist_ok=True); shutil.copy(f'{C}/fese_lab_cli.py', f'{env}/fese-lab')
    sop = ("# Lab SOP excerpt (real protocol file experiments/fese_grow_v2.md used during the run; Chinese original)\n\n"
           "Mapping to the replay CLI: `poll_cnn.py`/`watch_alert.py` -> `fese-lab rheed cnn` / `monitor --channels cnn`; "
           "`rheed_w3d.py` -> `fese-lab rheed w3d` / `monitor --channels w3d`; `poll_temps.py` -> `fese-lab get-pv` / `monitor --channels temp`.\n"
           "English gist: strong 3D (CNN p3D>0.5 sustained) -> close Fe, SeC +20 C, wait for 2D recovery (~2 min after the setpoint is reached), "
           "reopen Fe; if not recovered +20 again. Weak 3D (CNN p3D<0.3 but W3D>0.10 for >=5 frames) -> SeC +5..10 C, keep Fe open, re-check W3D; "
           "W3D 0.08-0.10 = grey zone, observe. Growth 0.2 layer/min of Fe-open time; stop = close both shutters; then return setpoints to standby.\n\n")
    write(f'{env}/docs/SOP.md', sop + open(f'{B}/assets/sop_excerpt_zh.md').read())
    write(f'{env}/Dockerfile', f"""FROM {BASE}
ENV PYTHONDONTWRITEBYTECODE=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 IS_SANDBOX=1
ARG INSTALL_AGENT=0
# optional: preinstall the Claude Code harness (pinned) for agent trials; no credentials in the image
RUN if [ "$INSTALL_AGENT" = "1" ]; then \\
      pip install -q --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple nodejs-wheel==24.* && \\
      npm install -g --prefix /usr/local --registry=https://registry.npmmirror.com @anthropic-ai/claude-code@2.1.292 && \\
      claude --version; fi
COPY fese-lab /usr/local/bin/fese-lab
COPY docs /app/docs
RUN chmod 755 /usr/local/bin/fese-lab
WORKDIR /app
ENV FESE_REPLAY_URL=http://replay:8080
""")
    # --- replay sidecar (environment-owned; holds data, private decision windows, audit, verifier token)
    rp = f'{env}/replay'; os.makedirs(f'{rp}/data', exist_ok=True)
    for f in ('mbe_replay_env.py', 'replay_server.py'): shutil.copy(f'{C}/{f}', f'{rp}/{f}')
    shutil.copy(f'{ROOT}/derived/replay_dataset_1012.json', f'{rp}/data/replay_dataset.json')
    shutil.copy(f'{ROOT}/data_private/decision_points.json', f'{rp}/data/decision_points.json')
    json.dump(task, open(f'{rp}/data/task.json', 'w'), indent=1)
    write(f'{rp}/Dockerfile', f"""FROM {BASE}
ENV PYTHONDONTWRITEBYTECODE=1
COPY mbe_replay_env.py replay_server.py /srv/replay/
COPY data /srv/replay/data
EXPOSE 8080
CMD ["python3", "-I", "/srv/replay/replay_server.py"]
""")
    write(f'{env}/docker-compose.yaml', f"""# merged on top of Harbor's base compose; `main` is the agent container.
services:
  main:
    build:
      args:
        INSTALL_AGENT: ${{FESE_INSTALL_AGENT:-0}}
    depends_on:
      replay:
        condition: service_healthy
  replay:
    build:
      context: ./replay
    environment:
      REPLAY_VERIFIER_TOKEN: "{token}"
      REPLAY_TASK_NAME: "{name}"
    expose:
      - "8080"
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 256M
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"]
      interval: 2s
      timeout: 5s
      retries: 20
      start_period: 3s
""")
    # --- tests (copied in only for verification)
    tests = f'{td}/tests'; os.makedirs(tests, exist_ok=True)
    shutil.copy(f'{C}/verify.py', f'{tests}/verify.py')
    write(f'{tests}/verifier_token', token + '\n')
    targets['task'] = name
    json.dump(targets, open(f'{tests}/targets.json', 'w'), indent=1)
    write(f'{tests}/test.sh', """#!/bin/bash
mkdir -p /logs/verifier
python3 -I /tests/verify.py --audit-url http://replay:8080/audit --token-file /tests/verifier_token \\
  --report /app/report.json --targets /tests/targets.json --out /logs/verifier
""", 0o755)
    # --- oracle solution (non-privileged SOP policy using only the public CLI)
    sol = f'{td}/solution'; os.makedirs(sol, exist_ok=True)
    if task['mode'] == 'diagnose':
        shutil.copy(f'{C}/diag_policy.py', f'{sol}/diag_policy.py')
        write(f'{sol}/solve.sh', '#!/bin/bash\nset -e\npython3 -I /solution/diag_policy.py --report /app/report.json\n', 0o755)
    else:
        shutil.copy(f'{C}/sop_policy.py', f'{sol}/sop_policy.py')
        write(f'{sol}/solve.sh', '#!/bin/bash\nset -e\npython3 -I /solution/sop_policy.py --channels cnn,w3d --report /app/report.json\n', 0o755)
    diff = {'fese-lowse-full-run': 'hard', 'fese-lowse-weak3d': 'medium', 'fese-lowse-diagnose': 'medium'}[name]
    write(f'{td}/task.toml', f"""version = "1.0"

[metadata]
author_name = "fese-replay-benchmark (Claude lead), data: low_Se_test 1012 real run"
difficulty = "{diff}"
category = "scientific-experimentation"
tags = ["mbe", "fese", "rheed", "replay", "interactive", "materials-science"]
keywords = ["mbe", "fese", "rheed", "logged-replay", "interactive-experiment", "deterministic-verifier"]

[verifier]
timeout_sec = 300.0

[agent]
timeout_sec = 1800.0

[environment]
build_timeout_sec = 900.0
cpus = 1
memory_mb = 1536
storage_mb = 4096
allow_internet = true
""")
    write(f'{td}/README.md', f"""# {name}

Interactive Harbor task built from a **real** FeSe MBE run (raw trace `low_se_test-1012-20261012.json`,
sha256 `{json.load(open(f'{ROOT}/derived/replay_dataset_1012.json'))['source']['sha256']}`).

* `environment/` - agent container (CLI + SOP only) and `replay/` sidecar (measured data, private decision
  windows, environment-owned audit log, verifier token). The agent never sees `replay/`.
* `tests/` - protected verifier; pulls the audit log from the sidecar with a token, cross-checks the
  agent report, writes `reward.json` (`reward` = outcome x integrity gate; `outcome`, `process`, components).
* `solution/` - deterministic, non-privileged SOP policy (oracle).
* Mode: `{task['mode']}`; start {task['start']}; decision points {task.get('decisions')}; query budget {task['max_queries']}.
* Replay semantics: observed actions replay real data; unlogged actions terminate (out-of-support) or are
  marked unevaluable when SOP-consistent. No physical counterfactual is claimed.
""")
    return td

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    man = {}
    for n in ('fese-lowse-full-run', 'fese-lowse-weak3d', 'fese-lowse-diagnose'):
        td = build(n)
        man[n] = {os.path.relpath(os.path.join(dp, f), td): sha(os.path.join(dp, f)) for dp, _, fs in os.walk(td) for f in fs}
    json.dump(man, open(f'{OUT}/MANIFEST.sha256.json', 'w'), indent=1)
    print('built', list(man), sum(len(v) for v in man.values()), 'files')
