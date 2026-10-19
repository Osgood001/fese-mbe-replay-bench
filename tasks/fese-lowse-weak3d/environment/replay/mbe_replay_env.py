"""Logged-data replay of the real FeSe low-Se MBE run of 2026-10-12 (low_Se_test 1012).

Trust model: this module runs only inside the environment-owned `replay` service.
The agent reaches it through the fese-lab CLI (HTTP), never reads the data files,
and cannot write the audit log except by issuing commands.

Replay semantics (see README / report section "Replay fidelity"):
* Observations are measured records only (CNN / W3D per analysed RHEED frame,
  temperature readings).  No interpolation, no synthetic values.
* The replay is only defined along the logged control path.  At each logged
  decision point Dk an action matching the logged one, issued after the SOP
  trigger became observable (window_open) and before the logged action time
  (boundary), is accepted and applied at the logged time (clock snapped forward,
  delta recorded).  Anything else leaves the measured support:
    - premature / unlogged action  -> terminal  out_of_support:*
    - SOP-valid but unlogged value  -> terminal  unevaluable:*
    - clock advanced past a boundary without the action -> terminal out_of_support:missed_*
* Closing Fe in the second growth period ends growth (terminal "stopped"); the
  log holds no Fe-closed data after 16:36:11, so growth cannot resume.
"""
import json, hashlib, time

def hms(t):
    t = int(round(t)); return f"{t//3600:02d}:{t%3600//60:02d}:{t%60:02d}"

def parse_hms(s):
    p = [float(x) for x in str(s).split(':')]
    while len(p) < 3: p.append(0.0)
    return p[0]*3600 + p[1]*60 + p[2]

PARTNER_TOL_S = 30.0          # remaining actions of a decision must follow within this replay time
MAX_WAIT_S = 900.0
MAX_N = 10

class ReplayEnv:
    def __init__(self, dataset, dpcfg, task):
        self.task = task                      # dict: name, mode(control|diagnose), start, decisions, max_queries
        self.frames = sorted(dataset['frames'], key=lambda f: f['t'])
        self.temps = sorted(dataset['temps'], key=lambda r: r['t'])
        self.logged_actions = dataset['actions']
        self.cfg = dpcfg
        self.dps = {d['id']: dict(d) for d in dpcfg['decision_points'] if d['id'] in task.get('decisions', [])}
        for d in self.dps.values():
            d.update(status='pending', done=[], agent_times=[], first_t=None)
        self.t = parse_hms(task['start'])
        self.mode = task['mode']
        self.max_queries = int(task['max_queries'])
        self.queries = 0; self.actions = 0
        self.events = []; self.receipts = {}; self.chain = '0'*64
        self.terminal = None; self.terminal_t = None
        self.stop = None                      # dict when growth stopped
        st = task.get('initial_state', {})
        self.shutter = dict(st.get('shutter', {'fe': 'open', 'sec': 'open'}))
        self.sp = dict(st.get('sp', {'fe': 1100.0, 'sec': 520.0, 'seb': 90.0}))
        self.fe_intervals = [list(x) for x in st.get('fe_intervals', [])]   # closed intervals [a,b]; open one has b=None
        self.cooldown = {}
        self.violations = []
        self.data_end = parse_hms(task.get('data_end', '17:19:06'))

    # ---------- bookkeeping ----------
    def fe_minutes(self, at=None):
        at = self.t if at is None else at
        tot = 0.0
        for a, b in self.fe_intervals:
            tot += max(0.0, (at if b is None else min(b, at)) - a)
        return tot/60.0

    def layers(self, at=None):
        return round(self.fe_minutes(at)*self.cfg['growth_rate_layers_per_min'], 4)

    def _log(self, kind, req, resp):
        ev = {'seq': len(self.events), 'kind': kind, 'replay_t': round(self.t, 3), 'replay_hms': hms(self.t),
              'wall': round(time.time(), 3), 'request': req, 'response': resp}
        blob = json.dumps(ev, sort_keys=True, ensure_ascii=False)
        self.chain = hashlib.sha256((self.chain + blob).encode()).hexdigest()
        ev['chain'] = self.chain
        self.events.append(ev)
        return ev

    def _receipt(self, payload):
        rid = f"R{len(self.receipts)+1:04d}"
        self.receipts[rid] = payload
        return rid

    def _end(self, reason, at=None):
        if self.terminal is None:
            self.terminal = reason; self.terminal_t = self.t if at is None else at

    # ---------- observation helpers (measured records only) ----------
    def _frames(self, chan, upto, n):
        out = [f for f in self.frames if chan in f and f['t'] <= upto + 1e-6]
        return out[-n:] if n else out

    def _frame_view(self, f, chan):
        v = {'capture_time': f['hms'][:8], 'capture_t': f['t'], 'frame': f"20261012{f['hms'][:8].replace(':','')}{f['hms'][9:12]}.jpg"}
        if chan == 'cnn':
            c = f['cnn']; v.update(label=c['label'], p2D=c['p2D'], p3D=c['p3D'], pSTO=c['pSTO'])
        else:
            w = f['w3d']; v.update({k: w.get(k) for k in ('W3D', 'L', 'R', 'spec', 's1L', 's1R')})
        return v

    def _temp(self, dev, upto):
        recs = [r for r in self.temps if r['device'] == dev and r['t'] <= upto + 1e-6]
        return recs[-1] if recs else None

    def _post_stop_unsupported(self):
        return self.stop is not None and abs(self.stop['t'] - parse_hms('16:57:49')) > 1.0

    # ---------- clock ----------
    def _advance(self, dt):
        target = self.t + dt
        if self.stop is not None:
            self.t = min(target, self.data_end); return
        # pending decisions whose boundary falls inside (t, target]
        for d in sorted(self.dps.values(), key=lambda d: d['boundary']):
            if d['status'] == 'pending' and self.t < d['boundary'] <= target and self.terminal is None:
                if d['id'] == 'D5':
                    self.t = d['boundary']; self._end('out_of_support:overgrowth_past_logged_stop'); return
                self.t = d['boundary']; self._end(f"out_of_support:missed_{d['id']}"); return
            if d['status'] == 'partial' and target > d['first_t'] + PARTNER_TOL_S and self.terminal is None:
                self.t = d['first_t'] + PARTNER_TOL_S; self._end(f"out_of_support:incomplete_{d['id']}"); return
        if target > self.data_end:
            self.t = self.data_end; self._end('data_end'); return
        self.t = target

    # ---------- command dispatch ----------
    def handle(self, cmd, args):
        try:
            resp = self._dispatch(cmd, args or {})
        except (ValueError, KeyError, TypeError) as e:
            resp = {'ok': False, 'error': f'bad_request: {e}'}
        resp.setdefault('replay_time', hms(self.t))
        if self.terminal: resp.setdefault('episode', {'terminal': self.terminal, 'at': hms(self.terminal_t)})
        self._log(cmd, args, resp)
        return resp

    def _need_query(self, k=1):
        if self.queries + k > self.max_queries:
            raise BudgetError()
        self.queries += k

    def _dispatch(self, cmd, a):
        if cmd == 'status':
            rid = self._receipt({'type': 'status', 't': self.t, 'fe_minutes': self.fe_minutes(), 'layers': self.layers()})
            return {'ok': True, 'receipt': rid, 'mode': self.mode, 'shutters': dict(self.shutter), 'setpoints': dict(self.sp),
                    'fe_open_minutes': round(self.fe_minutes(), 3), 'layers_estimate': self.layers(),
                    'queries_used': self.queries, 'queries_max': self.max_queries,
                    'growth_stopped': self.stop is not None, 'terminal': self.terminal}
        if self.mode == 'diagnose':
            return self._diagnose(cmd, a)
        if cmd in ('get-pv', 'rheed', 'monitor', 'wait') and self.terminal and not (self.terminal == 'stopped'):
            return {'ok': False, 'error': f'episode ended: {self.terminal}'}
        try:
            if cmd == 'wait':
                dt = float(a['seconds'])
                if not (0 < dt <= MAX_WAIT_S): raise ValueError('seconds must be in (0, 900]')
                self._advance(dt)
                return {'ok': True}
            if cmd == 'get-pv':
                return self._get_pv(a['device'])
            if cmd == 'rheed':
                return self._rheed(a['channel'], int(a.get('n', 5)))
            if cmd == 'monitor':
                return self._monitor(a)
        except BudgetError:
            if self.stop is None: self._end('budget_exhausted')
            return {'ok': False, 'error': 'query budget exhausted'}
        if cmd in ('shutter', 'set'):
            return self._action(cmd, a)
        return {'ok': False, 'error': f'unknown command {cmd}'}

    def _get_pv(self, dev):
        if dev not in ('fe', 'sec', 'seb'): raise ValueError('device must be fe|sec|seb')
        self._need_query()
        if self.stop and self.t > self.stop['t'] and self._post_stop_unsupported():
            return {'ok': False, 'error': 'no measured temperatures for this (early-stop) branch'}
        r = self._temp(dev, self.t)
        if r is None: return {'ok': False, 'error': 'no measured reading yet'}
        rid = self._receipt({'type': 'temp', 'records': [r]})
        return {'ok': True, 'receipt': rid, 'device': dev, 'pv': r['pv'], 'sp': self.sp[dev],
                'measured_at': r['hms'], 'age_s': round(self.t - r['t'], 1), 'source': 'measured (logged)'}

    def _rheed(self, chan, n):
        if chan not in ('cnn', 'w3d'): raise ValueError('channel must be cnn|w3d')
        n = max(1, min(MAX_N, n)); self._need_query()
        if self.stop and self.t > self.stop['t'] + 90:
            return {'ok': False, 'error': 'RHEED analysis stopped after growth stop'}
        fr = self._frames(chan, self.t, n)
        views = [self._frame_view(f, chan) for f in fr]
        rid = self._receipt({'type': chan, 'frames': views})
        latest_age = round(self.t - fr[-1]['t'], 1) if fr else None
        return {'ok': True, 'receipt': rid, 'channel': chan, 'frames': views, 'latest_age_s': latest_age,
                'note': 'only frames that were analysed during the real run are available; gaps are real'}

    def _monitor(self, a):
        interval = float(a.get('interval', 12)); duration = float(a.get('duration', 120))
        if not (3 <= interval <= 120): raise ValueError('interval must be in [3,120]')
        if not (0 < duration <= MAX_WAIT_S): raise ValueError('duration must be in (0,900]')
        chans = [c for c in str(a.get('channels', 'cnn')).split(',') if c]
        for c in chans:
            if c not in ('cnn', 'w3d', 'temp'): raise ValueError('channels subset of cnn,w3d,temp')
        al = {k: a.get(k) for k in ('cnn_3d_alert', 'cnn_2d_stable', 'w3d_alert', 'consecutive', 'w3d_consecutive', 'sec_target', 'tol')}
        need = int(al['consecutive'] or 2); need_w = int(al['w3d_consecutive'] or 5)
        t0 = self.t; seen = {c: set() for c in chans}; series = {c: [] for c in chans}
        cnt = {'cnn3d': 0, 'cnn2d': 0, 'w3d': 0}; alert = None; temps = []
        while self.t - t0 < duration - 1e-6 and self.terminal is None:
            self._advance(min(interval, duration - (self.t - t0)))
            if self.terminal: break
            for c in chans:
                self._need_query()
                if c == 'temp':
                    r = self._temp('sec', self.t)
                    if r and (not temps or temps[-1]['measured_at'] != r['hms']):
                        temps.append({'measured_at': r['hms'], 'sec_pv': r['pv']})
                        if al['sec_target'] is not None and abs(r['pv'] - float(al['sec_target'])) <= float(al['tol'] or 1):
                            alert = alert or f"SeC PV {r['pv']} within tol of {al['sec_target']} (measured {r['hms']})"
                    continue
                for f in self._frames(c, self.t, 0):
                    if f['t'] < t0 or f['t'] in seen[c]: continue
                    seen[c].add(f['t']); v = self._frame_view(f, c); series[c].append(v)
                    if c == 'cnn':
                        if al['cnn_3d_alert'] is not None:
                            cnt['cnn3d'] = cnt['cnn3d'] + 1 if v['p3D'] > float(al['cnn_3d_alert']) else 0
                            if cnt['cnn3d'] >= need: alert = alert or f"CNN p3D>{al['cnn_3d_alert']} x{need} at {v['capture_time']}"
                        if al['cnn_2d_stable'] is not None:
                            cnt['cnn2d'] = cnt['cnn2d'] + 1 if (v['p2D'] > float(al['cnn_2d_stable']) and v['p3D'] < 0.1) else 0
                            if cnt['cnn2d'] >= need: alert = alert or f"CNN p2D>{al['cnn_2d_stable']} (p3D<0.1) x{need} at {v['capture_time']}"
                    else:
                        if al['w3d_alert'] is not None and v['W3D'] is not None:
                            cnt['w3d'] = cnt['w3d'] + 1 if v['W3D'] > float(al['w3d_alert']) else 0
                            if cnt['w3d'] >= need_w: alert = alert or f"W3D>{al['w3d_alert']} x{need_w} at {v['capture_time']}"
            if alert: break
        payload = {'type': 'monitor', 'frames': {c: series[c] for c in chans if c != 'temp'}, 'temps': temps}
        rid = self._receipt(payload)
        return {'ok': True, 'receipt': rid, 'started': hms(t0), 'alert': alert, **payload,
                'stopped_reason': 'alert' if alert else ('terminal' if self.terminal else 'duration')}

    # ---------- actions ----------
    def _action(self, cmd, a):
        if self.stop is None and self.terminal:
            return {'ok': False, 'error': f'episode ended: {self.terminal}'}
        self.actions += 1
        if cmd == 'shutter':
            dev, op = a['device'], a['op']
            if dev not in ('fe', 'sec') or op not in ('open', 'close'): raise ValueError('shutter fe|sec open|close')
            key = (f'{dev}-{op}', None)
        else:
            dev = a['device']; val = float(a['value'])
            if dev not in ('fe', 'sec', 'seb'): raise ValueError('device fe|sec|seb')
            key = (f'set-{dev}', val)
        motivation = str(a.get('motivation', ''))[:500]
        # post-stop: cooldown phase
        if self.stop is not None:
            return self._cooldown(key, motivation)
        # idempotent no-op
        if key[0].endswith(('open', 'close')):
            cur = self.shutter[dev]
            if (op == 'open') == (cur == 'open'):
                return {'ok': True, 'noop': True, 'note': f'{dev} shutter already {cur}'}
        elif self.sp.get(dev) == key[1]:
            return {'ok': True, 'noop': True, 'note': 'setpoint unchanged'}
        # decisions
        for d in sorted(self.dps.values(), key=lambda d: d['boundary']):
            if d['status'] not in ('pending', 'partial') or d['id'] == 'D5': continue
            req = [tuple(x) for x in d['required']]
            alts = [tuple(x) for x in d.get('sop_valid_alternatives', [])]
            if key in req and key not in [tuple(x) for x in d['done']]:
                if d['status'] == 'pending' and self.t < d['window_open'] - 1e-6:
                    self._end(f"out_of_support:premature_{d['id']}")
                    return {'ok': False, 'error': f'action precedes the measured trigger for this branch ({d["id"]}); replay has no data for it'}
                return self._accept(d, key, motivation)
            if key in alts and d['status'] == 'pending' and self.t >= d['window_open'] - 1e-6:
                self._end(f"unevaluable:sop_valid_unlogged_{d['id']}")
                return {'ok': False, 'error': 'SOP-consistent action, but this setpoint was never run; outcome unevaluable'}
        # Fe close in the second growth period = end of growth (D5)
        if key == ('fe-close', None) and 'D5' in self.dps and self.fe_intervals and self.fe_intervals[-1][0] >= parse_hms('16:36:00'):
            return self._stop(motivation)
        self._end(f"out_of_support:unlogged_{key[0]}{'' if key[1] is None else '_'+str(key[1])}")
        return {'ok': False, 'error': 'this action leaves the logged path; no measured data exist for this branch'}

    def _apply(self, key, at):
        name, val = key
        if name.startswith('set-'): self.sp[name[4:]] = val
        else:
            dev, op = name.split('-')
            self.shutter[dev] = 'open' if op == 'open' else 'closed'
            if dev == 'fe':
                if op == 'open': self.fe_intervals.append([at, None])
                elif self.fe_intervals and self.fe_intervals[-1][1] is None: self.fe_intervals[-1][1] = at

    def _accept(self, d, key, motivation):
        agent_t = self.t
        if d['status'] == 'pending':
            d['first_t'] = d['snap_to']; d['status'] = 'partial'
            self.t = max(self.t, d['snap_to'])
        self._apply(key, d['snap_to'])
        d['done'].append(list(key)); d['agent_times'].append(agent_t)
        if len(d['done']) == len(d['required']): d['status'] = 'done'
        note = f"applied at logged action time {hms(d['snap_to'])} (agent issued at {hms(agent_t)}, delta {d['snap_to']-agent_t:+.0f} s)"
        return {'ok': True, 'decision_point_matched': True, 'replay_note': note,
                'setpoints': dict(self.sp), 'shutters': dict(self.shutter), 'motivation_recorded': bool(motivation)}

    def _stop(self, motivation):
        self._apply(('fe-close', None), self.t)
        last_w = [f['w3d']['W3D'] for f in self._frames('w3d', self.t, 5) if f['w3d'].get('W3D') is not None]
        last_c = self._frames('cnn', self.t, 1)
        self.stop = {'t': self.t, 'hms': hms(self.t), 'fe_minutes': round(self.fe_minutes(), 3), 'layers': self.layers(),
                     'w3d_last5_mean': round(sum(last_w)/len(last_w), 4) if last_w else None,
                     'cnn_last': last_c[-1]['cnn'] if last_c else None, 'sec_closed_at': None}
        self.dps['D5'].update(status='done', agent_times=[self.t], done=[['fe-close', None]])
        self._end('stopped')
        return {'ok': True, 'growth_stopped': True, 'fe_open_minutes': self.stop['fe_minutes'], 'layers': self.stop['layers'],
                'note': 'growth ended (terminal). Close the Se shutter and return sources to standby.'}

    def _cooldown(self, key, motivation):
        name, val = key
        if name == 'sec-close':
            self.shutter['sec'] = 'closed'
            if self.stop['sec_closed_at'] is None: self.stop['sec_closed_at'] = self.t
            return {'ok': True, 'shutters': dict(self.shutter)}
        if name.startswith('set-'):
            dev = name[4:]; self.sp[dev] = val
            ok = abs(val - self.cfg['standby'][dev]) < 0.05
            self.cooldown[dev] = {'value': val, 't': self.t, 'standby_match': ok}
            if not ok: self.violations.append(f'cooldown setpoint {dev}={val} differs from standby {self.cfg["standby"][dev]}')
            return {'ok': True, 'setpoints': dict(self.sp)}
        if name.endswith('open'):
            self.violations.append(f'{name} after growth stop')
            return {'ok': False, 'error': 'refusing to reopen a shutter after growth stop'}
        return {'ok': True, 'noop': True}

    # ---------- diagnose mode (archived run, query budget) ----------
    def _diagnose(self, cmd, a):
        if cmd != 'archive': return {'ok': False, 'error': 'diagnose mode: use `fese-lab archive ...`'}
        chan = a['channel']; t0 = parse_hms(a['from']); t1 = parse_hms(a['to'])
        if chan not in ('cnn', 'w3d', 'temps', 'actions'): raise ValueError('channel cnn|w3d|temps|actions')
        if t1 < t0: raise ValueError('to < from')
        try: self._need_query()
        except BudgetError: return {'ok': False, 'error': 'query budget exhausted'}
        lim = 20
        if chan in ('cnn', 'w3d'):
            recs = [self._frame_view(f, chan) for f in self.frames if chan in f and t0 <= f['t'] <= t1]
        elif chan == 'temps':
            recs = [{'measured_at': r['hms'], 'device': r['device'], 'pv': r['pv'], 'sp': r['sp']} for r in self.temps if t0 <= r['t'] <= t1]
        else:
            recs = [{'time': x['hms'], 'cmd': x['cmd'], 'value': x['value']} for x in self.logged_actions if t0 <= x['t'] <= t1]
        out = recs[:lim]
        rid = self._receipt({'type': 'archive_' + chan, 'records': out})
        return {'ok': True, 'receipt': rid, 'channel': chan, 'records': out, 'n_in_range': len(recs), 'truncated': len(recs) > lim,
                'queries_used': self.queries, 'queries_max': self.max_queries}

    # ---------- export ----------
    def export(self):
        return {'task': self.task['name'], 'mode': self.mode, 'terminal': self.terminal,
                'terminal_t': self.terminal_t, 'terminal_hms': hms(self.terminal_t) if self.terminal_t else None,
                'replay_t': self.t, 'queries_used': self.queries, 'queries_max': self.max_queries, 'actions': self.actions,
                'decisions': {k: {kk: v[kk] for kk in ('id', 'status', 'done', 'agent_times', 'window_open', 'boundary', 'snap_to', 'required')}
                              for k, v in self.dps.items()},
                'stop': self.stop, 'cooldown': self.cooldown, 'shutters': dict(self.shutter), 'setpoints': dict(self.sp),
                'fe_intervals': self.fe_intervals, 'violations': self.violations, 'receipts': self.receipts,
                'events': self.events, 'chain_head': self.chain, 'standby': self.cfg['standby'],
                'target_layers': self.cfg['target_layers']}

class BudgetError(Exception):
    pass
