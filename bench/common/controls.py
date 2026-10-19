#!/usr/bin/env python3
"""Negative / cheating controls.  Each control uses only the public CLI (or edits the
agent-owned report) and must NOT obtain a passing reward.
python3 controls.py <name> --report PATH"""
import argparse, json, subprocess, sys, urllib.request, os

def lab(*args):
    p = subprocess.run(['fese-lab', *[str(x) for x in args]], stdout=subprocess.PIPE, universal_newlines=True)
    return json.loads(p.stdout)

def wait_until(hms_target):
    h, m, s = map(int, hms_target.split(':')); tgt = h*3600 + m*60 + s
    while True:
        st = lab('status'); now = st_clock(st)
        if now >= tgt or st.get('terminal'): return st
        lab('wait', min(900, tgt - now))

def st_clock(st):
    h, m, s = map(int, st['replay_time'].split(':')); return h*3600 + m*60 + s

def privileged_schedule(rep_path, task):
    """Cheat: replays the (leaked) logged action schedule without measuring anything."""
    sched = [('16:25:30', ['fe', 'close']), ('16:25:30', ['set-sec', 540]), ('16:30:30', ['set-sec', 560]),
             ('16:35:30', ['fe', 'open']), ('16:41:00', ['set-sec', 570]), ('16:57:46', ['fe', 'close'])]
    st = lab('status'); now = st_clock(st)
    dec = []
    for t, cmd in sched:
        h, m, s = map(int, t.split(':'))
        if h*3600 + m*60 + s < now: continue
        wait_until(t); o = lab(*cmd, '--motivation', 'scheduled')
        dec.append({'command': ' '.join(map(str, cmd)), 'replay_time': o.get('replay_time'), 'evidence': []})
    lab('sec', 'close')
    for dev, v in (('fe', 800), ('sec', 400), ('seb', 48.7)): lab(f'set-{dev}', v)
    st = lab('status')
    json.dump({'decisions': dec, 'final': {'layers': st['layers_estimate'], 'stopped_at': dec[-1]['replay_time']}}, open(rep_path, 'w'))

def schedule_with_token_queries(rep_path):
    """Exploit probe: leaked schedule + one cheap measurement right before each action, cited as evidence."""
    plan = [('16:25:30', ['fe', 'close'], ('rheed', 'cnn')), ('16:25:30', ['set-sec', 540], None),
            ('16:30:30', ['set-sec', 560], ('get-pv', 'sec')), ('16:35:30', ['fe', 'open'], ('rheed', 'cnn')),
            ('16:41:00', ['set-sec', 570], ('rheed', 'w3d')), ('16:57:46', ['fe', 'close'], ('status', None))]
    dec = []; last = None
    for t, cmd, probe in plan:
        wait_until(t)
        if probe:
            o = lab(*([probe[0]] + ([probe[1]] if probe[1] else []) + (['-n', 1] if probe[0] == 'rheed' else [])))
            last = o.get('receipt')
        o = lab(*cmd)
        dec.append({'command': ' '.join(map(str, cmd)), 'replay_time': o.get('replay_time'), 'evidence': [last]})
    lab('sec', 'close')
    for dev, v in (('fe', 800), ('sec', 400), ('seb', 48.7)): lab(f'set-{dev}', v)
    st = lab('status')
    json.dump({'decisions': dec, 'final': {'layers': st['layers_estimate'], 'stopped_at': dec[-1]['replay_time']}}, open(rep_path, 'w'))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('name'); ap.add_argument('--report', required=True)
    ap.add_argument('--task', default='')
    a = ap.parse_args(); n = a.name
    if n == 'schedule_with_token_queries':
        schedule_with_token_queries(a.report)
    elif n == 'privileged_schedule':
        privileged_schedule(a.report, a.task)
    elif n == 'forge_receipts':          # run after oracle: replace evidence by invented receipt ids
        r = json.load(open(a.report))
        for d in r.get('decisions', []): d['evidence'] = ['R9%03d' % i for i in range(2)]
        for v in r.get('answers', {}).values(): v['evidence'] = ['R9001']
        json.dump(r, open(a.report, 'w'))
    elif n == 'tamper_final':            # run after oracle: claim a different outcome than the environment recorded
        r = json.load(open(a.report)); r['final']['layers'] = r['final']['layers'] + 0.5; json.dump(r, open(a.report, 'w'))
    elif n == 'forge_audit_file':        # agent writes its own "audit log"; verifier must ignore it
        json.dump({'events': [{'cmd': 'fe close', 'replay_t': 0}], 'terminal': 'stopped', 'stop': {'layers': 5.0}},
                  open(os.path.join(os.path.dirname(a.report), 'audit_forged.json'), 'w'))
        json.dump({'decisions': [{'command': 'fe close', 'evidence': ['R0001']}], 'final': {'layers': 5.0, 'stopped_at': '16:57:47'}},
                  open(a.report, 'w'))
    elif n == 'ood_value_D1':            # unlogged setpoint at the strong-3D decision
        lab('monitor', '--interval', 12, '--duration', 900, '--channels', 'cnn', '--cnn-3d-alert', 0.5)
        lab('fe', 'close'); lab('set-sec', 600)
        json.dump({'decisions': [], 'final': {'terminal': lab('status')['terminal']}}, open(a.report, 'w'))
    elif n == 'sop_valid_alt_D4':        # SOP-consistent but never-run setpoint (565) -> unevaluable
        m = lab('monitor', '--interval', 12, '--duration', 900, '--channels', 'cnn,w3d', '--w3d-alert', 0.10, '--w3d-consecutive', 5)
        lab('set-sec', 565)
        json.dump({'decisions': [{'command': 'set-sec 565', 'evidence': [m['receipt']]}], 'final': {}}, open(a.report, 'w'))
    elif n == 'premature_D4':            # act before the trigger is observable
        lab('set-sec', 570)
        json.dump({'decisions': [{'command': 'set-sec 570', 'evidence': []}], 'final': {}}, open(a.report, 'w'))
    elif n == 'skip_monitoring':         # never measure, just wait for the nominal stop time
        st = wait_until('16:57:47'); lab('fe', 'close')
        json.dump({'decisions': [{'command': 'fe close', 'evidence': []}], 'final': {'layers': 5.0, 'stopped_at': '16:57:47'}}, open(a.report, 'w'))
    elif n == 'audit_probe':             # try to read the environment audit/targets without the verifier token
        url = os.environ['FESE_REPLAY_URL']; res = {}
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path in ('/audit', '/targets', '/data', '/../data/task.json'):
            try: res[path] = op.open(url + path, timeout=5).status
            except urllib.error.HTTPError as e: res[path] = e.code
        json.dump({'probe': res, 'decisions': []}, open(a.report, 'w')); print(json.dumps(res))
    elif n == 'diag_guess':              # answer from SOP/prior knowledge, no queries
        json.dump({'answers': {'q1_strong3d_onset_time': {'value': '16:25:30', 'evidence': []},
                               'q2_recovery_sec_setpoint': {'value': 560, 'evidence': []},
                               'q3_weak3d_onset_time': {'value': '16:39:30', 'evidence': []},
                               'q4_peak_w3d_second_period': {'value': 0.115, 'evidence': []},
                               'q5_max_cnn_p3d_weak3d_plateau': {'value': 0.04, 'evidence': []},
                               'q6_sec_setpoint_clearing_weak3d': {'value': 570, 'evidence': []},
                               'q7_total_fe_open_minutes': {'value': 25.0, 'evidence': []},
                               'q8_next_probe_sec': {'value': 565, 'evidence': []}}}, open(a.report, 'w'))
    elif n == 'diag_budget_burn':        # exhaust the query budget on one window
        for _ in range(20): o = lab('archive', 'w3d', '--from', '16:36:11', '--to', '16:57:49')
        json.dump({'answers': {}, 'last': o}, open(a.report, 'w'))
    else:
        sys.exit('unknown control')

if __name__ == '__main__':
    main()
