# FeSe low-Se MBE run: evidence-backed diagnosis under a query budget

A real FeSe MBE growth run (2026-10-12, "low_Se_test 1012", target 5 layers, low-Se start SeC 520 C)
has finished. Its measured records are archived behind `fese-lab archive` (CNN and W3D values of
analysed RHEED frames, temperature readings, and the hardware action log). The protocol the operator
followed is in `/app/docs/SOP.md`.

Query: `fese-lab archive cnn|w3d|temps|actions --from HH:MM:SS --to HH:MM:SS` returns at most 20
records (earliest first; `truncated` tells you whether more exist). **Budget: 16 queries in total.**
Each response has a receipt id. `fese-lab status` is free.

Answer the questions below in `/app/report.json` as
`{"answers": {"q1_strong3d_onset_time": {"value": "HH:MM:SS", "evidence": ["R0003"]}, ...}}`.
Each answer must cite the receipt(s) whose records directly contain the supporting value (for setpoint
questions cite the action-log receipt). Times are frame capture times (HH:MM:SS).

1. `q1_strong3d_onset_time` - Capture time of the first analysed RHEED frame after the Fe shutter opened (16:22:52) with CNN p3D > 0.5.
2. `q2_recovery_sec_setpoint` - SeC setpoint (degC) at which 2D growth recovered after the strong-3D event.
3. `q3_weak3d_onset_time` - After the Fe shutter reopened (16:36:11): capture time of the first frame of the first run of >=5 consecutive analysed frames with W3D > 0.10.
4. `q4_peak_w3d_second_period` - Maximum W3D among analysed frames captured between 16:36:11 and 16:57:49.
5. `q5_max_cnn_p3d_weak3d_plateau` - Maximum CNN p3D among analysed frames captured from the weak-3D onset (q3) to the SeC change at 16:41:51.
6. `q6_sec_setpoint_clearing_weak3d` - SeC setpoint (degC) in effect when W3D fell back below 0.08.
7. `q7_total_fe_open_minutes` - Total Fe-shutter-open time (minutes) of the run.
8. `q8_next_probe_sec` - Lowest untested SeC setpoint (5 degC granularity) between the last insufficient and the first sufficient setpoint for clearing weak 3D.

Notes: all data are real measurements; analysed frames are irregularly spaced. Do not guess - unsupported
answers score zero.
