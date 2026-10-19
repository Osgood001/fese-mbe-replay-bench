#!/usr/bin/env python3
"""fese-lab — replay edition of the lab CLI (Osgood001/fese-rheed-lab command style).
All commands talk to the environment-owned replay service; output is JSON."""
import argparse, json, os, sys, urllib.request

URL = os.environ.get('FESE_REPLAY_URL', 'http://replay:8080')

def call(cmd, args=None):
    req = urllib.request.Request(URL + '/api', data=json.dumps({'cmd': cmd, 'args': args or {}}).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=120) as r:
        return json.loads(r.read())

def main(argv=None):
    p = argparse.ArgumentParser(prog='fese-lab', description='FeSe MBE replay lab CLI (logged real run, 2026-10-12)')
    p.add_argument('--hardware', action='store_true', help='accepted for compatibility; all commands act on the replay')
    s = p.add_subparsers(dest='cmd', required=True)
    s.add_parser('status', help='clock, shutters, setpoints, Fe-open minutes, budget (free)')
    w = s.add_parser('wait', help='advance the replay clock'); w.add_argument('seconds', type=float)
    g = s.add_parser('get-pv', help='latest measured temperature'); g.add_argument('device', choices=['fe', 'sec', 'seb'])
    r = s.add_parser('rheed', help='latest analysed RHEED frames'); r.add_argument('channel', choices=['cnn', 'w3d'])
    r.add_argument('-n', type=int, default=5)
    m = s.add_parser('monitor', help='poll channels every --interval s for --duration s; stop early on an alert')
    m.add_argument('--interval', type=float, default=12); m.add_argument('--duration', type=float, default=120)
    m.add_argument('--channels', default='cnn', help='comma list of cnn,w3d,temp (each poll of each channel costs 1 query)')
    m.add_argument('--cnn-3d-alert', type=float); m.add_argument('--cnn-2d-stable', type=float)
    m.add_argument('--w3d-alert', type=float); m.add_argument('--consecutive', type=int, default=2, help='consecutive frames for CNN alerts')
    m.add_argument('--w3d-consecutive', type=int, default=5, help='consecutive frames for the W3D alert')
    m.add_argument('--sec-target', type=float); m.add_argument('--tol', type=float, default=1.0)
    for dev in ('fe', 'sec'):
        sh = s.add_parser(dev, help=f'{dev} shutter'); sh.add_argument('op', choices=['open', 'close'])
        sh.add_argument('--motivation', default='')
    for dev in ('fe', 'sec', 'seb'):
        st = s.add_parser(f'set-{dev}', help=f'set {dev} setpoint (degC)'); st.add_argument('value', type=float)
        st.add_argument('--rate', type=float); st.add_argument('--motivation', default='')
    a = s.add_parser('archive', help='diagnose mode: query archived records (max 20 per query)')
    a.add_argument('channel', choices=['cnn', 'w3d', 'temps', 'actions'])
    a.add_argument('--from', dest='frm', required=True); a.add_argument('--to', required=True)
    o = p.parse_args(argv)
    c = o.cmd
    if c == 'status': out = call('status')
    elif c == 'wait': out = call('wait', {'seconds': o.seconds})
    elif c == 'get-pv': out = call('get-pv', {'device': o.device})
    elif c == 'rheed': out = call('rheed', {'channel': o.channel, 'n': o.n})
    elif c == 'monitor':
        out = call('monitor', {'interval': o.interval, 'duration': o.duration, 'channels': o.channels,
                               'cnn_3d_alert': o.cnn_3d_alert, 'cnn_2d_stable': o.cnn_2d_stable, 'w3d_alert': o.w3d_alert,
                               'consecutive': o.consecutive, 'w3d_consecutive': o.w3d_consecutive, 'sec_target': o.sec_target, 'tol': o.tol})
    elif c in ('fe', 'sec'): out = call('shutter', {'device': c, 'op': o.op, 'motivation': o.motivation})
    elif c.startswith('set-'): out = call('set', {'device': c[4:], 'value': o.value, 'rate': o.rate, 'motivation': o.motivation})
    elif c == 'archive': out = call('archive', {'channel': o.channel, 'from': o.frm, 'to': o.to})
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out.get('ok') else 1

if __name__ == '__main__':
    sys.exit(main())
