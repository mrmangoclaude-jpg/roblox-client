import copy
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

from client_session_lease import acquire_session_lease
import multi_session
from persistent_runtime import PersistentClientScriptRuntime, PersistentLuauHost
import roblox_session
from script_console import ScriptConsole

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = json.loads((ROOT / 'tests/fixtures/world_snapshot.json').read_text(encoding='utf-8'))


class MultiSessionTests(unittest.TestCase):
    def test_state_root_env_isolates_leases_across_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root_a = Path(tmp) / 'bot1'
            root_b = Path(tmp) / 'bot2'
            (root_a / 'secrets').mkdir(parents=True)
            (root_b / 'secrets').mkdir(parents=True)
            with acquire_session_lease(root_a), acquire_session_lease(root_b):
                self.assertTrue((root_a / 'secrets/client-session.lock').exists())
                self.assertTrue((root_b / 'secrets/client-session.lock').exists())

    def test_roblox_session_module_respects_state_root_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom_root = Path(tmp).resolve()
            with mock.patch.dict(os.environ, {'ROVE_STATE_ROOT': str(custom_root)}):
                importlib.reload(roblox_session)
                self.assertEqual(roblox_session.ROOT, custom_root)
                self.assertEqual(roblox_session.REPO_ROOT, multi_session.REPO_ROOT)
        importlib.reload(roblox_session)
        self.assertEqual(roblox_session.ROOT, roblox_session.REPO_ROOT)

    def test_persistent_runtime_validates_and_stores_memory_mb(self):
        with self.assertRaises(ValueError):
            PersistentClientScriptRuntime(lambda: None, 1, memory_mb=4)
        with self.assertRaises(ValueError):
            PersistentClientScriptRuntime(lambda: None, 1, memory_mb=1024)
        rt = PersistentClientScriptRuntime(lambda: None, 1, memory_mb=128)
        self.assertEqual(rt.memory_mb, 128)

    def test_discover_accounts_sorts_skips_empty_and_caps_at_six(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for i in range(1, 9):
                (d / f'bot{i}.txt').write_text(f'cookie-{i}\n', encoding='utf-8')
            (d / 'empty.txt').write_text('   \n', encoding='utf-8')
            (d / 'bot1.example.txt').write_text('ignored\n', encoding='utf-8')
            accounts = multi_session.discover_accounts(d, max_clients=6)
            self.assertEqual([n for n, _ in accounts], [f'bot{i}' for i in range(1, 7)])

    def test_leader_wrapper_preserves_original_script_and_runs_hooks_in_luau(self):
        snapshot = copy.deepcopy(SNAPSHOT)
        with tempfile.TemporaryDirectory() as tmp:
            orig = Path(tmp) / 'riddler_orig.lua'
            orig_body = (
                'local Players = game:GetService("Players")\n'
                'local pg = Instance.new("Folder"); pg.Name = "PlayerGui"; pg.Parent = Players.LocalPlayer\n'
                'local codes = Instance.new("ScreenGui"); codes.Name = "Codes"; codes.Parent = pg\n'
                'local inner = Instance.new("Frame"); inner.Name = "Codes"; inner.Parent = codes\n'
                'local cr = Instance.new("Frame"); cr.Name = "CodeRedeem"; cr.Parent = inner\n'
                'local tb = Instance.new("TextBox"); tb.Name = "TextBox"; tb.Parent = cr\n'
                'local btn = Instance.new("TextButton"); btn.Name = "Confirm"; btn.Parent = inner\n'
                '_G.HIT = false\n'
                'btn.Activated:Connect(function() _G.HIT = tb.Text end)\n'
                'tb.Text = "MANGO100"\n'
                'for _, c in ipairs(getconnections(btn.Activated)) do c:Fire() end\n'
                'return _G.HIT\n'
            )
            orig.write_text(orig_body, encoding='utf-8')
            state = multi_session.CoordinatorState()
            state.register_bot('bot2', Path(tmp) / 'bot2', role='follower')
            dispatched = []
            state._sender = lambda sock, src, timeout_ms=1000: (dispatched.append(src) or {'ok': True})
            server = multi_session.make_coordinator_server(state, port=0)
            port = server.server_address[1]
            srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
            srv_thread.start()
            wrapped = multi_session.build_leader_script(
                orig,
                Path(tmp) / 'leader_wrapped.luau',
                api_url=f'http://127.0.0.1:{port}/api/redeem',
                token=state.token,
                sender='bot1',
            )
            self.assertEqual(orig.read_text(encoding='utf-8'), orig_body)
            host = PersistentLuauHost(snapshot, memory_mb=64)
            try:
                res = host.call({'op': 'execute', 'source': wrapped.read_text(encoding='utf-8'), 'timeout_ms': 1000})
                self.assertTrue(res['ok'], res)
                self.assertEqual(res['values'], ['MANGO100'])
                # Pump deferred tasks so task.spawn HTTP request reaches the coordinator server
                for _ in range(20):
                    host.call({'op': 'poll', 'timeout_ms': 50})
                    if dispatched:
                        break
                self.assertEqual(len(dispatched), 1)
                self.assertIn('MANGO100', dispatched[0])
            finally:
                host.close()
                server.shutdown()
                server.server_close()
                state.close()

    def test_follower_luau_script_redeems_via_ui_confirm_connections(self):
        snapshot = copy.deepcopy(SNAPSHOT)
        host = PersistentLuauHost(snapshot, memory_mb=64)
        try:
            setup = (
                'local pg = Instance.new("Folder"); pg.Name = "PlayerGui"; pg.Parent = game:GetService("Players").LocalPlayer\n'
                'local codes = Instance.new("ScreenGui"); codes.Name = "Codes"; codes.Parent = pg\n'
                'local inner = Instance.new("Frame"); inner.Name = "Codes"; inner.Parent = codes\n'
                'local cr = Instance.new("Frame"); cr.Name = "CodeRedeem"; cr.Parent = inner\n'
                'local tb = Instance.new("TextBox"); tb.Name = "TextBox"; tb.Parent = cr\n'
                'local btn = Instance.new("TextButton"); btn.Name = "Confirm"; btn.Parent = inner\n'
                '_G.REDEEMED = nil\n'
                'btn.Activated:Connect(function() _G.REDEEMED = tb.Text end)\n'
            )
            r1 = host.call({'op': 'execute', 'source': setup, 'timeout_ms': 1000})
            self.assertTrue(r1['ok'], r1)
            follower_src = multi_session.FOLLOWER_SCRIPT.read_text(encoding='utf-8')
            r2 = host.call({'op': 'execute', 'source': follower_src, 'timeout_ms': 1000})
            self.assertTrue(r2['ok'], r2)
            r3 = host.call({'op': 'execute', 'source': multi_session.build_redeem_snippet('GARA77MA'), 'timeout_ms': 1000})
            self.assertTrue(r3['ok'], r3)
            self.assertEqual(r3['values'], [True, 'ui:GARA77MA'])
            r4 = host.call({'op': 'execute', 'source': 'return _G.REDEEMED', 'timeout_ms': 500})
            self.assertEqual(r4['values'], ['GARA77MA'])
        finally:
            host.close()

    def test_coordinator_api_broadcast_dedupe_auth_and_singleflight_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            received = {}
            consoles = []
            stop_pump = threading.Event()
            state = multi_session.CoordinatorState(dedupe_seconds=10.0)
            for idx in range(1, 4):
                name = f'bot{idx}'
                p = root / name
                (p / 'secrets').mkdir(parents=True)
                state.register_bot(name, p, role='leader' if idx == 1 else 'follower')
                sock = p / 'secrets/client-script.sock'

                def make_exec(bot_name):
                    def _exec(source, timeout_ms=1000):
                        received.setdefault(bot_name, []).append(source)
                        return {'ok': True, 'values': [True, bot_name]}
                    return _exec

                c = ScriptConsole(sock, make_exec(name))
                consoles.append(c)

            def pump():
                while not stop_pump.is_set():
                    for c in consoles:
                        c.poll()
                    stop_pump.wait(0.01)

            pump_thread = threading.Thread(target=pump, daemon=True)
            pump_thread.start()
            server = multi_session.make_coordinator_server(state, port=0)
            port = server.server_address[1]
            srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
            srv_thread.start()
            try:
                # Unauthorized request rejected
                req_unauth = urllib.request.Request(f'http://127.0.0.1:{port}/api/status')
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req_unauth, timeout=3)
                self.assertEqual(ctx.exception.code, 401)

                # Leader broadcasts once -> followers (bot2, bot3) redeem; sender (bot1) skipped
                req = urllib.request.Request(
                    f'http://127.0.0.1:{port}/api/redeem',
                    data=json.dumps({'code': 'BRAINROT1', 'sender': 'bot1'}).encode('utf-8'),
                    headers={'Content-Type': 'application/json', 'X-Rove-Token': state.token},
                    method='POST',
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    payload = json.loads(resp.read().decode('utf-8'))
                self.assertTrue(payload['ok'])
                self.assertFalse(payload['deduplicated'])
                self.assertEqual(payload['dispatched'], 2)
                self.assertEqual(set(payload['results']), {'bot2', 'bot3'})
                self.assertNotIn('bot1', received)
                self.assertIn('BRAINROT1', received['bot2'][0])
                self.assertIn('BRAINROT1', received['bot3'][0])

                # Repeat within 10s is deduplicated
                with urllib.request.urlopen(req, timeout=3) as resp2:
                    payload2 = json.loads(resp2.read().decode('utf-8'))
                self.assertTrue(payload2['deduplicated'])
                self.assertEqual(payload2['dispatched'], 0)

                # Status reflects follower redemption count
                req_status = urllib.request.Request(
                    f'http://127.0.0.1:{port}/api/status',
                    headers={'X-Rove-Token': state.token},
                )
                with urllib.request.urlopen(req_status, timeout=3) as sresp:
                    status_data = json.loads(sresp.read().decode('utf-8'))
                counts = {b['name']: b['redeemed_count'] for b in status_data['bots']}
                self.assertEqual(counts, {'bot1': 0, 'bot2': 1, 'bot3': 1})

                # Single-flight upstream HTTP cache fires fetcher only once for 6 concurrent callers
                calls = 0
                gate = threading.Event()

                def slow_fetch(url, method, headers, body):
                    nonlocal calls
                    calls += 1
                    gate.wait(0.2)
                    return {'status': 200, 'body': 'CODE: UNIQUE99'}

                with ThreadPoolExecutor(max_workers=6) as pool:
                    futs = [
                        pool.submit(
                            state.singleflight_http,
                            url='https://example.invalid/gemini',
                            body='riddle prompt',
                            fetcher=slow_fetch,
                        )
                        for _ in range(6)
                    ]
                    gate.set()
                    out = [f.result() for f in futs]
                self.assertEqual(calls, 1)
                self.assertEqual(sum(1 for item in out if not item['cached']), 1)
                self.assertTrue(all(item['body'] == 'CODE: UNIQUE99' for item in out))
            finally:
                stop_pump.set()
                pump_thread.join(timeout=2)
                for c in consoles:
                    c.close()
                server.shutdown()
                server.server_close()
                state.close()


if __name__ == '__main__':
    unittest.main()
