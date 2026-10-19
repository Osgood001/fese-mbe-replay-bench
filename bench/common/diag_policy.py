#!/usr/bin/env python3
"""Deterministic oracle for the diagnose task: budgeted archive queries via the public CLI."""
import argparse, json, subprocess, sys

def lab(*args):
    p = subprocess.run(['fese-lab', *[str(x) for x in args]], stdout=subprocess.PIPE, universal_newlines=True)
    return json.loads(p.stdout)

def sec(s):
    h, m, x = s.split(':'); return int(h)*3600 + int(m)*60 + float(x)

def hms(t):
    t = int(round(t)); return f"{t//3600:02d}:{t%3600//60:02d}:{t%60:02d}"

def scan(chan, t0, t1):
    """page through [t0,t1]; returns (records, receipts)"""
    recs, rids, cur = [], [], t0
    while cur <= t1:
        o = lab('archive', chan, '--from', hms(cur), '--to', hms(t1))
        if not o.get('ok'): break
        rids.append(o['receipt']); recs += [dict(r, _rid=o['receipt']) for r in o['records']]
        if not o['truncated']: break
        cur = sec(o['records'][-1]['capture_time']) + 1
    return recs, rids

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--report', default='/app/report.json'); a = ap.parse_args()
    acts = lab('archive', 'actions', '--from', '15:00:00', '--to', '17:30:00')
    A, ra = acts['records'], acts['receipt']
    fe = [sec(x['time']) for x in A if x['cmd'] in ('fe-open', 'fe-close')]
    fe_min = sum(b - a for a, b in zip(fe[0::2], fe[1::2])) / 60
    fe_open1 = fe[0]
    cnn, _ = scan('cnn', fe_open1, fe_open1 + 240)
    on = next(r for r in cnn if r['p3D'] > 0.5)
    reopen = fe[2]; stop = fe[3]
    w3d, _ = scan('w3d', reopen, stop)
    run, w_on = [], None
    for r in w3d:
        run = run + [r] if (r.get('W3D') or 0) > 0.10 else []
        if len(run) >= 5: w_on = run[0]; break
    pk = max((r for r in w3d if r.get('W3D') is not None), key=lambda r: r['W3D'])
    sets = [x for x in A if x['cmd'] == 'set-sec']
    weak_fix = next(x for x in sets if sec(x['time']) > sec(w_on['capture_time']))
    plat, _ = scan('cnn', sec(w_on['capture_time']), sec(weak_fix['time']))
    cm = max(plat, key=lambda r: r['p3D'])
    rec_sp = [x for x in sets if fe[1] < sec(x['time']) < reopen][-1]
    ans = {
        'q1_strong3d_onset_time': {'value': on['capture_time'], 'evidence': [on['_rid']]},
        'q2_recovery_sec_setpoint': {'value': rec_sp['value'], 'evidence': [ra]},
        'q3_weak3d_onset_time': {'value': w_on['capture_time'], 'evidence': [w_on['_rid']]},
        'q4_peak_w3d_second_period': {'value': pk['W3D'], 'evidence': [pk['_rid']]},
        'q5_max_cnn_p3d_weak3d_plateau': {'value': cm['p3D'], 'evidence': [cm['_rid']]},
        'q6_sec_setpoint_clearing_weak3d': {'value': weak_fix['value'], 'evidence': [ra]},
        'q7_total_fe_open_minutes': {'value': round(fe_min, 2), 'evidence': [ra]},
        'q8_next_probe_sec': {'value': (rec_sp['value'] + weak_fix['value']) / 2, 'evidence': []},
    }
    json.dump({'answers': ans}, open(a.report, 'w'), indent=1)
    print(json.dumps({k: v['value'] for k, v in ans.items()}))

if __name__ == '__main__':
    sys.exit(main())
