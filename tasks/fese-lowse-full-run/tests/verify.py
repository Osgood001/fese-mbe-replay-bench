#!/usr/bin/env python3
"""Protected verifier.  Reads the environment-owned audit export (from the replay
service, token-protected) and the agent's report; never trusts report claims
without cross-checking them against environment receipts.

python3 verify.py --audit-url http://replay:8080/audit --token-file /tests/verifier_token \
                  --report /app/report.json --targets /tests/targets.json --out /logs/verifier
"""
import argparse, json, os, re, sys, urllib.request

def parse_hms(s):
    p = [float(x) for x in str(s).strip().split(':')]
    while len(p) < 3: p.append(0.0)
    return p[0]*3600 + p[1]*60 + p[2]

def load_audit(a):
    if a.audit_file:
        return json.load(open(a.audit_file))
    tok = open(a.token_file).read().strip()
    req = urllib.request.Request(a.audit_url, headers={'X-Verifier-Token': tok})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=60) as r:
        return json.loads(r.read())

def receipt_times(ex):
    out = {}
    for ev in ex['events']:
        rid = (ev.get('response') or {}).get('receipt')
        if rid: out[rid] = ev['replay_t']
    return out

def frames_of(payload, chan):
    if payload.get('type') == chan: return payload.get('frames', [])
    if payload.get('type') == 'monitor': return payload.get('frames', {}).get(chan, [])
    return []

def temps_of(payload):
    if payload.get('type') == 'temp':
        return [{'device': r['device'], 'pv': r['pv']} for r in payload['records']]
    if payload.get('type') == 'monitor':
        return [{'device': 'sec', 'pv': r['sec_pv']} for r in payload.get('temps', [])]
    return []

SUPPORT = {
    'D1': lambda p: any(f['p3D'] > 0.5 for f in frames_of(p, 'cnn')),
    'D2': lambda p: any(r['device'] == 'sec' and r['pv'] >= 538.5 for r in temps_of(p)),
    'D3': lambda p: any(f['p2D'] > 0.9 and f['p3D'] < 0.1 for f in frames_of(p, 'cnn')),
    'D4': lambda p: any((f.get('W3D') or 0) > 0.10 for f in frames_of(p, 'w3d')),
    'D5': lambda p: p.get('type') == 'status' and p.get('fe_minutes', 0) >= 24.0,
}

def norm_cmd(s):
    s = re.sub(r'\s+', ' ', str(s).lower().replace('fese-lab', '').replace('--hardware', '')).strip()
    m = re.match(r'^(fe|sec) (open|close)', s)
    if m: return f'{m[1]}-{m[2]}', None
    m = re.match(r'^set-(fe|sec|seb) ([\d.]+)', s)
    if m: return f'set-{m[1]}', float(m[2])
    return s, None

def clip(x): return max(0.0, min(1.0, x))

def verify_control(ex, rep, notes):
    rt = receipt_times(ex)
    decisions = ex['decisions']; term = ex['terminal'] or 'unfinished'
    evaluable = not term.startswith('unevaluable')
    # ---------- outcome (environment-owned facts only) ----------
    stop = ex.get('stop'); comps = {'completed_in_support': 0.0, 'thickness': 0.0, 'film_state': 0.0, 'shutdown': 0.0}
    if term == 'stopped' and stop:
        comps['completed_in_support'] = 1.0
        comps['thickness'] = clip(1 - abs(stop['layers'] - ex['target_layers'])/0.5)
        cl = stop.get('cnn_last') or {}
        comps['film_state'] = 1.0 if (stop.get('w3d_last5_mean') is not None and stop['w3d_last5_mean'] < 0.08 and cl.get('label') == '2D') else 0.0
        sec_ok = stop.get('sec_closed_at') is not None and stop['sec_closed_at'] - stop['t'] <= 120
        cd = ex.get('cooldown', {})
        sb_ok = all(cd.get(d, {}).get('standby_match') for d in ('fe', 'sec', 'seb'))
        comps['shutdown'] = 0.5*sec_ok + 0.5*sb_ok
    outcome = comps['completed_in_support']*(0.5*comps['thickness'] + 0.3*comps['film_state'] + 0.2*comps['shutdown'])
    # ---------- process ----------
    lat = []
    for k, d in decisions.items():
        if k == 'D5' or not d['agent_times'] or d['window_open'] is None: continue
        L = d['boundary'] - d['window_open']
        lat.append(clip(1 - (d['agent_times'][0] - d['window_open'])/L))
    timeliness = sum(lat)/len(lat) if lat else 0.0
    efficiency = clip(1 - ex['queries_used']/ex['queries_max'])
    entries = (rep or {}).get('decisions', []) if isinstance(rep, dict) else []
    cited = [r for e in entries if isinstance(e, dict) for r in (e.get('evidence') or [])]
    fabricated = sorted({r for r in cited if r not in ex['receipts']})
    supported, needed, detail = 0, 0, {}
    for k, d in decisions.items():
        if not d['done']: continue
        needed += 1
        agent_t = d['agent_times'][0]
        cands = []
        for e in entries:
            if not isinstance(e, dict): continue
            nc = norm_cmd(e.get('command', ''))
            if any(nc == (x[0], x[1]) for x in d['done']):
                cands.append(e)
        ok = False
        for e in cands:
            for r in e.get('evidence') or []:
                if r in ex['receipts'] and rt.get(r, 1e18) <= agent_t + 1e-6 and SUPPORT[k](ex['receipts'][r]):
                    ok = True
        detail[k] = {'report_entry': bool(cands), 'supported': ok}
        supported += ok
    support_frac = supported/needed if needed else 0.0
    fin = (rep or {}).get('final', {}) if isinstance(rep, dict) else {}
    claims_ok = 1.0
    if stop:
        try:
            if abs(float(fin.get('layers')) - stop['layers']) > 0.05: claims_ok = 0.0
            if abs(parse_hms(fin.get('stopped_at')) - stop['t']) > 2: claims_ok = 0.0
        except (TypeError, ValueError):
            claims_ok = 0.0
    else:
        claims_ok = 1.0 if str(fin.get('terminal', '')).strip() == term else 0.0
    integrity = 0.0 if fabricated else 0.7*support_frac + 0.3*claims_ok
    gate = 1.0 if (not fabricated and needed and supported == needed and claims_ok == 1.0) else 0.0
    unlogged = term.startswith('out_of_support:unlogged') or term.startswith('out_of_support:premature')
    compliance = 0.0 if (unlogged or ex.get('violations')) else 1.0
    process = 0.3*timeliness + 0.2*efficiency + 0.35*integrity + 0.15*compliance
    notes.update(terminal=term, outcome_components=comps, decision_evidence=detail, fabricated_receipts=fabricated,
                 claims_consistent=claims_ok, violations=ex.get('violations'), queries_used=ex['queries_used'])
    return {'reward': round(outcome*gate, 4) if evaluable else 0.0, 'outcome': round(outcome, 4), 'process': round(process, 4),
            'evaluable': 1.0 if evaluable else 0.0, 'integrity_gate': gate, 'timeliness': round(timeliness, 4),
            'efficiency': round(efficiency, 4), 'integrity': round(integrity, 4), 'compliance': compliance,
            'decisions_done': float(sum(1 for d in decisions.values() if d['status'] == 'done')),
            'decisions_total': float(len(decisions))}

def verify_diagnose(ex, rep, targets, notes):
    ans = (rep or {}).get('answers', {}) if isinstance(rep, dict) else {}
    cited_all = [r for v in ans.values() if isinstance(v, dict) for r in (v.get('evidence') or [])]
    fabricated = sorted({r for r in cited_all if r not in ex['receipts']})
    correct = 0; supported = 0; per = {}
    for q, t in targets['questions'].items():
        a = ans.get(q) if isinstance(ans.get(q), dict) else {}
        v = a.get('value'); ok = False
        try:
            if t['kind'] == 'time': ok = abs(parse_hms(v) - parse_hms(t['value'])) <= t['tol']
            else: ok = abs(float(v) - float(t['value'])) <= t['tol']
        except (TypeError, ValueError):
            ok = False
        sup = False
        if t.get('evidence') is None:
            sup = True
        else:
            for r in a.get('evidence') or []:
                p = ex['receipts'].get(r)
                if p and evidence_ok(t['evidence'], p, t, v): sup = True
        per[q] = {'correct': ok, 'supported': sup}
        correct += ok; supported += sup
    n = len(targets['questions'])
    outcome = correct/n; support_frac = supported/n
    efficiency = clip(1 - ex['queries_used']/ex['queries_max'])
    integrity = 0.0 if fabricated else support_frac
    gate = 1.0 if (not fabricated and support_frac >= 0.999) else 0.0
    process = 0.6*integrity + 0.4*efficiency
    notes.update(per_question=per, fabricated_receipts=fabricated, queries_used=ex['queries_used'])
    return {'reward': round(outcome*gate, 4), 'outcome': round(outcome, 4), 'process': round(process, 4), 'evaluable': 1.0,
            'integrity_gate': gate, 'integrity': round(integrity, 4), 'efficiency': round(efficiency, 4)}

def evidence_ok(kind, p, t, v):
    recs = p.get('records', [])
    try:
        if kind == 'cnn_p3d_gt_0.5_near':
            return p['type'] == 'archive_cnn' and any(r['p3D'] > 0.5 and abs(parse_hms(r['capture_time']) - parse_hms(v)) <= t['tol'] for r in recs)
        if kind == 'w3d_gt_0.10_near':
            return p['type'] == 'archive_w3d' and any((r.get('W3D') or 0) > 0.10 and abs(parse_hms(r['capture_time']) - parse_hms(v)) <= t['tol'] for r in recs)
        if kind == 'w3d_value':
            return p['type'] == 'archive_w3d' and any(r.get('W3D') is not None and abs(r['W3D'] - float(v)) < 1e-9 for r in recs)
        if kind == 'cnn_p3d_value':
            return p['type'] == 'archive_cnn' and any(abs(r['p3D'] - float(v)) < 1e-9 for r in recs)
        if kind.startswith('action_set_sec_'):
            want = float(kind.rsplit('_', 1)[1])
            return p['type'] == 'archive_actions' and any(r['cmd'] == 'set-sec' and r['value'] == want for r in recs)
        if kind == 'fe_actions':
            return p['type'] == 'archive_actions' and sum(r['cmd'] in ('fe-open', 'fe-close') for r in recs) >= 2
    except (TypeError, ValueError, KeyError):
        return False
    return False

def targets_task(a):
    try: return json.load(open(a.targets)).get('task')
    except Exception: return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--audit-url', default='http://replay:8080/audit'); ap.add_argument('--audit-file')
    ap.add_argument('--token-file', default='/tests/verifier_token'); ap.add_argument('--report', default='/app/report.json')
    ap.add_argument('--targets', default='/tests/targets.json'); ap.add_argument('--out', default='/logs/verifier')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    notes = {}
    try:
        ex = load_audit(a)
    except Exception as e:  # environment unavailable -> cannot verify; never fall back to agent files
        json.dump({'reward': 0.0}, open(f'{a.out}/reward.json', 'w'))
        json.dump({'verifier_error': str(e)}, open(f'{a.out}/details.json', 'w'))
        print('audit unavailable:', e); return 0
    try:
        rep = json.load(open(a.report))
    except Exception as e:
        rep = None; notes['report_error'] = str(e)
    if targets_task(a) and ex.get('task') != targets_task(a):
        res = {'reward': 0.0}; notes['task_mismatch'] = [ex.get('task'), targets_task(a)]
    elif ex['mode'] == 'diagnose':
        res = verify_diagnose(ex, rep, json.load(open(a.targets)), notes)
    else:
        res = verify_control(ex, rep, notes)
    json.dump({'reward': res['reward']}, open(f'{a.out}/reward.json', 'w'))  # Harbor: single key
    json.dump({'result': res, 'notes': notes, 'chain_head': ex['chain_head'], 'n_events': len(ex['events'])},
              open(f'{a.out}/details.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(ex, open(f'{a.out}/audit_export.json', 'w'))
    print(json.dumps(res))
    return 0

if __name__ == '__main__':
    sys.exit(main())
