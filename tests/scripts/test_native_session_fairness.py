"""Fake-transport regression for tick scheduling under a slow callback.

These tests do not create a socket, request an allocation, or connect to Roblox.
They check fixed-deadline cadence and skipped deadlines under slow callbacks.
"""
from contextlib import nullcontext
from collections import deque
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_session import NativeSession
from aioquic.quic.events import ConnectionTerminated


class NativeSessionFairnessTests(unittest.TestCase):
    def test_termination_preserves_only_known_safe_reason(self):
        for phrase in ('Idle timeout', 'private-session-data'):
            client = NativeSession.__new__(NativeSession)
            client.report = {}
            client.http = None
            client.finished = False
            client.handle_event(ConnectionTerminated(
                error_code=1, frame_type=0, reason_phrase=phrase), None, None)
            self.assertTrue(client.finished)
            self.assertEqual(client.report['termination']['reason_length'], len(phrase))
            if phrase == 'Idle timeout':
                self.assertEqual(client.report['termination']['reason'], phrase)
            else:
                self.assertNotIn('reason', client.report['termination'])
                self.assertNotIn(phrase, json.dumps(client.report))

    def make_fake_client(self, clock, queued_datagrams, order, *, recv_seconds=0.00001):
        class FakeSocket:
            def bind(self, address):
                pass

            def setblocking(self, enabled):
                pass

            def recvfrom(self, _size):
                if not queued_datagrams:
                    raise BlockingIOError
                data = queued_datagrams.popleft()
                clock[0] += recv_seconds
                return data, ("127.0.0.1", 9)

            def close(self):
                pass

            def sendto(self, data, destination):
                self.sent.append((data, destination))

        pending_events = deque()

        class FakeQuic:
            def connect(self, endpoint, now):
                pass

            def datagrams_to_send(self, now):
                return []

            def get_timer(self):
                return None

            def receive_datagram(self, payload, endpoint, *, now):
                order.append(("receive", payload))
                pending_events.append(payload)

            def next_event(self):
                return pending_events.popleft() if pending_events else None

            def close(self, **kwargs):
                pass

        client = NativeSession.__new__(NativeSession)
        client.duration = 0.05
        client.started = clock[0]
        client.endpoint = ("127.0.0.1", 9)
        client.header = b"header:"
        client.pins = []
        client.capture = []
        client.finished = False
        client.report = {"datagrams_sent": 0, "datagrams_received": 0,
                         "bytes_received": 0,
                         "run_id": "synthetic",
                         "quic_handshake_completed": False}
        client.quic = FakeQuic()
        client.handle_event = lambda event, _ready, _packet: order.append(("event", event))
        sock = FakeSocket()
        sock.sent = []
        return client, sock

    def test_short_callback_keeps_configured_twenty_hz_cadence(self):
        clock = [0.0]
        tick_starts = []
        callback_ends = []
        waits = []

        def select_wait(read, write, error, timeout):
            self.assertGreater(timeout, 0)
            waits.append(timeout)
            clock[0] += timeout
            return [], [], []

        order = []
        client, fake_socket = self.make_fake_client(clock, deque(), order)
        client.duration = 0.25

        def short_tick(_client, scheduled_now):
            tick_starts.append(scheduled_now)
            clock[0] += 0.01
            callback_ends.append(clock[0])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/gamejoin").mkdir(parents=True)
            with patch("native_session.socket.socket", return_value=fake_socket), \
                    patch("native_session.select.select", side_effect=select_wait), \
                    patch("native_session.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("native_session.certificate_pins", side_effect=lambda *_: nullcontext()), \
                    patch("native_session.write_private"), \
                    patch("native_session.ROOT", root):
                client.run(lambda _client: None, lambda *_args: None,
                           report_name="synthetic", on_tick=short_tick,
                           tick_interval=0.05)

        self.assertEqual(len(tick_starts), 5)
        self.assertEqual(len(callback_ends), len(tick_starts))
        for next_start, previous_start in zip(tick_starts[1:], tick_starts):
            self.assertAlmostEqual(next_start - previous_start, 0.05)
        self.assertAlmostEqual(tick_starts[-1], 0.20)
        self.assertEqual(client.report["elapsed_seconds"], 0.25)

    def test_long_callback_skips_missed_deadlines_without_catchup(self):
        clock = [0.0]
        starts = []
        def select_wait(read, write, error, timeout):
            self.assertGreater(timeout, 0)
            clock[0] += timeout
            return [], [], []
        client, fake_socket = self.make_fake_client(clock, deque(), [])
        client.duration = 0.5
        def long_tick(_client, scheduled_now):
            starts.append(scheduled_now)
            clock[0] += 0.12
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/gamejoin").mkdir(parents=True)
            with patch("native_session.socket.socket", return_value=fake_socket), \
                    patch("native_session.select.select", side_effect=select_wait), \
                    patch("native_session.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("native_session.certificate_pins", side_effect=lambda *_: nullcontext()), \
                    patch("native_session.write_private"), \
                    patch("native_session.ROOT", root):
                client.run(lambda _client: None, lambda *_args: None,
                           report_name="synthetic", on_tick=long_tick,
                           tick_interval=0.05)
        self.assertEqual(len(starts), 4)
        for left, right in zip(starts, starts[1:]):
            self.assertAlmostEqual(right-left, 0.15)
        self.assertGreaterEqual(client.report['local_scheduler']['tick_deadlines_skipped'], 6)

    def test_report_finalizer_runs_before_single_native_public_and_history_save(self):
        clock = [0.0]
        order = []

        def select_wait(read, write, error, timeout):
            clock[0] += timeout
            return [], [], []

        client, fake_socket = self.make_fake_client(clock, deque(), order)
        client.duration = 0.05
        client.report_finalizer = lambda report: (
            order.append('finalizer'),
            report.update({'experimental_physics': {
                'running': False, 'stop_reason': 'server_disconnected'}}))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'outputs/gamejoin'
            output.mkdir(parents=True)
            history_path = output / 'session-history.jsonl'
            history_path.write_text(json.dumps({'run_id': 'prior'}) + '\n')
            public_path = output / 'synthetic.json'
            history_open_modes = []
            real_path_open = Path.open

            def track_path_open(path, mode='r', *args, **kwargs):
                if path == history_path:
                    history_open_modes.append(mode)
                return real_path_open(path, mode, *args, **kwargs)

            with patch("native_session.socket.socket", return_value=fake_socket), \
                    patch("native_session.select.select", side_effect=select_wait), \
                    patch("native_session.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("native_session.certificate_pins", side_effect=lambda *_: nullcontext()), \
                    patch("native_session.write_private"), \
                    patch("native_session.ROOT", root), \
                    patch("pathlib.Path.open", new=track_path_open):
                result = client.run(lambda _client: None, lambda *_args: None,
                                    report_name='synthetic')

            self.assertEqual(order, ['finalizer'])
            self.assertEqual(history_open_modes, ['a'])
            saved_public = json.loads(public_path.read_text())
            saved_history = [json.loads(line) for line in history_path.read_text().splitlines()]
            self.assertFalse(saved_public['experimental_physics']['running'])
            self.assertEqual(saved_public, result)
            self.assertEqual([row['run_id'] for row in saved_history], ['prior', 'synthetic'])
            self.assertEqual(saved_history[-1], saved_public)

    def test_udp_queue_is_drained_within_batch_bound_before_luau_tick(self):
        clock = [0.0]
        order = []
        payloads = deque(bytes((i,)) for i in range(70))
        client, fake_socket = self.make_fake_client(clock, payloads, order)
        received_before_tick = []

        def select_wait(read, write, error, timeout):
            if payloads:
                return [fake_socket], [], []
            clock[0] += timeout
            return [], [], []

        def tick(_client, _now):
            order.append(("tick", None))
            received_before_tick.append(len(order) // 2)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/gamejoin").mkdir(parents=True)
            with patch("native_session.socket.socket", return_value=fake_socket), \
                    patch("native_session.select.select", side_effect=select_wait), \
                    patch("native_session.split_datagram", side_effect=lambda data: ({}, data)), \
                    patch("native_session.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("native_session.certificate_pins", side_effect=lambda *_: nullcontext()), \
                    patch("native_session.write_private"), \
                    patch("native_session.ROOT", root):
                client.run(lambda _client: None, lambda *_args: None,
                           report_name="synthetic", on_tick=tick,
                           tick_interval=0.01)

        first_tick = next(i for i, item in enumerate(order) if item[0] == "tick")
        self.assertEqual(order[:first_tick], [
            part for payload in (bytes((i,)) for i in range(70))
            for part in (("receive", payload), ("event", payload))
        ][:first_tick])
        self.assertLessEqual(received_before_tick[0], 64)
        self.assertGreater(received_before_tick[0], 0)
        self.assertEqual(client.report["datagrams_received"], 70)

    def test_readable_drain_processes_each_datagram_events_and_honors_count_limit(self):
        clock = [0.0]
        order = []
        payloads = deque(bytes((i,)) for i in range(70))
        client, fake_socket = self.make_fake_client(clock, payloads, order,
                                                    recv_seconds=0.0)
        with patch("native_session.split_datagram", side_effect=lambda data: ({}, data)), \
                patch("native_session.time.monotonic", side_effect=lambda: clock[0]):
            count = client._drain_readable(fake_socket, lambda *_: None,
                                           lambda *_: None, max_datagrams=64,
                                           max_seconds=1.0)
        self.assertEqual(count, 64)
        self.assertEqual(len(payloads), 6)
        self.assertEqual(order[:6], [
            ("receive", b"\x00"), ("event", b"\x00"),
            ("receive", b"\x01"), ("event", b"\x01"),
            ("receive", b"\x02"), ("event", b"\x02"),
        ])

    def test_readable_drain_stops_at_elapsed_time_limit(self):
        clock = [0.0]
        order = []
        payloads = deque(bytes((i,)) for i in range(20))
        client, fake_socket = self.make_fake_client(clock, payloads, order,
                                                    recv_seconds=0.001)
        with patch("native_session.split_datagram", side_effect=lambda data: ({}, data)), \
                patch("native_session.time.monotonic", side_effect=lambda: clock[0]):
            count = client._drain_readable(fake_socket, lambda *_: None,
                                           lambda *_: None, max_datagrams=64,
                                           max_seconds=0.004)
        self.assertEqual(count, 4)
        self.assertEqual(len(payloads), 16)
        self.assertEqual(clock[0], 0.004)

    def test_slow_callback_crossing_deadline_closes_before_flush(self):
        clock = [0.0]
        client, fake_socket = self.make_fake_client(clock, deque(), [])
        state = {"closed": False, "application_pending": False}

        def close(**_kwargs):
            state["closed"] = True

        def datagrams_to_send(_now):
            if state["closed"]:
                return [(b"close", client.endpoint)]
            if state["application_pending"]:
                return [(b"application", client.endpoint)]
            return []

        client.quic.close = close
        client.quic.datagrams_to_send = datagrams_to_send

        def slow_tick(_client, _now):
            state["application_pending"] = True
            clock[0] += 0.06

        def select_wait(read, write, error, timeout):
            clock[0] += timeout
            return [], [], []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/gamejoin").mkdir(parents=True)
            with patch("native_session.socket.socket", return_value=fake_socket), \
                    patch("native_session.select.select", side_effect=select_wait), \
                    patch("native_session.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("native_session.certificate_pins", side_effect=lambda *_: nullcontext()), \
                    patch("native_session.write_private"), \
                    patch("native_session.ROOT", root):
                client.run(lambda _client: None, lambda *_args: None,
                           report_name="synthetic", on_tick=slow_tick,
                           tick_interval=0.05)

        self.assertTrue(client.finished)
        self.assertTrue(client.report["duration_limit_reached"])
        self.assertEqual([packet for packet, _ in fake_socket.sent],
                         [client.header + b"close"])

    def test_transport_ack_flushes_before_slow_tick_and_tick_output_after(self):
        clock = [0.0]
        order = []
        payloads = deque([b"incoming"])
        client, fake_socket = self.make_fake_client(clock, payloads, order)
        pending_outbound = deque()

        def handle_event(event, _ready, _packet):
            order.append(("event", event))
            pending_outbound.append((b"transport-ack", client.endpoint))

        def datagrams_to_send(_now):
            return [pending_outbound.popleft()] if pending_outbound else []

        client.handle_event = handle_event
        client.quic.datagrams_to_send = datagrams_to_send
        original_sendto = fake_socket.sendto

        def sendto(data, destination):
            order.append(("send", data[len(client.header):]))
            original_sendto(data, destination)

        fake_socket.sendto = sendto

        def select_wait(read, write, error, timeout):
            if payloads:
                return [fake_socket], [], []
            clock[0] += timeout
            return [], [], []

        def tick(_client, _now):
            order.append(("tick", None))
            if not any(item == ("queued", None) for item in order):
                order.append(("queued", None))
                pending_outbound.append((b"tick-output", client.endpoint))
            clock[0] += 0.02

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/gamejoin").mkdir(parents=True)
            with patch("native_session.socket.socket", return_value=fake_socket), \
                    patch("native_session.select.select", side_effect=select_wait), \
                    patch("native_session.split_datagram", side_effect=lambda data: ({}, data)), \
                    patch("native_session.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("native_session.certificate_pins", side_effect=lambda *_: nullcontext()), \
                    patch("native_session.write_private"), \
                    patch("native_session.ROOT", root):
                client.run(lambda _client: None, lambda *_args: None,
                           report_name="synthetic", on_tick=tick,
                           tick_interval=0.01)

        self.assertLess(order.index(("send", b"transport-ack")),
                        order.index(("tick", None)))
        self.assertLess(order.index(("tick", None)),
                        order.index(("send", b"tick-output")))
        self.assertEqual([packet[len(client.header):]
                          for packet, _ in fake_socket.sent],
                         [b"transport-ack", b"tick-output"])

    def test_timer_handler_crossing_deadline_prevents_lua_tick(self):
        clock = [0.0]
        client, fake_socket = self.make_fake_client(clock, deque(), [])
        client.duration = 0.05
        state = {"timer_handled": False, "closed": False}
        ticks = []

        def get_timer():
            return None if state["timer_handled"] else 0.0

        def handle_timer(now):
            state["timer_handled"] = True
            clock[0] = 0.06

        def close(**_kwargs):
            state["closed"] = True

        def datagrams_to_send(_now):
            return [(b"close", client.endpoint)] if state["closed"] else []

        client.quic.get_timer = get_timer
        client.quic.handle_timer = handle_timer
        client.quic.close = close
        client.quic.datagrams_to_send = datagrams_to_send

        def select_wait(read, write, error, timeout):
            clock[0] += timeout
            return [], [], []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/gamejoin").mkdir(parents=True)
            with patch("native_session.socket.socket", return_value=fake_socket), \
                    patch("native_session.select.select", side_effect=select_wait), \
                    patch("native_session.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("native_session.certificate_pins", side_effect=lambda *_: nullcontext()), \
                    patch("native_session.write_private"), \
                    patch("native_session.ROOT", root):
                client.run(lambda _client: None, lambda *_args: None,
                           report_name="synthetic", on_tick=lambda *_: ticks.append(clock[0]),
                           tick_interval=0.01)

        self.assertEqual(ticks, [])
        self.assertTrue(client.finished)
        self.assertTrue(client.report["duration_limit_reached"])
        self.assertEqual([packet for packet, _ in fake_socket.sent],
                         [client.header + b"close"])

    def test_outgoing_batch_stops_at_traffic_cap_and_only_flushes_close(self):
        clock = [0.0]
        client, fake_socket = self.make_fake_client(clock, deque(), [])
        state = {"closed": False, "app_batch_pending": True}

        def close(**_kwargs):
            state["closed"] = True

        def datagrams_to_send(_now):
            if state["closed"]:
                return [(b"close", client.endpoint)]
            if state["app_batch_pending"]:
                state["app_batch_pending"] = False
                return [(f"app-{i}".encode(), client.endpoint) for i in range(5)]
            return []

        client.quic.close = close
        client.quic.datagrams_to_send = datagrams_to_send
        client.report["datagrams_sent"] = 59998

        def select_wait(read, write, error, timeout):
            clock[0] += timeout
            return [], [], []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/gamejoin").mkdir(parents=True)
            with patch("native_session.socket.socket", return_value=fake_socket), \
                    patch("native_session.select.select", side_effect=select_wait), \
                    patch("native_session.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("native_session.certificate_pins", side_effect=lambda *_: nullcontext()), \
                    patch("native_session.write_private"), \
                    patch("native_session.ROOT", root):
                client.run(lambda _client: None, lambda *_args: None,
                           report_name="synthetic")

        sent = [packet[len(client.header):] for packet, _ in fake_socket.sent]
        self.assertEqual(sent, [b"app-0", b"app-1", b"close"])
        self.assertEqual(client.report["datagrams_sent"], 60001)
        self.assertTrue(client.report["traffic_limit_reached"])
        self.assertTrue(client.finished)


if __name__ == "__main__":
    unittest.main()
