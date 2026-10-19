"""Local (no-docker) harness: start replay server for a task, run a policy command, run the verifier.
python3 run_local.py <task> <out_dir> -- <policy command...>"""
import json, os, subprocess, sys, time, shutil, socket, urllib.request
B = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(B)
def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p
def prep_data(task, d):
    os.makedirs(d, exist_ok=True)
    shutil.copy(f'{ROOT}/derived/replay_dataset_1012.json', f'{d}/replay_dataset.json')
    shutil.copy(f'{ROOT}/data_private/decision_points.json', f'{d}/decision_points.json')
    shutil.copy(f'{B}/tasks_src/{task}/task.json', f'{d}/task.json')
    open(f'{d}/verifier_token', 'w').write('local-test-token\n')
def run(task, out, policy):
    os.makedirs(out, exist_ok=True); data = f'{out}/data'; prep_data(task, data)
    port = free_port(); env = dict(os.environ, REPLAY_VERIFIER_TOKEN='local-test-token', REPLAY_TASK_NAME=task, REPLAY_HOST='127.0.0.1', REPLAY_DATA_DIR=data, REPLAY_PORT=str(port), REPLAY_AUDIT_PATH=f'{out}/audit_live.json')
    srv = subprocess.Popen([sys.executable, '-I', f'{B}/common/replay_server.py'], env=env)
    try:
        for _ in range(50):
            try: urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{port}/health', timeout=1); break
            except Exception: time.sleep(0.1)
        shim = f'{out}/bin'; os.makedirs(shim, exist_ok=True)
        open(f'{shim}/fese-lab', 'w').write(f'#!/bin/sh\nexec {sys.executable} -I {B}/common/fese_lab_cli.py "$@"\n'); os.chmod(f'{shim}/fese-lab', 0o755)
        penv = dict(os.environ, FESE_REPLAY_URL=f'http://127.0.0.1:{port}', PATH=shim + ':' + os.environ['PATH'], REPORT=f'{out}/report.json')
        p = subprocess.run(policy, shell=True, env=penv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        open(f'{out}/policy.log', 'w').write(p.stdout)
        v = subprocess.run([sys.executable, '-I', f'{B}/common/verify.py', '--audit-url', f'http://127.0.0.1:{port}/audit',
                            '--token-file', f'{data}/verifier_token', '--report', f'{out}/report.json',
                            '--targets', f'{B}/tasks_src/{task}/targets.json', '--out', f'{out}/verifier'],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        return p.stdout[-400:], v.stdout.strip()[-600:]
    finally:
        srv.terminate(); srv.wait()
if __name__ == '__main__':
    i = sys.argv.index('--'); task, out = sys.argv[1], sys.argv[2]
    pl, vr = run(task, out, ' '.join(sys.argv[i+1:]))
    print('POLICY:', pl); print('VERIFY:', vr)
