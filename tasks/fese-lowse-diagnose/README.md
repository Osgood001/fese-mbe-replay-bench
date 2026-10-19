# fese-lowse-diagnose

Interactive Harbor task built from a **real** FeSe MBE run (raw trace `low_se_test-1012-20261012.json`,
sha256 `e05e8fed3b1edbb5db7e59d5869bb12c5b02c93ba48998ba051268dbdc0e0e60`).

* `environment/` - agent container (CLI + SOP only) and `replay/` sidecar (measured data, private decision
  windows, environment-owned audit log, verifier token). The agent never sees `replay/`.
* `tests/` - protected verifier; pulls the audit log from the sidecar with a token, cross-checks the
  agent report, writes `reward.json` (`reward` = outcome x integrity gate; `outcome`, `process`, components).
* `solution/` - deterministic, non-privileged SOP policy (oracle).
* Mode: `diagnose`; start 17:19:06; decision points []; query budget 16.
* Replay semantics: observed actions replay real data; unlogged actions terminate (out-of-support) or are
  marked unevaluable when SOP-consistent. No physical counterfactual is claimed.
