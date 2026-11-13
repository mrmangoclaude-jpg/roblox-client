#!/usr/bin/env python3
"""Run up to six isolated Rove clients in one private server with a shared API.

Only one designated leader client runs the full solver/sniping script while
the coordinator HTTP API broadcasts redeemed codes to every connected follower.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from join_allocation import write_private
from local_transport import probe
from platform_environment import runtime_environment
from platform_process import group_options, stop_group
from roblox_session import REPO_ROOT, SessionError
from script_console import send_source
from select_private_server import resolve_invite


FOLLOWER_SCRIPT = REPO_ROOT / 'runtime/scripts/redeem_follower.luau'
LEADER_PRELUDE = REPO_ROOT / 'runtime/scripts/redeem_leader_prelude.luau'
MAX_BODY_BYTES = 1024 * 1024


def discover_accounts(accounts_dir: Path, *, max_clients: int = 6) -> list[tuple[str, str]]:
    """Return sorted (profile_name, cookie) pairs from ``*.txt`` files."""
    if max_clients < 1 or max_clients > 6:
        raise ValueError('max_clients must be between 1 and 6')
    if not accounts_dir.is_dir():
        raise SessionError(f'Accounts directory does not exist: {accounts_dir}')
    entries: list[tuple[str, str]] = []
    for path in sorted(accounts_dir.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() != '.txt':
            continue
        if path.name.lower().endswith('.example.txt') or path.name.startswith('.'):
            continue
        cookie = path.read_text(encoding='utf-8').strip()
        if not cookie:
            continue
        entries.append((path.stem, cookie))
        if len(entries) >= max_clients:
            break
    if not entries:
        raise SessionError(f'No non-empty *.txt cookie files found in {accounts_dir}')
    return entries


def prepare_profile(profile_root: Path, cookie: str, link_url: str | None) -> dict | None:
    """Create isolated secrets/outputs dirs for one bot and resolve its invite."""
    secrets_dir = profile_root / 'secrets'
    outputs_dir = profile_root / 'outputs/gamejoin'
    logs_dir = profile_root / 'outputs/logs'
    secrets_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        os.chmod(secrets_dir, 0o700)
    _write_cookie(secrets_dir / 'roblox-cookie.txt', cookie)
    if link_url:
        write_private(secrets_dir / 'private-server-link.json', {'url': link_url})
        return resolve_invite(link_url, state_root=profile_root, cookie=cookie, archive_previous=False)
    return None


def _write_cookie(path: Path, cookie: str) -> None:
    from platform_files import open_nofollow
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = open_nofollow(path, flags, 0o600)
    try:
        if os.name != 'nt':
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            fd = None
            out.write(cookie + '\n')
    finally:
        if fd is not None:
            os.close(fd)


def build_leader_script(leader_script_path: Path, output_path: Path, *,
                        api_url: str, token: str, sender: str) -> Path:
    """Wrap the user's leader script with the broadcast prelude without editing the source file."""
    prelude = LEADER_PRELUDE.read_text(encoding='utf-8')
    prelude = (prelude
               .replace('__ROVE_API_URL__', json.dumps(api_url))
               .replace('__ROVE_TOKEN__', json.dumps(token))
               .replace('__ROVE_SENDER__', json.dumps(sender)))
    body = leader_script_path.read_text(encoding='utf-8')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prelude + '\n' + body, encoding='utf-8')
    return output_path


def build_redeem_snippet(code: str) -> str:
    """Return bounded Luau source that invokes _G.ROVE_REDEEM on a follower VM."""
    encoded = json.dumps(code, ensure_ascii=True)
    return (
        f'local code = {encoded}\n'
        'if type(_G.ROVE_REDEEM) == "function" then\n'
        '    return _G.ROVE_REDEEM(code)\n'
        'end\n'
        'return false, "follower redeemer not loaded yet"\n'
    )


class CoordinatorState:
    """Thread-safe bot registry, code-broadcast deduplicator, and HTTP proxy cache."""

    def __init__(self, *, dedupe_seconds: float = 10.0, token: str | None = None,
                 sender_executor=None):
        self.dedupe_seconds = dedupe_seconds
        self.token = token or secrets.token_hex(24)
        self.lock = threading.RLock()
        self.bots: dict[str, dict] = {}
        self.seen_codes: dict[str, float] = {}
        self.history: list[dict] = []
        self.stop_event = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix='rove-bcast')
        self._sender = sender_executor or send_source
        self._cache_lock = threading.Lock()
        self._upstream_cache: dict[str, dict] = {}
        self._inflight: dict[str, threading.Event] = {}

    def register_bot(self, name: str, profile_root: Path, *, role: str) -> None:
        with self.lock:
            self.bots[name] = {
                'name': name,
                'role': role,
                'profile_root': profile_root,
                'socket_path': profile_root / 'secrets/client-script.sock',
                'pid': None,
                'returncode': None,
                'redeemed_count': 0,
                'last_code': None,
                'last_result': None,
            }

    def attach_process(self, name: str, process: subprocess.Popen) -> None:
        with self.lock:
            if name in self.bots:
                self.bots[name]['pid'] = process.pid
                self.bots[name]['process'] = process

    def status(self) -> dict:
        with self.lock:
            bot_rows = []
            for name, info in self.bots.items():
                proc = info.get('process')
                rc = proc.poll() if proc is not None else info.get('returncode')
                if rc is not None:
                    info['returncode'] = rc
                sock_ready = False
                if rc is None and info['socket_path'].exists():
                    try:
                        probe(info['socket_path'], timeout=0.1)
                        sock_ready = True
                    except OSError:
                        sock_ready = False
                bot_rows.append({
                    'name': name,
                    'role': info['role'],
                    'pid': info['pid'],
                    'alive': rc is None and info['pid'] is not None,
                    'returncode': rc,
                    'console_ready': sock_ready,
                    'redeemed_count': info['redeemed_count'],
                    'last_code': info['last_code'],
                    'last_result': info['last_result'],
                })
            return {
                'ok': True,
                'bot_count': len(bot_rows),
                'bots': bot_rows,
                'recent_broadcasts': self.history[-20:],
            }

    def broadcast_redeem(self, code: str, *, sender: str | None = None,
                         force: bool = False, include_sender: bool = False) -> dict:
        code = code.strip()
        if not code or len(code) > 64:
            return {'ok': False, 'error': 'Code must be 1..64 characters'}
        now = time.monotonic()
        with self.lock:
            prev = self.seen_codes.get(code)
            if not force and prev is not None and (now - prev) < self.dedupe_seconds:
                return {'ok': True, 'deduplicated': True, 'code': code, 'dispatched': 0, 'results': {}}
            self.seen_codes[code] = now
            targets = [
                (name, info['socket_path'])
                for name, info in self.bots.items()
                if include_sender or name != sender
            ]

        snippet = build_redeem_snippet(code)
        futures = {
            name: self._executor.submit(self._dispatch_one, name, sock, snippet, code)
            for name, sock in targets
        }
        results = {name: fut.result() for name, fut in futures.items()}
        entry = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'code': code,
            'sender': sender,
            'dispatched': len(results),
            'results': results,
        }
        with self.lock:
            self.history.append(entry)
            if len(self.history) > 100:
                self.history = self.history[-100:]
        return {'ok': True, 'deduplicated': False, **entry}

    def _dispatch_one(self, name: str, sock_path: Path, source: str, code: str | None) -> dict:
        try:
            reply = self._sender(sock_path, source, timeout_ms=1000)
            ok = bool(reply.get('ok', True)) if isinstance(reply, dict) else True
            out = {'ok': ok, 'reply': reply}
        except Exception as error:
            out = {'ok': False, 'error': str(error) or type(error).__name__}
        with self.lock:
            bot = self.bots.get(name)
            if bot is not None:
                if code is not None and out['ok']:
                    bot['redeemed_count'] += 1
                    bot['last_code'] = code
                bot['last_result'] = out
        return out

    def execute_on(self, source: str, *, target: str = 'all') -> dict:
        if not isinstance(source, str) or not source.strip():
            return {'ok': False, 'error': 'source must be non-empty Luau'}
        with self.lock:
            if target == 'all':
                targets = [(n, b['socket_path']) for n, b in self.bots.items()]
            elif target in self.bots:
                targets = [(target, self.bots[target]['socket_path'])]
            else:
                return {'ok': False, 'error': f'Unknown target bot: {target}'}
        futures = {
            name: self._executor.submit(self._dispatch_one, name, sock, source, None)
            for name, sock in targets
        }
        return {'ok': True, 'results': {name: fut.result() for name, fut in futures.items()}}

    def singleflight_http(self, *, url: str, method: str = 'POST', headers: dict | None = None,
                          body: str | None = None, cache_key: str | None = None,
                          fetcher=None) -> dict:
        """Deduplicate identical upstream HTTP calls across multiple bots/callers."""
        if not (url.startswith('https://') or url.startswith('http://')):
            return {'ok': False, 'error': 'HTTP(S) URL required'}
        key = cache_key or hashlib.sha256(
            json.dumps({'url': url, 'method': method.upper(), 'body': body or ''}, sort_keys=True).encode()
        ).hexdigest()
        while True:
            with self._cache_lock:
                if key in self._upstream_cache:
                    return {'ok': True, 'cached': True, **self._upstream_cache[key]}
                event = self._inflight.get(key)
                if event is None:
                    event = threading.Event()
                    self._inflight[key] = event
                    leader = True
                    break
                leader = False
            event.wait(timeout=25)
            if not event.is_set():
                return {'ok': False, 'error': 'upstream request timed out'}

        try:
            payload = _default_fetch(url, method, headers or {}, body) if fetcher is None else fetcher(url, method, headers or {}, body)
            with self._cache_lock:
                self._upstream_cache[key] = payload
            return {'ok': True, 'cached': False, **payload}
        except Exception as error:
            return {'ok': False, 'error': str(error) or type(error).__name__}
        finally:
            with self._cache_lock:
                done = self._inflight.pop(key, None)
                if done is not None:
                    done.set()

    def close(self) -> None:
        self.stop_event.set()
        self._executor.shutdown(wait=False)


def _default_fetch(url: str, method: str, headers: dict, body: str | None) -> dict:
    req = urllib.request.Request(
        url,
        data=body.encode('utf-8') if body is not None else None,
        method=method.upper(),
        headers={str(k): str(v) for k, v in headers.items()},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return {'status': resp.status, 'body': resp.read(4 * 1024 * 1024).decode('utf-8', errors='replace')}
    except urllib.error.HTTPError as err:
        return {'status': err.code, 'body': err.read(4 * 1024 * 1024).decode('utf-8', errors='replace')}


def make_coordinator_server(state: CoordinatorState, *, port: int = 0) -> ThreadingHTTPServer:
    """Create the localhost-only HTTP API bound to 127.0.0.1."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            return

        def _authorized(self) -> bool:
            provided = self.headers.get('X-Rove-Token', '')
            return hmac.compare_digest(provided, state.token)

        def _send_json(self, status: int, payload: dict) -> None:
            raw = json.dumps(payload, ensure_ascii=True).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _read_json(self) -> dict:
            length = int(self.headers.get('Content-Length', '0') or '0')
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError('Invalid or oversized request body')
            raw = self.rfile.read(length)
            value = json.loads(raw.decode('utf-8'))
            if not isinstance(value, dict):
                raise ValueError('JSON object required')
            return value

        def do_GET(self):  # noqa: N802
            if not self._authorized():
                self._send_json(401, {'ok': False, 'error': 'Missing or invalid X-Rove-Token'})
                return
            if self.path == '/api/status':
                self._send_json(200, state.status())
                return
            self._send_json(404, {'ok': False, 'error': 'Not found'})

        def do_POST(self):  # noqa: N802
            if not self._authorized():
                self._send_json(401, {'ok': False, 'error': 'Missing or invalid X-Rove-Token'})
                return
            if self.path == '/api/stop':
                state.stop_event.set()
                self._send_json(200, {'ok': True, 'stopping': True})
                return
            try:
                body = self._read_json()
            except Exception as error:
                self._send_json(400, {'ok': False, 'error': str(error)})
                return
            if self.path == '/api/redeem':
                code = body.get('code', '')
                if not isinstance(code, str):
                    self._send_json(400, {'ok': False, 'error': 'code must be text'})
                    return
                res = state.broadcast_redeem(
                    code,
                    sender=body.get('sender') if isinstance(body.get('sender'), str) else None,
                    force=bool(body.get('force', False)),
                    include_sender=bool(body.get('include_sender', False)),
                )
                self._send_json(200 if res.get('ok') else 400, res)
                return
            if self.path == '/api/execute':
                source = body.get('source', '')
                target = body.get('target', 'all')
                res = state.execute_on(source, target=str(target))
                self._send_json(200 if res.get('ok') else 400, res)
                return
            if self.path == '/api/gemini-cache':
                res = state.singleflight_http(
                    url=str(body.get('url', '')),
                    method=str(body.get('method', 'POST')),
                    headers=body.get('headers') if isinstance(body.get('headers'), dict) else None,
                    body=body.get('body') if isinstance(body.get('body'), str) else None,
                    cache_key=body.get('cache_key') if isinstance(body.get('cache_key'), str) else None,
                )
                self._send_json(200 if res.get('ok') else 400, res)
                return
            self._send_json(404, {'ok': False, 'error': 'Not found'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def build_session_command(script_path: Path | None, *, duration: int, memory_mb: int,
                          physics: bool, visual_mesh_collisions: bool, log_level: str) -> list[str]:
    cmd = [
        sys.executable, '-u', str(REPO_ROOT / 'scripts/game_session.py'),
        '--refresh', '--protocol-sync', '--luau-range', '--ticket',
        '--time-sync', '--bytecode-auth',
        '--duration', str(duration), '--progress',
        '--script-console', '--persistent-scripts', '--chat-console',
        '--log-level', log_level, '--memory-mb', str(memory_mb),
    ]
    if physics:
        cmd.append('--physics')
        if visual_mesh_collisions:
            cmd.append('--visual-mesh-collisions')
    if script_path is not None:
        cmd.extend(['--script', str(script_path)])
    return cmd


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accounts-dir', type=Path, default=REPO_ROOT / 'secrets/accounts',
                        help='Directory containing up to 6 *.txt cookie files')
    parser.add_argument('--profiles-dir', type=Path, default=REPO_ROOT / 'outputs/profiles',
                        help='Directory for per-bot isolated secrets/outputs/logs')
    parser.add_argument('--private-server', default=None,
                        help='Roblox private server share URL (defaults to secrets/private-server-link.json)')
    parser.add_argument('--leader-script', type=Path, default=None,
                        help='Luau script run on Bot 1 only (e.g. riddler.lua); followers run the lightweight redeemer')
    parser.add_argument('--max-clients', type=int, default=6, help='Number of clients to launch (1..6)')
    parser.add_argument('--stagger-seconds', type=float, default=2.0, help='Delay between launching bots')
    parser.add_argument('--memory-mb', type=int, default=256, help='Luau VM memory cap per bot (8..512 MiB)')
    parser.add_argument('--duration', type=int, default=0, help='Session duration in seconds (0 = until stopped)')
    parser.add_argument('--api-port', type=int, default=0, help='Local coordinator HTTP API port (0 = auto)')
    parser.add_argument('--physics', action='store_true', help='Enable character physics (off by default to save CPU/RAM)')
    parser.add_argument('--visual-mesh-collisions', action='store_true', help='Enable visual mesh colliders (requires --physics)')
    parser.add_argument('--log-level', choices=('verbose', 'normal', 'off'), default='normal')
    args = parser.parse_args(argv)
    if args.visual_mesh_collisions and not args.physics:
        parser.error('--visual-mesh-collisions requires --physics')
    if not 1 <= args.max_clients <= 6:
        parser.error('--max-clients must be between 1 and 6')
    if not 8 <= args.memory_mb <= 512:
        parser.error('--memory-mb must be between 8 and 512')
    if args.leader_script is not None and not args.leader_script.is_file():
        parser.error(f'Leader script not found: {args.leader_script}')
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    link_url = args.private_server
    if not link_url:
        saved_link = REPO_ROOT / 'secrets/private-server-link.json'
        if not saved_link.is_file():
            raise SessionError('Provide --private-server URL or save one in secrets/private-server-link.json')
        link_url = json.loads(saved_link.read_text(encoding='utf-8'))['url']

    accounts = discover_accounts(args.accounts_dir, max_clients=args.max_clients)
    state = CoordinatorState()
    server = make_coordinator_server(state, port=args.api_port)
    port = server.server_address[1]
    api_base = f'http://127.0.0.1:{port}'
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print(json.dumps({
        'coordinator_url': api_base,
        'token': state.token,
        'endpoints': {
            'status': f'GET {api_base}/api/status',
            'redeem': f'POST {api_base}/api/redeem',
            'execute': f'POST {api_base}/api/execute',
            'gemini_cache': f'POST {api_base}/api/gemini-cache',
            'stop': f'POST {api_base}/api/stop',
        },
        'clients': [name for name, _ in accounts],
    }, indent=2), flush=True)

    processes: list[tuple[str, subprocess.Popen, object]] = []
    try:
        for index, (name, cookie) in enumerate(accounts):
            role = 'leader' if index == 0 else 'follower'
            profile_root = (args.profiles_dir / name).resolve()
            prepare_profile(profile_root, cookie, link_url)
            state.register_bot(name, profile_root, role=role)

        base_env = runtime_environment(REPO_ROOT)
        for index, (name, _) in enumerate(accounts):
            if state.stop_event.is_set():
                break
            profile_root = (args.profiles_dir / name).resolve()
            if index == 0 and args.leader_script is not None:
                script_for_bot = build_leader_script(
                    args.leader_script,
                    profile_root / 'secrets/leader_wrapped.luau',
                    api_url=f'{api_base}/api/redeem',
                    token=state.token,
                    sender=name,
                )
            else:
                script_for_bot = FOLLOWER_SCRIPT
            cmd = build_session_command(
                script_for_bot,
                duration=args.duration,
                memory_mb=args.memory_mb,
                physics=args.physics,
                visual_mesh_collisions=args.visual_mesh_collisions,
                log_level=args.log_level,
            )
            env = dict(base_env)
            env['ROVE_STATE_ROOT'] = str(profile_root)
            log_file = (profile_root / 'outputs/logs/session-stdout.log').open('w', encoding='utf-8')
            proc = subprocess.Popen(
                cmd, cwd=str(REPO_ROOT), env=env,
                stdout=log_file, stderr=subprocess.STDOUT,
                **group_options(),
            )
            state.attach_process(name, proc)
            processes.append((name, proc, log_file))
            print(f'[multi] started {name} ({ "leader" if index == 0 else "follower" }, pid={proc.pid})', flush=True)
            if index + 1 < len(accounts) and args.stagger_seconds > 0:
                state.stop_event.wait(args.stagger_seconds)

        while not state.stop_event.is_set():
            if processes and all(proc.poll() is not None for _, proc, _ in processes):
                break
            state.stop_event.wait(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        state.stop_event.set()
        for _, proc, log_file in processes:
            stop_group(proc, force=True)
            log_file.close()
        server.shutdown()
        server.server_close()
        state.close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SessionError as error:
        print(json.dumps({'error_type': 'SessionError', 'error': str(error)}))
        raise SystemExit(1)
