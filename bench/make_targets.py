"""Compute private diagnose targets from the canonical dataset (deterministic)."""
import json, sys
D = json.load(open(sys.argv[1])); F = D['frames']
def sec(s): h,m,x = s.split(':'); return int(h)*3600+int(m)*60+float(x)
def hms(t): t=int(round(t)); return f"{t//3600:02d}:{t%3600//60:02d}:{t%60:02d}"
onset = next(f for f in F if 'cnn' in f and f['t'] >= sec('16:22:52') and f['cnn']['p3D'] > 0.5)
run = []; w_on = None
for f in F:
    if 'w3d' not in f or f['t'] < sec('16:36:11'): continue
    if (f['w3d'].get('W3D') or 0) > 0.10: run.append(f)
    else: run = []
    if len(run) >= 5: w_on = run[0]; break
seg = [f for f in F if 'w3d' in f and sec('16:36:11') <= f['t'] <= sec('16:57:49') and f['w3d'].get('W3D') is not None]
peak = max(f['w3d']['W3D'] for f in seg)
plateau = [f for f in F if 'cnn' in f and w_on['t'] <= f['t'] <= sec('16:41:51')]
cmax = max(f['cnn']['p3D'] for f in plateau)
fe = (sec('16:26:16')-sec('16:22:52') + sec('16:57:49')-sec('16:36:11'))/60
Q = {
 'q1_strong3d_onset_time': dict(kind='time', value=hms(onset['t']), tol=12, evidence='cnn_p3d_gt_0.5_near',
   text='Capture time of the first analysed RHEED frame after the Fe shutter opened (16:22:52) with CNN p3D > 0.5.'),
 'q2_recovery_sec_setpoint': dict(kind='num', value=560, tol=0.5, evidence='action_set_sec_560',
   text='SeC setpoint (degC) at which 2D growth recovered after the strong-3D event.'),
 'q3_weak3d_onset_time': dict(kind='time', value=hms(w_on['t']), tol=18, evidence='w3d_gt_0.10_near',
   text='After the Fe shutter reopened (16:36:11): capture time of the first frame of the first run of >=5 consecutive analysed frames with W3D > 0.10.'),
 'q4_peak_w3d_second_period': dict(kind='num', value=peak, tol=0.0005, evidence='w3d_value',
   text='Maximum W3D among analysed frames captured between 16:36:11 and 16:57:49.'),
 'q5_max_cnn_p3d_weak3d_plateau': dict(kind='num', value=cmax, tol=0.0005, evidence='cnn_p3d_value',
   text='Maximum CNN p3D among analysed frames captured from the weak-3D onset (q3) to the SeC change at 16:41:51.'),
 'q6_sec_setpoint_clearing_weak3d': dict(kind='num', value=570, tol=0.5, evidence='action_set_sec_570',
   text='SeC setpoint (degC) in effect when W3D fell back below 0.08.'),
 'q7_total_fe_open_minutes': dict(kind='num', value=round(fe, 2), tol=0.1, evidence='fe_actions',
   text='Total Fe-shutter-open time (minutes) of the run.'),
 'q8_next_probe_sec': dict(kind='num', value=565, tol=0.5, evidence=None,
   text='Lowest untested SeC setpoint (5 degC granularity) between the last insufficient and the first sufficient setpoint for clearing weak 3D.'),
}
json.dump({'questions': Q}, open(sys.argv[2], 'w'), indent=1)
for k, v in Q.items(): print(k, v['value'])
print('w3d frames in second period', len(seg), 'plateau cnn frames', len(plateau))
