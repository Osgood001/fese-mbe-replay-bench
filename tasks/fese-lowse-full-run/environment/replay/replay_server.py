"""Environment-owned replay service (runs in the `replay` sidecar container).
POST /api {"cmd":..., "args":{...}} -> JSON ; GET /audit with header X-Verifier-Token -> full export."""
import json, os, sys, hmac
from http.server import HTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mbe_replay_env import ReplayEnv

D = os.environ.get('REPLAY_DATA_DIR', '/srv/replay/data')
ENV = ReplayEnv(json.load(open(f'{D}/replay_dataset.json')), json.load(open(f'{D}/decision_points.json')),
                json.load(open(f'{D}/task.json')))
TOKEN = os.environ.get('REPLAY_VERIFIER_TOKEN', '').strip()
if not TOKEN: raise SystemExit('REPLAY_VERIFIER_TOKEN missing')
# guard against stale build-cache content: the compose file pins the expected task name
if os.environ.get('REPLAY_TASK_NAME') and ENV.task['name'] != os.environ['REPLAY_TASK_NAME']:
    raise SystemExit(f"task.json name {ENV.task['name']} != REPLAY_TASK_NAME {os.environ['REPLAY_TASK_NAME']}")
AUDIT = os.environ.get('REPLAY_AUDIT_PATH', '/var/lib/replay/audit.json')

def persist():
    os.makedirs(os.path.dirname(AUDIT), exist_ok=True)
    tmp = AUDIT + '.tmp'
    with open(tmp, 'w') as f: json.dump(ENV.export(), f)
    os.replace(tmp, AUDIT)

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == '/health': return self._send(200, {'ok': True})
        if self.path == '/audit':
            if hmac.compare_digest(self.headers.get('X-Verifier-Token', ''), TOKEN):
                return self._send(200, ENV.export())
            return self._send(403, {'ok': False, 'error': 'forbidden'})
        self._send(404, {'ok': False, 'error': 'not found'})
    def do_POST(self):
        if self.path != '/api': return self._send(404, {'ok': False, 'error': 'not found'})
        try:
            n = min(int(self.headers.get('Content-Length', 0)), 65536)
            req = json.loads(self.rfile.read(n) or b'{}')
            resp = ENV.handle(str(req.get('cmd', '')), req.get('args') or {})
        except (ValueError, json.JSONDecodeError) as e:
            resp = {'ok': False, 'error': f'bad request: {e}'}
        persist(); self._send(200, resp)
    def log_message(self, *a): pass

if __name__ == '__main__':
    persist()
    HTTPServer((os.environ.get('REPLAY_HOST', '0.0.0.0'), int(os.environ.get('REPLAY_PORT', '8080'))), H).serve_forever()
