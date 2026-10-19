#!/usr/bin/env python3
"""Deterministic SOP policy (oracle / reference baselines).  Uses only the public
fese-lab CLI and the SOP thresholds from fese_grow_v2.md; no private data.

  --channels cnn,w3d   oracle (SOP with weak-3D W3D channel)
  --channels cnn       CNN-only reference baseline (ignores W3D)
"""
import argparse, json, subprocess, sys

LOG = []

def lab(*args):
    p = subprocess.run(['fese-lab', *[str(x) for x in args]], stdout=subprocess.PIPE, universal_newlines=True)
    out = json.loads(p.stdout)
    LOG.append({'cmd': ' '.join(str(x) for x in args), 'ok': out.get('ok'), 'receipt': out.get('receipt'),
                'replay_time': out.get('replay_time'), 'alert': out.get('alert')})
    return out

def ended(o):
    ep = o.get('episode') or {}
    return ep.get('terminal') not in (None, 'stopped')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--channels', default='cnn,w3d'); ap.add_argument('--report', default='/app/report.json')
    ap.add_argument('--interval', type=float, default=12); ap.add_argument('--target-minutes', type=float, default=25.0)
    a = ap.parse_args()
    use_w3d = 'w3d' in a.channels
    decisions = []
    weak_adjusted = False
    st = lab('status')
    sp = st['setpoints']['sec']

    def decide(cmd_args, evidence, why):
        o = lab(*cmd_args, '--motivation', why)
        decisions.append({'command': ' '.join(str(x) for x in cmd_args), 'replay_time': o.get('replay_time'),
                          'evidence': [e for e in evidence if e], 'rationale': why, 'ok': o.get('ok')})
        return o

    while True:
        st = lab('status')
        if st.get('terminal') or st['growth_stopped']: break
        fe_open = st['shutters']['fe'] == 'open'
        if fe_open:
            remaining = (a.target_minutes - st['fe_open_minutes']) * 60
            if remaining <= 0.5:
                decide(['fe', 'close'], [st['receipt']], f"stop: Fe-open {st['fe_open_minutes']:.2f} min -> {st['layers_estimate']:.2f} layers")
                break
            mon = ['monitor', '--interval', a.interval, '--duration', min(900, max(1, remaining)), '--channels', a.channels,
                   '--cnn-3d-alert', 0.5, '--consecutive', 2]
            # after a weak-3D Se adjustment keep only a deterioration guard (0.15), as the operator did
            if use_w3d: mon += ['--w3d-alert', 0.15 if weak_adjusted else 0.10, '--w3d-consecutive', 5]
            m = lab(*mon)
            if ended(m) or not m.get('ok'): break
            al = m.get('alert') or ''
            if al.startswith('CNN'):
                o = decide(['fe', 'close'], [m['receipt']], f'strong 3D: {al}')
                sp += 20
                decide(['set-sec', sp, '--rate', 15], [m['receipt']], f'strong 3D intervention: SeC +20 -> {sp}')
            elif al.startswith('W3D') and weak_adjusted:
                o = decide(['fe', 'close'], [m['receipt']], f'weak 3D deteriorating after Se adjustment: {al}; escalate (close Fe)')
                break
            elif al.startswith('W3D'):
                weak_adjusted = True
                sp += 10
                decide(['set-sec', sp, '--rate', 15], [m['receipt']], f'weak 3D (CNN blind): {al}; SeC +10 -> {sp}')
                lab('wait', 30)
        else:
            # Fe closed: wait for SeC to reach setpoint, then judge recovery for ~2 min
            m = lab('monitor', '--interval', 6, '--duration', 600, '--channels', 'temp', '--sec-target', sp, '--tol', 1)
            if ended(m) or not m.get('ok'): break
            reached_receipt = m['receipt']
            m2 = lab('monitor', '--interval', 6, '--duration', 120, '--channels', 'cnn', '--cnn-2d-stable', 0.9, '--consecutive', 5)
            if ended(m2) or not m2.get('ok'): break
            last = (m2.get('frames', {}).get('cnn') or [{}])[-1]
            if not m2.get('alert') and last.get('p2D', 0) > 0.5:
                # clear recovery trend (2D dominant but not yet stable): extend the judgement once by 60 s
                m2 = lab('monitor', '--interval', 6, '--duration', 60, '--channels', 'cnn', '--cnn-2d-stable', 0.9, '--consecutive', 5)
                if ended(m2) or not m2.get('ok'): break
            if m2.get('alert'):
                decide(['fe', 'open'], [m2['receipt']], f"2D recovered at SeC {sp}: {m2['alert']}")
            else:
                sp += 20
                decide(['set-sec', sp, '--rate', 15], [reached_receipt, m2['receipt']], f'not recovered 2 min after reaching setpoint; SeC +20 -> {sp}')
    st = lab('status')
    if st['growth_stopped']:
        lab('sec', 'close', '--motivation', 'stop: close Se shutter')
        for dev, v in (('fe', 800), ('sec', 400), ('seb', 48.7)):
            lab(f'set-{dev}', v, '--motivation', 'cooldown to standby')
    st = lab('status')
    rep = {'decisions': decisions,
           'final': {'layers': st['layers_estimate'], 'stopped_at': next((d['replay_time'] for d in decisions if d['command'] == 'fe close' and 'stop' in d['rationale']), None),
                     'terminal': st.get('terminal')},
           'command_log': LOG}
    json.dump(rep, open(a.report, 'w'), indent=1)
    print(json.dumps({'terminal': st.get('terminal'), 'layers': st['layers_estimate'], 'queries': st['queries_used']}))

if __name__ == '__main__':
    sys.exit(main())
