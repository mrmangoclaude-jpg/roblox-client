#!/usr/bin/env python3
"""Bounded QUIC handshake probe using the alt's normal HTTPS join allocation.

No cookie is sent over UDP. No game authentication or replication is attempted.
Certificate authentication uses the certificate hashes delivered by Roblox's
verified HTTPS join response. TLS CertificateVerify remains enabled.
"""
import argparse
import base64
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import io
import json
import logging
from pathlib import Path
import select
import socket
import ssl
import stat
import time
from urllib.parse import unquote

from aioquic import tls
from aioquic.h3.connection import H3Connection
from aioquic.h3.events import HeadersReceived, DataReceived, WebTransportStreamDataReceived, DatagramReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.events import ConnectionTerminated, HandshakeCompleted, ProtocolNegotiated
from cryptography.hazmat.primitives.serialization import Encoding

from roblox_session import ROOT, SessionError
from rupp import client_header, split_datagram
from join_allocation import write_private, main as refresh_allocation
from channels import reliable_header, parse_reliable_header


def validate_pinned_certificate(certificate, pins, now=None):
    now = now or datetime.now(timezone.utc)
    if not certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc:
        raise tls.AlertCertificateExpired("Server certificate is outside its validity period")
    digest = hashlib.sha256(certificate.public_bytes(Encoding.DER)).digest()
    if not any(hmac.compare_digest(digest, pin) for pin in pins):
        raise tls.AlertBadCertificate("Server certificate does not match the issued certificate hashes")


@contextmanager
def certificate_pins(pins, report):
    # aioquic 1.7.1 has no public pin callback. Replace only the CA/hostname
    # validator for this single-threaded probe, preserving the TLS 1.3
    # CertificateVerify signature check and handshake transcript checks.
    original = tls.verify_certificate

    def verify(certificate, **kwargs):
        validate_pinned_certificate(certificate, pins)
        report["certificate_pin_verified"] = True

    tls.verify_certificate = verify
    try:
        yield
    finally:
        tls.verify_certificate = original


def allocation(*, target=None):
    from platform_files import read_private
    path = ROOT / "secrets/last-join.json"
    # POSIX mode bits are meaningless on Windows (always 0o666); read_private
    # checks the owner/DACL there and the mode bits elsewhere.
    try:
        saved = json.loads(read_private(path, 4 * 1024 * 1024))
    except (OSError, ValueError):
        raise SessionError("Join response must be a regular owner-only file") from None
    if target is None:
        target = json.loads((ROOT / "outputs/gamejoin/target-selection.json").read_text())
    elif isinstance(target, dict):
        target = target.copy()
    else:
        raise SessionError('Explicit allocation target must be an object')
    if (target.get("selection") not in ('alt_owned_public_place', 'user_selected_place', 'user_selected_private_server')
        or target.get('is_playable') is not True or saved["place_id"] != target["place_id"]):
        raise SessionError("Allocation does not match the verified selected place")
    if target['selection'] == 'user_selected_private_server':
        invite = json.loads((ROOT / 'secrets/private-server-target.json').read_text())
        if (saved.get('selection') != target['selection']
                or saved.get('private_server_invite_id') != invite.get('privateServerId')):
            raise SessionError('Allocation does not match the selected private server invite')
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(saved["received_at"])).total_seconds()
    if not 0 <= age < 600:
        raise SessionError("Refresh the normal join allocation before probing")
    if saved["body"].get("status") != 2:
        raise SessionError("Join allocation is not ready")
    join = saved["body"]["joinScript"]
    config = json.loads(unquote(join["NetStackConfig"]))
    # 104c89c44 applies the NetStackPort override to both endpoint structs.
    proxy = join["UdmuxEndpoints"][0]
    address = proxy.get("Address") or proxy.get("address")
    backend = join["MachineAddress"]
    if not ipaddress.ip_address(address).is_global or not ipaddress.ip_address(backend).is_private:
        raise SessionError("Unexpected allocation endpoint type")
    port = int(config["port"])
    if port != int(join["NetStackPort"]) or not 1 <= port <= 65535:
        raise SessionError("Inconsistent allocated transport port")
    token = base64.b64decode(join["NetStackTokenValue"], validate=True)
    pins = [base64.b64decode(value, validate=True) for value in config["certHashes"]]
    if not pins or any(len(pin) != 32 for pin in pins):
        raise SessionError("Missing or invalid server-issued certificate hashes")
    return saved["place_id"], (address, port), backend, token, pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Request a fresh normal join allocation first")
    parser.add_argument("--webtransport", action="store_true", help="Test a native extended CONNECT after TLS")
    parser.add_argument("--observe", action="store_true", help="Observe initial session streams for two seconds")
    parser.add_argument("--channel", action="store_true", help="Open game application 4 reliable channel 0")
    args = parser.parse_args()
    if args.observe and not args.webtransport:
        parser.error("--observe requires --webtransport")
    if args.channel and not args.observe:
        parser.error("--channel requires --webtransport --observe")
    if args.refresh:
        with redirect_stdout(io.StringIO()):
            ready = refresh_allocation()
        if ready != 0:
            raise SessionError("Roblox did not return a ready allocation; see outputs/gamejoin/allocation-check.json")
    logging.getLogger("quic").disabled = True  # arbitrary peer strings never go to logs
    place_id, endpoint, backend, token, pins = allocation()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "place_id": place_id,
              "transport": "RUPP-wrapped QUIC with h3 ALPN", "certificate_pin_verified": False,
              "quic_handshake_completed": False, "webtransport_session_established": False,
              "gameplay_joined": False, "datagrams_sent": 0, "datagrams_received": 0,
              "received_shapes": [], "events": [], "token_rotations": 0,
              "probe_mode": "channel" if args.channel else "observation" if args.observe else "webtransport" if args.webtransport else "handshake"}
    header = client_header(token, backend, endpoint[1])
    config = QuicConfiguration(is_client=True, alpn_protocols=["h3"], verify_mode=ssl.CERT_REQUIRED,
                               max_datagram_frame_size=65536, idle_timeout=8, max_data=262144,
                               max_stream_data=65536)
    quic = QuicConnection(configuration=config)
    http = None
    connect_stream = None
    observed_streams = []
    observe_until = None
    channel_stream = None
    stream_buffers = {}
    then = time.monotonic()
    deadline = then + 10
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.setblocking(False)
    try:
        with certificate_pins(pins, report):
            quic.connect(endpoint, now=then)
            finished = False
            while time.monotonic() < deadline and report["datagrams_sent"] < 24 and report["datagrams_received"] < 64:
                now = time.monotonic()
                if observe_until is not None and now >= observe_until:
                    quic.close(reason_phrase="Research session observation complete")
                    finished = True
                for data, destination in quic.datagrams_to_send(now):
                    if destination != endpoint:
                        raise SessionError("Probe refused an unallocated destination")
                    if report["datagrams_sent"] >= 24:
                        break
                    sock.sendto(header + data, endpoint)
                    report["datagrams_sent"] += 1
                if finished:
                    break
                timer = quic.get_timer()
                wait = max(0, min(deadline, timer if timer is not None else deadline,
                                  observe_until if observe_until is not None else deadline) - time.monotonic())
                if select.select([sock], [], [], wait)[0]:
                    data, source = sock.recvfrom(65536)
                    report["datagrams_received"] += 1
                    try:
                        routing, payload = split_datagram(data)
                    except ValueError:
                        report["received_shapes"].append({"bytes": len(data), "invalid_routing_header": True})
                        continue
                    shape = {"bytes": len(data), "payload_bytes": len(payload), "from_allocated_ip": source[0] == endpoint[0]}
                    if routing:
                        shape["routing"] = {key: routing[key] for key in ("kind", "flags", "size")}
                        shape["routing"]["tlvs"] = [{"type": k, "bytes": len(v)} for k, v in routing["fields"]]
                        for field_type, value in routing["fields"]:
                            if field_type == 1 and len(value) == 17:
                                shape["routing"]["token_kind"] = value[0]
                                if value[0] == 2 and value[1:] != token:
                                    token = value[1:]
                                    header = client_header(token, backend, endpoint[1], token_kind=2)
                                    report["token_rotations"] += 1
                    report["received_shapes"].append(shape)
                    # A DSR reply can arrive from another source. Treat the
                    # allocated route as the logical peer; QUIC cryptographic
                    # validation and the issued certificate pin authenticate it.
                    quic.receive_datagram(payload, endpoint, now=time.monotonic())
                else:
                    if timer is not None and time.monotonic() >= timer:
                        quic.handle_timer(now=time.monotonic())
                while (event := quic.next_event()) is not None:
                    report["events"].append(type(event).__name__)
                    if isinstance(event, ProtocolNegotiated):
                        report["alpn"] = event.alpn_protocol if event.alpn_protocol == "h3" else "unexpected"
                    if isinstance(event, HandshakeCompleted):
                        report["quic_handshake_completed"] = True
                        if args.webtransport:
                            http = H3Connection(quic, enable_webtransport=True)
                            connect_stream = quic.get_next_available_stream_id()
                            # No optional Roblox capability is implemented by
                            # this probe, so advertise zero instead of echoing
                            # the server's capability set as if it were ours.
                            caps = b"0000000000000000"
                            http.send_headers(connect_stream, [
                                (b":method", b"CONNECT"), (b":scheme", b"https"),
                                (b":authority", (endpoint[0] + ":" + str(endpoint[1])).encode()),
                                (b":path", b"/wt?X-Rbx-Capabilities=" + caps),
                                (b":protocol", b"webtransport-h3"),
                                (b"x-rbx-capabilities", caps),
                            ])
                            report["connect_sent"] = True
                        else:
                            quic.close(reason_phrase="Research handshake probe complete")
                            finished = True
                    if isinstance(event, ConnectionTerminated):
                        report["termination"] = {"error_code": event.error_code, "frame_type": event.frame_type,
                                                 "reason_length": len(event.reason_phrase)}
                        finished = True
                    if http is not None:
                        for http_event in http.handle_event(event):
                            report["events"].append(type(http_event).__name__)
                            if isinstance(http_event, HeadersReceived) and http_event.stream_id == connect_stream:
                                headers = dict(http_event.headers)
                                status = headers.get(b":status", b"")
                                report["connect_http_status"] = int(status) if status.isdigit() else None
                                report["response_header_names"] = [key.decode("ascii", "replace") for key in headers]
                                server_caps = headers.get(b"x-rbx-capabilities", b"")
                                report["server_capabilities_valid"] = len(server_caps) == 16 and all(c in b"0123456789abcdefABCDEF" for c in server_caps)
                                report["webtransport_session_established"] = (report["certificate_pin_verified"]
                                    and status == b"200" and not http_event.stream_ended and report["server_capabilities_valid"])
                                if args.observe and report["webtransport_session_established"]:
                                    observe_until = time.monotonic() + 2
                                    if args.channel:
                                        channel_stream = http.create_webtransport_stream(connect_stream, is_unidirectional=False)
                                        quic.send_stream_data(channel_stream, reliable_header(4, 0))
                                        report["channel_open_sent"] = {"application": 4, "channel": 0, "stream_id": channel_stream}
                                else:
                                    quic.close(reason_phrase="Research WebTransport probe complete")
                                    finished = True
                            if isinstance(http_event, DataReceived):
                                report["http_response_data_bytes"] = report.get("http_response_data_bytes", 0) + len(http_event.data)
                            if isinstance(http_event, (WebTransportStreamDataReceived, DatagramReceived)):
                                observed_streams.append({"event": type(http_event).__name__,
                                    "stream_id": http_event.stream_id,
                                    "session_id": getattr(http_event, "session_id", connect_stream),
                                    "ended": getattr(http_event, "stream_ended", False),
                                    "data_base64": base64.b64encode(http_event.data).decode()})
                                report.setdefault("application_data", []).append({"event": type(http_event).__name__,
                                    "stream_id": http_event.stream_id, "bytes": len(http_event.data)})
                                if isinstance(http_event, WebTransportStreamDataReceived):
                                    buffer = stream_buffers.setdefault(http_event.stream_id, bytearray())
                                    buffer.extend(http_event.data)
                                    if len(buffer) >= 7 and len(buffer) - len(http_event.data) < 7:
                                        try:
                                            app, channel = parse_reliable_header(buffer)
                                        except ValueError:
                                            report.setdefault("unparsed_stream_headers", []).append(http_event.stream_id)
                                        else:
                                            report.setdefault("received_channel_headers", []).append({"stream_id": http_event.stream_id,
                                                "application": app, "channel": channel})
                                            if http_event.stream_id == channel_stream and (app, channel) == (4, 0):
                                                report["channel_header_echo_received"] = True
            report["elapsed_seconds"] = round(time.monotonic() - then, 3)
    finally:
        sock.close()
    if args.observe:
        write_private(ROOT / "secrets" / ("channel-observation.json" if args.channel else "session-observation.json"), observed_streams)
    filename = ("channel-observation.json" if args.channel else "session-observation.json" if args.observe
                else "webtransport-probe.json" if args.webtransport else "transport-probe.json")
    path = ROOT / "outputs/gamejoin" / filename
    path.write_text(json.dumps(report, indent=2) + "\n")
    with (ROOT / "outputs/gamejoin/probe-history.jsonl").open("a") as output:
        output.write(json.dumps(report) + "\n")
    # Detailed packet shapes are in the report; the CLI prints a compact result.
    summary_keys = ("checked_at", "place_id", "probe_mode", "certificate_pin_verified", "quic_handshake_completed",
                    "webtransport_session_established", "connect_http_status", "gameplay_joined", "datagrams_sent",
                    "datagrams_received", "received_channel_headers", "termination", "elapsed_seconds")
    print(json.dumps({**{key: report[key] for key in summary_keys if key in report}, "report": str(path)}, indent=2))
    return 0 if report["webtransport_session_established" if args.webtransport else "quic_handshake_completed"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SessionError as error:
        print(json.dumps({"error": str(error)}))
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1)
