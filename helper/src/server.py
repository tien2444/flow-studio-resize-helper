"""Loopback-only processor, usable before the desktop app is packaged."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
import uuid
from engine import Engine, EXTENSIONS, SIZES


def bundled_file(name):
    """Resolve files copied beside the source or into a PyInstaller bundle."""
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=43127)
    parser.add_argument('--data-dir')
    parser.add_argument('--targets')
    args = parser.parse_args()
    if args.data_dir:
        root = Path(args.data_dir)
    elif sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'FlowStudioWebHelper' / 'data'
    else:
        root = Path.home() / 'Movies' / 'FlowStudio'
    import imageio_ffmpeg
    engine = Engine(root, imageio_ffmpeg.get_ffmpeg_exe())
    if not engine.targets:
        targets_file = Path(args.targets) if args.targets else bundled_file('default_targets.json')
        if targets_file.is_file():
            engine.configure(json.loads(targets_file.read_text(encoding='utf8')))
    token = secrets.token_urlsafe(40)
    allowed = {
        'http://localhost:3002',
        'http://127.0.0.1:3002',
        'https://flow-studio-web-one.vercel.app',
        'https://flow-studio-vip.vercel.app',
    }
    allowed.update(filter(None, os.environ.get('FLOW_PROCESSOR_ORIGINS', '').split(',')))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def headers_ok(self, auth=True):
            if self.headers.get('Host') not in (f'127.0.0.1:{args.port}', f'localhost:{args.port}'):
                return False
            if self.headers.get('Origin') not in allowed:
                return False
            return not auth or secrets.compare_digest(self.headers.get('X-Flow-Token', ''), token)

        def reply(self, data, status=200):
            raw = json.dumps(data, ensure_ascii=False).encode('utf8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            origin = self.headers.get('Origin')
            if origin in allowed:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self):
            if not self.headers_ok(False):
                return self.reply({'error':'Origin not allowed.'},403)
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Flow-Token, X-File-Name')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.end_headers()

        def do_GET(self):
            route = urlparse(self.path).path
            if not self.headers_ok(route != '/session'):
                return self.reply({'error':'Local processor access denied.'},403)
            try:
                if route == '/session':
                    return self.reply({'token':token,'platform':sys.platform,'outputFolder':str(engine.output_root),
                                       'targets':engine.target_view(),'sizes':SIZES,'version':12})
                if route == '/jobs':
                    return self.reply({'jobs':[engine.view(k) for k in list(engine.jobs)[-30:]][::-1]})
                if route.startswith('/jobs/'):
                    return self.reply(engine.view(route.split('/')[2]))
                if route.startswith('/files/'):
                    _, _, jobid, itemid, kind = route.split('/')
                    job = engine.view(jobid)
                    item = next(i for i in job['items'] if i['id'] == itemid)
                    path = Path(item['thumbnail' if kind == 'thumbnail' else 'path'])
                    if kind not in ('output', 'thumbnail') or not path.resolve().is_relative_to(Path(job['outputFolder']).resolve()):
                        raise ValueError('Invalid output path.')
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Type', 'image/jpeg' if path.suffix=='.jpg' else 'video/mp4' if path.suffix=='.mp4' else 'application/octet-stream')
                    self.send_header('Content-Length', str(path.stat().st_size))
                    self.end_headers()
                    with path.open('rb') as file:
                        while block := file.read(1024*1024):
                            self.wfile.write(block)
                    return
                self.reply({'error':'Not found.'},404)
            except (KeyError, StopIteration, FileNotFoundError):
                self.reply({'error':'Output or job not found.'},404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                self.reply({'error':str(error)},400)

        def do_POST(self):
            if not self.headers_ok():
                return self.reply({'error':'Local processor access denied.'},403)
            try:
                route = urlparse(self.path).path
                length = int(self.headers.get('Content-Length','0'))
                if route == '/inputs':
                    if not 0 < length <= 512*1024*1024:
                        return self.reply({'error':'Choose a file up to 512 MB.'},413)
                    name = unquote(self.headers.get('X-File-Name',''))
                    ext = Path(name).suffix.lower()
                    if ext not in EXTENSIONS:
                        raise ValueError('Choose a supported video or image.')
                    path = engine.root / 'inputs' / (str(uuid.uuid4()) + ext)
                    remaining = length
                    try:
                        with path.open('xb') as file:
                            while remaining:
                                block = self.rfile.read(min(1024*1024,remaining))
                                if not block:
                                    raise ValueError('Upload interrupted.')
                                file.write(block)
                                remaining -= len(block)
                        return self.reply(engine.add_input(path,name))
                    except Exception:
                        path.unlink(missing_ok=True)
                        raise
                if length > 500000:
                    return self.reply({'error':'Request too large.'},413)
                body = json.loads(self.rfile.read(length) or b'{}')
                if route == '/jobs':
                    return self.reply(engine.create(body))
                if route == '/output-folder':
                    return self.reply(engine.configure_output(body.get('outputFolder')))
                if route == '/targets':
                    engine.configure(body)
                    return self.reply({'targets':engine.target_view()})
                if route == '/refresh-targets':
                    return self.reply({'targets':engine.refresh_targets()})
                if route.startswith('/jobs/') and route.endswith('/retry-drive'):
                    return self.reply(engine.retry_drive(route.split('/')[2]))
                if route.startswith('/jobs/') and route.endswith('/cancel'):
                    return self.reply(engine.cancel(route.split('/')[2]))
                if route.startswith('/jobs/') and route.endswith('/delete'):
                    return self.reply(engine.delete(route.split('/')[2]))
                self.reply({'error':'Not found.'},404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                self.reply({'error':str(error)},400)

    print(f'Flow Studio local processor ready on 127.0.0.1:{args.port}', flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    def terminate(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for key in list(engine.jobs):
            if engine.view(key)['status'] in ('queued', 'running', 'cancelling'):
                engine.cancel(key)
        deadline = time.time() + 5
        while engine.work.unfinished_tasks and time.time() < deadline:
            time.sleep(.05)
        server.server_close()


if __name__ == '__main__':
    main()
