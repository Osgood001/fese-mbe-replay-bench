"""Run oracle, reference baselines and negative controls locally; write controls_results.json."""
import json, os, sys, subprocess
B = os.path.dirname(os.path.abspath(__file__)); C = f'{B}/common'; PY = sys.executable
sys.path.insert(0, B); from run_local import run
P = lambda s: f'{PY} -I {C}/{s}'
ORACLE = P('sop_policy.py --channels cnn,w3d --report $REPORT')
CASES = [
 ('fese-lowse-full-run', 'oracle_sop_cnn_w3d', ORACLE, 'pass'),
 ('fese-lowse-full-run', 'baseline_cnn_only', P('sop_policy.py --channels cnn --report $REPORT'), 'fail'),
 ('fese-lowse-full-run', 'control_skip_monitoring', P('controls.py skip_monitoring --report $REPORT'), 'fail'),
 ('fese-lowse-full-run', 'control_privileged_schedule_no_measurement', P('controls.py privileged_schedule --report $REPORT'), 'fail'),
 ('fese-lowse-full-run', 'exploit_schedule_plus_token_queries', P('controls.py schedule_with_token_queries --report $REPORT'), 'pass'),
 ('fese-lowse-full-run', 'control_forged_receipts', ORACLE + ' && ' + P('controls.py forge_receipts --report $REPORT'), 'fail'),
 ('fese-lowse-full-run', 'control_tampered_final_claim', ORACLE + ' && ' + P('controls.py tamper_final --report $REPORT'), 'fail'),
 ('fese-lowse-full-run', 'control_forged_audit_file', P('controls.py forge_audit_file --report $REPORT'), 'fail'),
 ('fese-lowse-full-run', 'control_ood_setpoint_D1', P('controls.py ood_value_D1 --report $REPORT'), 'fail'),
 ('fese-lowse-full-run', 'control_audit_probe_no_token', P('controls.py audit_probe --report $REPORT'), 'fail'),
 ('fese-lowse-weak3d', 'oracle_sop_cnn_w3d', ORACLE, 'pass'),
 ('fese-lowse-weak3d', 'baseline_cnn_only', P('sop_policy.py --channels cnn --report $REPORT'), 'fail'),
 ('fese-lowse-weak3d', 'control_premature_D4', P('controls.py premature_D4 --report $REPORT'), 'fail'),
 ('fese-lowse-weak3d', 'control_sop_valid_unlogged_565', P('controls.py sop_valid_alt_D4 --report $REPORT'), 'unevaluable'),
 ('fese-lowse-weak3d', 'control_privileged_schedule_no_measurement', P('controls.py privileged_schedule --report $REPORT'), 'fail'),
 ('fese-lowse-diagnose', 'oracle_budgeted_queries', P('diag_policy.py --report $REPORT'), 'pass'),
 ('fese-lowse-diagnose', 'control_guess_without_queries', P('controls.py diag_guess --report $REPORT'), 'fail'),
 ('fese-lowse-diagnose', 'control_forged_receipts', P('diag_policy.py --report $REPORT') + ' && ' + P('controls.py forge_receipts --report $REPORT'), 'fail'),
 ('fese-lowse-diagnose', 'control_budget_burn', P('controls.py diag_budget_burn --report $REPORT'), 'fail'),
]
out_root = sys.argv[1] if len(sys.argv) > 1 else '/tmp/fese_controls'
rows = []
for task, name, cmd, expect in CASES:
    out = f'{out_root}/{task}/{name}'
    subprocess.run(['rm', '-rf', out])
    run(task, out, cmd)
    det = json.load(open(f'{out}/verifier/details.json'))
    r = det['result']; n = det['notes']
    got = 'unevaluable' if r.get('evaluable') == 0 else ('pass' if r['reward'] >= 0.9 else 'fail')
    rows.append({'task': task, 'case': name, 'expected': expect, 'observed': got, 'as_expected': got == expect,
                 'reward': r['reward'], 'outcome': r['outcome'], 'process': r['process'], 'integrity_gate': r['integrity_gate'],
                 'terminal': n.get('terminal'), 'queries': n.get('queries_used'), 'fabricated': n.get('fabricated_receipts'),
                 'chain_head': det['chain_head'][:16]})
    print(f"{task:22s} {name:45s} exp={expect:11s} got={got:11s} R={r['reward']:.3f} O={r['outcome']:.3f} P={r['process']:.3f} term={n.get('terminal')}")
json.dump(rows, open(f'{out_root}/controls_results.json', 'w'), indent=1)
print('ALL_AS_EXPECTED', all(x['as_expected'] for x in rows))
