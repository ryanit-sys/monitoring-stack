import base64, hmac, html, os, pathlib, secrets, signal, subprocess, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

config = pathlib.Path('/config/prometheus.yml')
backup = pathlib.Path('/config/prometheus.previous.yml')
password = os.environ['CONFIG_PASSWORD']
if len(password) < 16 or password.startswith('CHANGE_ME'):
    raise SystemExit('Set a strong PROMETHEUS_CONFIG_PASSWORD')
csrf = secrets.token_urlsafe(32)
lock = threading.Lock()
if not config.exists():
    config.write_bytes(pathlib.Path('/app/default.yml').read_bytes())

def validate(path):
    p = subprocess.run(['promtool','check','config',str(path)], capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise ValueError(p.stdout + p.stderr)

def start():
    return subprocess.Popen(['prometheus','--config.file='+str(config),'--storage.tsdb.path=/prometheus','--web.listen-address=0.0.0.0:9090'])

validate(config)
proc = start()

def ready():
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:9090/-/ready', timeout=1) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError('Prometheus not ready')

def restart():
    global proc
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    proc = start()
    ready()

def reload_config():
    proc.send_signal(signal.SIGHUP)
    for _ in range(30):
        time.sleep(1)
        with urllib.request.urlopen('http://127.0.0.1:9090/api/v1/query?query=prometheus_config_last_reload_successful', timeout=3) as r:
            import json
            data = json.load(r)['data']['result']
            if data and all(x['value'][1] == '1' for x in data):
                return
    raise RuntimeError('Reload not confirmed')

def apply(value):
    candidate = config.with_suffix('.tmp')
    candidate.write_text(value)
    try:
        validate(candidate)
        old = config.read_bytes()
        backup.write_bytes(old)
        candidate.replace(config)
        try:
            restart()
        except Exception:
            candidate.write_bytes(old)
            candidate.replace(config)
            restart()
            raise
    finally:
        candidate.unlink(missing_ok=True)

class Handler(BaseHTTPRequestHandler):
    def auth(self):
        expected = 'Basic '+base64.b64encode(('admin:'+password).encode()).decode()
        if hmac.compare_digest(self.headers.get('Authorization',''), expected):
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate','Basic realm="Prometheus config"')
        self.end_headers()
        return False
    def page(self, message='', status=200):
        body = ('<!doctype html><meta charset=utf-8><title>Prometheus configuration</title>'
                '<style>body{max-width:1000px;margin:40px auto;font:16px system-ui}textarea{width:100%;height:60vh;font:14px monospace}button{padding:10px;margin:8px}</style>'
                '<h1>Prometheus configuration</h1><pre>'+html.escape(message)+'</pre>'
                '<form method=post><input type=hidden name=csrf value="'+csrf+'"><textarea name=config>'+html.escape(config.read_text())+'</textarea>'
                '<button name=action value=save>Validate, save and restart</button><button name=action value=restart>Restart</button><button name=action value=rollback>Rollback</button></form>').encode()
        self.send_response(status)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.auth():
            with lock:
                self.page()
    def do_POST(self):
        if not self.auth():
            return
        try:
            n = int(self.headers.get('Content-Length','0'))
            if not 0 < n <= 1048576:
                raise ValueError('Invalid request size')
            fields = urllib.parse.parse_qs(self.rfile.read(n).decode())
            if not hmac.compare_digest(fields.get('csrf',[''])[0],csrf):
                self.send_error(403)
                return
            with lock:
                action = fields.get('action',[''])[0]
                if action == 'save':
                    apply(fields['config'][0])
                elif action == 'restart':
                    restart()
                elif action == 'rollback':
                    apply(backup.read_text())
                else:
                    raise ValueError('Unknown action')
                self.page('Success')
        except Exception as e:
            self.page(str(e),400)

def shutdown(*_):
    proc.terminate()
    proc.wait(timeout=30)
    raise SystemExit(0)

signal.signal(signal.SIGTERM,shutdown)
signal.signal(signal.SIGINT,shutdown)
server = ThreadingHTTPServer(('0.0.0.0',9091),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
while True:
    time.sleep(1)
    with lock:
        if proc.poll() is not None:
            raise SystemExit(proc.returncode or 1)
