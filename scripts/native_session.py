"""Native RUPP/QUIC/WebTransport session for the selected place.

Transport authentication reuses the already verified allocation and certificate
pinning path. Game handlers receive complete channel frames, not UDP fragments.
Application payloads are private; public reports contain only message IDs,
lengths, channel numbers, and connection outcomes. Unlimited sessions retain
a bounded tail of diagnostics instead of their entire traffic history.
"""
import base64
from collections import deque
from datetime import datetime, timezone
import json
import logging
import math
import select
import socket
import ssl
import sys
import time
import uuid

from aioquic.h3.connection import H3Connection
from aioquic.h3.events import HeadersReceived, WebTransportStreamDataReceived, DatagramReceived
from aioquic.quic.configuration import QuicConfiguration
from datagram_delivery import DatagramTrackingQuicConnection as QuicConnection
from aioquic.quic.events import ConnectionTerminated, HandshakeCompleted, PingAcknowledged
from session_diagnostics import current, NULL, exit_reason, public_state

from channels import reliable_header, parse_reliable_header
from game_wire import CONTROL_CHANNEL, FrameDecoder, frame
from join_allocation import write_private
from probe_transport import allocation, certificate_pins
from roblox_session import ROOT, SessionError
from rupp import client_header, split_datagram
from unreliable import control_open, parse_control_open, encode_datagram, parse_datagram
from ping_telemetry import SessionPingTelemetry


class NativeSession:
    diagnostics = NULL

    def __init__(self, duration=15, capabilities=0):
        self.diagnostics = current()
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("Session duration must be nonnegative; 0 means no time limit")
        self.duration = duration
        if capabilities not in (0, 0x100000):
            raise ValueError("An unimplemented transport capability was requested")
        self.capabilities = capabilities
        self.place, self.endpoint, self.backend, self.token, self.pins = allocation()
        self.header = client_header(self.token, self.backend, self.endpoint[1])
        self.quic = QuicConnection(configuration=QuicConfiguration(
            is_client=True, alpn_protocols=["h3"], verify_mode=ssl.CERT_REQUIRED,
            max_datagram_frame_size=65536, idle_timeout=15,
            max_data=16 * 1024 * 1024, max_stream_data=8 * 1024 * 1024))
        self.http = None
        self.connect_stream = None
        self.outgoing = {}
        self.incoming = {}
        self.unreliable_incoming = {}
        self.unreliable_outgoing = {}
        self.next_wire_id = 2
        self.capture = deque() if duration == 0 else []
        self.capture_bytes = 0
        self.finished = False
        self.started = None
        self.ping_telemetry = SessionPingTelemetry(
            transport='quic_without_raknet', capabilities=self.capabilities)
        self._received_datagram_at_ns = None
        self.report = {
            "run_id": uuid.uuid4().hex,
            "checked_at": datetime.now(timezone.utc).isoformat(), "place_id": self.place,
            "client_capabilities": format(capabilities, "016x"),
            "certificate_pin_verified": False, "quic_handshake_completed": False,
            "webtransport_session_established": False, "early_auth_sent": False,
            "game_account_accepted": False, "player_spawned": False,
            "walk_seconds_verified": 0, "datagrams_sent": 0, "datagrams_received": 0,
            "bytes_received": 0, "token_rotations": 0,
            "channels_sent": [], "channels_received": [],
            "messages": deque(maxlen=4096) if duration == 0 else [],
        }
        # Optional in-process finalizer for component state that must be
        # terminal before the single public/history snapshot is persisted.
        self.report_finalizer = None
        if duration == 0:
            self.report['capture_tail_only'] = True

    def capture_entry(self, entry):
        self.capture.append(entry)
        if self.duration == 0:
            # Keep diagnostics bounded without disconnecting long-lived sessions.
            self.capture_bytes += len(entry.get('data_base64', '')) + 256
            while self.capture_bytes > 16 * 1024 * 1024 or len(self.capture) > 4096:
                removed = self.capture.popleft()
                self.capture_bytes -= len(removed.get('data_base64', '')) + 256
                self.report['capture_entries_evicted'] = self.report.get('capture_entries_evicted', 0) + 1

    def open_channel(self, application, channel):
        key = (application, channel)
        if key not in self.outgoing:
            stream = self.http.create_webtransport_stream(self.connect_stream, is_unidirectional=True)
            self.outgoing[key] = stream
            self.quic.send_stream_data(stream, reliable_header(*key))
            self.report["channels_sent"].append({"application": application, "channel": channel, "stream_id": stream})
        return self.outgoing[key]

    def record(self, direction, application, channel, payload):
        elapsed = round(time.monotonic() - self.started, 6)
        self.diagnostics.emit('application.frame', verbose=True, direction=direction,
            application=application, channel=channel, bytes=len(payload),
            message_id=payload[0] if payload else None, session_s=elapsed)
        self.capture_entry({"direction": direction, "application": application, "channel": channel,
                             "seconds": elapsed, "data_base64": base64.b64encode(payload).decode()})
        self.report["messages"].append({"direction": direction, "application": application, "channel": channel,
                                        "seconds": elapsed, "bytes": len(payload),
                                        "message_id": payload[0] if payload else None})

    def send(self, channel, payload, application=4):
        stream = self.open_channel(application, channel)
        self.quic.send_stream_data(stream, frame(payload))
        self.record("sent", application, channel, payload)

    def close(self, reason="Session complete"):
        # Call sites can pass arbitrary text; expose its source location rather
        # than copying it into the shareable log.
        caller=sys._getframe(1)
        self.diagnostics.emit('close.requested', reason_length=len(reason),
            caller={'file':caller.f_code.co_filename.replace('\\','/').rsplit('/',1)[-1],
                    'line':caller.f_lineno,'function':caller.f_code.co_name})
        del caller
        self.quic.close(reason_phrase=reason)
        self.finished = True
        self.report["local_close_requested"] = True

    def open_unreliable_channel(self, application, channel):
        key = (application, channel)
        if key not in self.unreliable_outgoing:
            wire_id = self.next_wire_id
            self.next_wire_id += 2
            self.send(CONTROL_CHANNEL, control_open(application, channel, wire_id), application)
            self.unreliable_outgoing[key] = {'wire_id': wire_id, 'sequence': 0}
            self.report['channels_sent'].append({'application': application, 'channel': channel,
                                                'wire_id': wire_id, 'unreliable': True})
        return self.unreliable_outgoing[key]

    def send_unreliable(self, channel, payload, application=4, *, on_delivery=None):
        state = self.open_unreliable_channel(application, channel)
        state['sequence'] += 1
        data = encode_datagram(state['wire_id'], state['sequence'], payload)
        if on_delivery is None:
            self.http.send_datagram(self.connect_stream, data)
        else:
            with self.quic.observe_datagram_delivery(on_delivery):
                self.http.send_datagram(self.connect_stream, data)
        self.record('sent', application, channel, payload)

    def receive_stream(self, event, on_packet):
        if event.session_id != self.connect_stream:
            raise SessionError("Peer sent data for an unexpected WebTransport session")
        state = self.incoming.setdefault(event.stream_id, {"header": bytearray(), "channel": None, "decoder": FrameDecoder()})
        data = event.data
        if state["channel"] is None:
            needed = 7 - len(state["header"])
            state["header"].extend(data[:needed])
            data = data[needed:]
            if len(state["header"]) < 7:
                if event.stream_ended:
                    raise SessionError("Peer ended an incomplete channel header")
                return
            state["channel"] = parse_reliable_header(state["header"])
            app, channel = state["channel"]
            self.report["channels_received"].append({"application": app, "channel": channel, "stream_id": event.stream_id})
        app, channel = state["channel"]
        payloads = state["decoder"].feed(data)
        frame_ready_ns = time.monotonic_ns()
        for payload in payloads:
            self.record("received", app, channel, payload)
            if channel == CONTROL_CHANNEL:
                if payload[:1] == b'\x02':
                    app_id, channel_id, wire_id = parse_control_open(payload)
                    self.unreliable_incoming[wire_id] = (app_id, channel_id)
                elif payload and payload[0] == 1 and len(payload) >= 10 and payload[1] >= 8:
                    self.report["application_close"] = {
                        "application": app, "reason_class": int.from_bytes(payload[2:6], "big"),
                        "reason_code": int.from_bytes(payload[6:10], "big")}
                    self.report['server_application_close_at_seconds'] = round(time.monotonic() - self.started, 3)
                    self.diagnostics.emit('server.application_close', **self.report['application_close'],
                        session_s=self.report['server_application_close_at_seconds'])
                    self.close("Server closed game application")
            else:
                self.dispatch_packet(on_packet, app, channel, payload, frame_ready_ns=frame_ready_ns)
        if event.stream_ended:
            state["decoder"].finish()

    def dispatch_packet(self, on_packet, application, channel, payload, *, frame_ready_ns):
        telemetry = getattr(self, 'ping_telemetry', None)
        if telemetry is not None:
            telemetry.observe_dispatch(application, channel, payload,
                                       received_ns=self._received_datagram_at_ns,
                                       frame_ready_ns=frame_ready_ns)
        with self.diagnostics.stage('game.packet', application=application, channel=channel,
                                    message_id=payload[0] if payload else None, bytes=len(payload)):
            on_packet(self, application, channel, payload)

    def handle_event(self, event, on_ready, on_packet):
        if isinstance(event, HandshakeCompleted):
            self.report["quic_handshake_completed"] = True
            self.diagnostics.emit('transport.handshake_completed')
            self.http = H3Connection(self.quic, enable_webtransport=True)
            self.connect_stream = self.quic.get_next_available_stream_id()
            caps = format(self.capabilities, "016x").encode("ascii")
            self.http.send_headers(self.connect_stream, [
                (b":method", b"CONNECT"), (b":scheme", b"https"),
                (b":authority", (self.endpoint[0] + ":" + str(self.endpoint[1])).encode()),
                (b":path", b"/wt?X-Rbx-Capabilities=" + caps), (b":protocol", b"webtransport-h3"),
                (b"x-rbx-capabilities", caps)])
        if isinstance(event, PingAcknowledged):
            self.report['quic_keepalives_acknowledged'] = self.report.get('quic_keepalives_acknowledged',0)+1
            self.report['last_quic_ack_at_seconds'] = round(time.monotonic()-self.started,3)
            self.diagnostics.emit('transport.keepalive_acknowledged', ping_id=event.uid)
        if isinstance(event, ConnectionTerminated):
            self.report["termination"] = {"error_code": event.error_code, "frame_type": event.frame_type,
                                           "reason_length": len(event.reason_phrase)}
            # Preserve known transport diagnostics without publishing arbitrary
            # peer-supplied reason strings, which can contain session data.
            if event.reason_phrase == "Idle timeout":
                self.report["termination"]["reason"] = "Idle timeout"
            self.diagnostics.emit('transport.terminated', **self.report['termination'])
            self.finished = True
        if self.http is None:
            return
        for received in self.http.handle_event(event):
            if isinstance(received, HeadersReceived) and received.stream_id == self.connect_stream:
                headers = dict(received.headers)
                status, caps = headers.get(b":status", b""), headers.get(b"x-rbx-capabilities", b"")
                valid_caps = len(caps) == 16 and all(c in b"0123456789abcdefABCDEF" for c in caps)
                self.report["connect_http_status"] = int(status) if status.isdigit() else None
                if valid_caps:
                    self.report["server_capabilities"] = caps.decode("ascii")
                ready = self.report["certificate_pin_verified"] and status == b"200" and valid_caps and not received.stream_ended
                if ready and not self.report["webtransport_session_established"]:
                    self.report["webtransport_session_established"] = True
                    self.send(CONTROL_CHANNEL, b"\0\0", application=0)
                    self.send(CONTROL_CHANNEL, b"\0\0", application=4)
                    self.diagnostics.emit('transport.webtransport_ready', http_status=200)
                    with self.diagnostics.stage('game.ready'):
                        on_ready(self)
                elif not ready:
                    self.diagnostics.emit('transport.webtransport_rejected',
                        http_status=self.report['connect_http_status'],valid_capabilities=valid_caps,
                        certificate_pin_verified=self.report['certificate_pin_verified'],stream_ended=received.stream_ended)
                    self.close("WebTransport was not established")
            elif isinstance(received, WebTransportStreamDataReceived):
                self.receive_stream(received, on_packet)
            elif isinstance(received, DatagramReceived):
                self.capture_entry({"direction": "received_datagram", "bytes": len(received.data),
                                     "seconds": round(time.monotonic() - self.started, 6),
                                     "data_base64": base64.b64encode(received.data).decode()})
                self.report["application_datagrams"] = self.report.get("application_datagrams", 0) + 1
                datagram = parse_datagram(received.data)
                key = self.unreliable_incoming.get(datagram['wire_id'])
                if key is not None and datagram['complete']:
                    app, channel = key
                    frame_ready_ns = time.monotonic_ns()
                    self.record('received', app, channel, datagram['payload'])
                    self.dispatch_packet(on_packet, app, channel, datagram['payload'],
                                         frame_ready_ns=frame_ready_ns)
                else:
                    self.report['unhandled_unreliable_datagrams'] = self.report.get('unhandled_unreliable_datagrams', 0) + 1

    def _enforce_limits(self, deadline):
        if self.finished:
            return
        if time.monotonic() >= deadline:
            self.report["duration_limit_reached"] = True
            self.close("Bounded session complete")
        elif self.duration and (self.report["datagrams_sent"] >= 60000 or
                                self.report["bytes_received"] >= 256 * 1024 * 1024):
            self.report["traffic_limit_reached"] = True
            self.close("Bounded traffic limit")

    def _drain_events(self, on_ready, on_packet):
        while not self.finished and (event := self.quic.next_event()) is not None:
            self.handle_event(event, on_ready, on_packet)

    def _flush_datagrams(self, sock, deadline):
        closing = self.finished
        for data, destination in self.quic.datagrams_to_send(time.monotonic()):
            if not closing:
                self._enforce_limits(deadline)
                if self.finished:
                    # Discard the already-produced application batch. Ask
                    # QUIC again so only its newly queued close is emitted.
                    self._flush_datagrams(sock, deadline)
                    return
            if destination != self.endpoint:
                raise SessionError("Session refused an unallocated destination")
            sock.sendto(self.header + data, self.endpoint)
            self.report["datagrams_sent"] += 1
            self.report['last_udp_send_at_seconds'] = round(time.monotonic()-self.started,3)
            self.diagnostics.emit('udp.sent',verbose=True,bytes=len(self.header)+len(data),
                                  datagram_number=self.report['datagrams_sent'])

    def _drain_readable(self, sock, on_ready, on_packet, *, max_datagrams=64,
                        max_seconds=0.004, deadline=math.inf):
        """Service queued UDP without letting an input burst starve ticks/timers."""
        batch_deadline = time.monotonic() + max_seconds
        count = 0
        while count < max_datagrams and time.monotonic() < batch_deadline:
            self._enforce_limits(deadline)
            if self.finished:
                break
            try:
                data, _source = sock.recvfrom(65536)
            except BlockingIOError:
                break
            except InterruptedError:
                continue
            self._received_datagram_at_ns = time.monotonic_ns()
            self.report["datagrams_received"] += 1
            self.report["bytes_received"] += len(data)
            self.report['last_udp_receive_at_seconds'] = round(time.monotonic()-self.started,3)
            self.diagnostics.emit('udp.received',verbose=True,bytes=len(data),
                                  datagram_number=self.report['datagrams_received'])
            count += 1
            routing, payload = split_datagram(data)
            if routing:
                for kind, value in routing["fields"]:
                    if kind == 1 and len(value) == 17 and value[0] == 2 and value[1:] != self.token:
                        self.token = value[1:]
                        self.header = client_header(self.token, self.backend, self.endpoint[1], token_kind=2)
                        self.report["token_rotations"] += 1
            # Direct server return may use another source address.
            # The issued certificate pin and QUIC authenticate it.
            self.quic.receive_datagram(payload, self.endpoint, now=time.monotonic())
            # Dispatch before receiving the next datagram, preserving receive
            # timestamps and allowing control changes to affect later packets.
            self._drain_events(on_ready, on_packet)
        return count

    def run(self, on_ready, on_packet, report_name="game-session", *, on_tick=None, tick_interval=0.05):
        if on_tick is not None and (not math.isfinite(tick_interval) or not 0.01 <= tick_interval <= 1):
            raise ValueError("Tick interval must be between 0.01 and 1 seconds")
        logging.getLogger("quic").disabled = True
        self.started = time.monotonic()
        self.diagnostics.emit('transport.start', duration_s=self.duration,
            unlimited=self.duration==0, quic_idle_timeout_s=15, keepalive_interval_s=2,
            tick_interval_s=tick_interval)
        next_diagnostics = self.started
        scheduler = self.report['local_scheduler'] = {
            'tick_count': 0, 'tick_seconds_total': 0.,
            'tick_seconds_max': 0., 'ticks_over_250ms': 0,
            'tick_deadlines_skipped': 0}
        deadline = self.started + self.duration if self.duration else math.inf
        next_ping, ping_id = self.started + 2, 0
        next_tick = self.started if on_tick is not None else deadline
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", 0))
        sock.setblocking(False)
        try:
            with certificate_pins(self.pins, self.report):
                self.quic.connect(self.endpoint, now=self.started)
                while True:
                    if time.monotonic() >= next_diagnostics:
                        self.report['session_age_seconds'] = round(time.monotonic()-self.started,3)
                        self.diagnostics.update(self.report)
                        next_diagnostics = time.monotonic()+1
                    self._enforce_limits(deadline)
                    if not self.finished:
                        self._drain_readable(sock, on_ready, on_packet, deadline=deadline)
                    now = time.monotonic()
                    self._enforce_limits(deadline)
                    timer = self.quic.get_timer()
                    if timer is not None and now >= timer and not self.finished:
                        self.quic.handle_timer(now=now)
                        self._drain_events(on_ready, on_packet)
                        now = time.monotonic()
                        self._enforce_limits(deadline)
                    if now >= next_ping:
                        if self.report["quic_handshake_completed"] and not self.finished:
                            self.quic.send_ping(ping_id)
                            self.report['quic_keepalives_sent'] = ping_id+1
                            self.diagnostics.emit('transport.keepalive_sent',ping_id=ping_id)
                            ping_id += 1
                        next_ping = now + 2
                    # Flush transport control output before running application
                    # work. A slow game tick must not hold QUIC ACKs or ping
                    # replies that were made ready while draining the socket.
                    # Keep the post-tick flush below for packets queued by the
                    # callback itself.
                    finished_before_preflush = self.finished
                    if not finished_before_preflush:
                        self._flush_datagrams(sock, deadline)
                    if self.finished:
                        if finished_before_preflush:
                            self._flush_datagrams(sock, deadline)
                        break
                    if on_tick is not None and now >= next_tick and not self.finished:
                        with self.diagnostics.stage('game.tick'):
                            on_tick(self, now)
                        completed_at = time.monotonic()
                        elapsed = max(0., completed_at-now)
                        scheduler['tick_count'] += 1
                        scheduler['tick_seconds_total'] = round(scheduler['tick_seconds_total']+elapsed, 6)
                        scheduler['tick_seconds_max'] = round(max(scheduler['tick_seconds_max'], elapsed), 6)
                        scheduler['ticks_over_250ms'] += int(elapsed > .25)
                        # Keep a fixed cadence from the prior deadline. If this
                        # callback ran past one or more deadlines, skip those
                        # periods instead of issuing catch-up callbacks.
                        next_tick += tick_interval
                        if next_tick < completed_at - 1e-12:
                            skipped = math.floor((completed_at-next_tick) / tick_interval) + 1
                            scheduler['tick_deadlines_skipped'] += skipped
                            next_tick += skipped * tick_interval
                    self._enforce_limits(deadline)
                    self._flush_datagrams(sock, deadline)
                    if self.finished:
                        break
                    timer = self.quic.get_timer()
                    wait = max(0, min(deadline, next_ping, next_tick,
                                      timer if timer is not None else deadline) - time.monotonic())
                    if select.select([sock], [], [], wait)[0]:
                        self._drain_readable(sock, on_ready, on_packet, deadline=deadline)
                    elif timer is not None and time.monotonic() >= timer:
                        self.quic.handle_timer(now=time.monotonic())
                    self._drain_events(on_ready, on_packet)
        except KeyboardInterrupt:
            self.report['interrupted'] = True
            self.diagnostics.emit('session.interrupted')
            self.close('User interrupted session')
            raise
        except Exception as error:
            self.report["error_type"] = type(error).__name__
            self.diagnostics.exception('transport.error',error)
            self.close("Local session processing stopped")
            for data, destination in self.quic.datagrams_to_send(time.monotonic()):
                if destination == self.endpoint:
                    sock.sendto(self.header + data, self.endpoint)
            raise
        finally:
            sock.close()
            self.report["elapsed_seconds"] = round(time.monotonic() - self.started, 3)
            self.report['disconnect_category'] = exit_reason(self.report)
            self.diagnostics.update(self.report)
            self.diagnostics.emit('session.ended', reason=self.report['disconnect_category'],
                                  state=public_state(self.report))
            print(json.dumps({'disconnect_category':self.report['disconnect_category'],
                              'elapsed_seconds':self.report['elapsed_seconds']}),flush=True)
            delivery_report = getattr(self.quic, 'datagram_delivery_report', None)
            if callable(delivery_report):
                self.report['tracked_datagram_delivery'] = delivery_report()
            if 'application_ping_session_telemetry' in self.report:
                self.report['application_ping_session_telemetry'] = self.ping_telemetry.public_report()
            finalizer = getattr(self, 'report_finalizer', None)
            if callable(finalizer):
                try:
                    finalizer(self.report)
                except Exception as error:
                    # A report hook must not prevent the normal durable
                    # session record from being written during cleanup.
                    self.report['report_finalizer_error_type'] = type(error).__name__
            capture = list(self.capture) if self.duration == 0 else self.capture
            if self.duration == 0:
                self.report['messages'] = list(self.report['messages'])
            write_private(ROOT / "secrets" / (report_name + ".json"), capture)
            archive = report_name + "-" + self.report["run_id"] + ".json"
            write_private(ROOT / "secrets" / archive, capture)
            public = ROOT / "outputs/gamejoin" / (report_name + ".json")
            self.report["private_capture"] = "secrets/" + archive
            public.write_text(json.dumps(self.report, indent=2) + "\n")
            with (ROOT / "outputs/gamejoin/session-history.jsonl").open("a") as history:
                history.write(json.dumps(self.report) + "\n")
        return self.report
