#!/usr/bin/env python3
"""Exercise the recovered normal game-handshake stages with the authorized alt."""
import argparse
from contextlib import nullcontext, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import time

if sys.pycache_prefix is None:
    sys.pycache_prefix = str(Path.home()/'.cache/roblox-client-research/python')
os.environ.setdefault('PYTHONPYCACHEPREFIX', sys.pycache_prefix)
if os.name == 'nt':
    import signal
    signal.signal(signal.SIGBREAK, signal.default_int_handler)

from game_wire import CONTROL_CHANNEL, issued_early_auth, feature_configuration, protocol_sync
from join_allocation import main as refresh_allocation, write_private
from native_session import NativeSession
from login_packets import ticket_packet, verification_packet, server_id_packet
from roblox_session import REPO_ROOT, ROOT, SessionError
from world_replication import World
from world_schema import parse_schema
from isr_replication import InstanceStateReceiver
from replication_out import streaming_ready, MarkerQueue
from ping_responder import SessionPingHandler
from dummy_sync import APPLICATION as CLOCK_APPLICATION, REQUEST_CHANNEL as CLOCK_CHANNEL, TimeSyncProbe
from replication_rpc import FrameworkInitRpc
from bytecode_check import parse_program_check, BytecodeAuthHandler, BytecodeAuthError
from run_world_luau import read_source
from script_runtime import ClientScriptRuntime
from script_console import ScriptConsole
from persistent_runtime import PersistentClientScriptRuntime
from chat_console import ChatConsole
from physics_live_monitor import PhysicsLiveMonitor
from physics_runtime_prediction import own_character_monitor_snapshot
from runtime_diagnostics import CoalescedPrivateSnapshotWriter
from physics_trial_finalization import finalize_physics_reports
from client_session_lease import SessionLeaseBusy, acquire_session_lease
from session_diagnostics import current, session_logging
from session_awake import prevent_idle_sleep


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--duration", type=int, default=12, help="Session seconds; 0 runs until quit or disconnection")
    parser.add_argument('--log-level',choices=('verbose','normal','off'),default='verbose',
                        help='Session timeline in outputs/logs (default: verbose)')
    parser.add_argument("--protocol-sync", action="store_true", help="Also send the recovered version/player-info packet")
    parser.add_argument("--luau-range", action="store_true", help="Negotiate the existing static reader's bytecode versions 13–14")
    parser.add_argument("--ticket", action="store_true", help="Send the issued account ticket and remaining normal connection packets")
    parser.add_argument("--streaming-ready", action="store_true", help="Report readiness after receiving the character's surrounding region")
    parser.add_argument("--progress", action="store_true", help="Print sanitized connection milestones while the test is running")
    parser.add_argument("--time-sync", action="store_true", help="Also exercise the normal native clock service with five bounded requests")
    parser.add_argument("--framework-init", action="store_true", help="Make the single statically verified Nothingness framework-state request")
    parser.add_argument('--bytecode-auth', action='store_true',
                        help='Verify and execute the server-issued signed program, then send its result')
    parser.add_argument('--require-spawn', action='store_true',
                        help='Require a server-replicated own Character for a successful exit')
    parser.add_argument('--experimental-physics-fall', action='store_true',
                        help='Try at most three candidate own-root physics frames within 1.5 seconds')
    parser.add_argument('--experimental-physics-walk', action='store_true',
                        help='Run the bounded one-minute Luau walk exercise, then leave')
    parser.add_argument('--physics', action='store_true',
                        help='Run continuous own-character gravity physics for this authenticated session')
    parser.add_argument('--visual-mesh-collisions', action='store_true',
                        help='Opt in to approximate collisions from fetched visual mesh triangles; Roblox collision fidelity can differ')
    parser.add_argument('--walk-for-minute', action='store_true',
                        help='Move the own character for one minute on a continuous --physics session, then leave')
    parser.add_argument('--script', action='append', default=[],
                        help='Run a .luau source file against the client world after the character loads')
    parser.add_argument('--script-timeout-ms', type=int, default=1000)
    parser.add_argument('--script-console', action='store_true',
                        help='Accept .luau source through the owner-only local client socket')
    parser.add_argument('--chat-console', action='store_true',
                        help='Compatibility flag; chat is enabled in every authenticated session')
    parser.add_argument('--persistent-scripts', action='store_true',
                        help='Compatibility flag; authenticated sessions always use persistent Luau')
    parser.add_argument('--early-script', action='append', default=[],
                        help='Start a persistent source file once the own Player is replicated')
    parser.add_argument('--memory-mb', type=int, default=512,
                        help='Persistent Luau VM memory cap in MiB (8..512, default 512)')
    args = parser.parse_args(argv)
    if not 8 <= args.memory_mb <= 512:
        parser.error('--memory-mb must be between 8 and 512')
    if args.ticket:
        args.chat_console = True
        args.persistent_scripts = True
    elif args.chat_console:
        args.persistent_scripts = True
    if args.luau_range and not args.protocol_sync:
        parser.error("--luau-range requires --protocol-sync")
    if args.ticket and not (args.protocol_sync and args.luau_range):
        parser.error("--ticket requires --protocol-sync --luau-range")
    if args.framework_init and not args.ticket:
        parser.error('--framework-init requires --ticket')
    if (args.bytecode_auth or args.require_spawn) and not args.ticket:
        parser.error('--bytecode-auth and --require-spawn require --ticket')
    if (args.physics or args.experimental_physics_fall or args.experimental_physics_walk) and not args.ticket:
        parser.error('Experimental physics requires --ticket')
    if args.walk_for_minute and not args.ticket:
        parser.error('--walk-for-minute requires --ticket')
    if args.walk_for_minute and not args.physics:
        parser.error('--walk-for-minute requires --physics')
    if args.visual_mesh_collisions and not args.physics:
        parser.error('--visual-mesh-collisions requires --physics')
    if sum((args.physics, args.experimental_physics_fall, args.experimental_physics_walk)) > 1:
        parser.error('Choose only one of --physics, --experimental-physics-fall, or --experimental-physics-walk')
    if (args.script or args.early_script or args.script_console or args.persistent_scripts) and not args.ticket:
        parser.error('--script and --script-console require --ticket')
    if args.early_script and not args.persistent_scripts:
        parser.error('--early-script requires --persistent-scripts')
    if args.chat_console and not args.ticket:
        parser.error('--chat-console requires --ticket')
    if len(args.script)+len(args.early_script) > 8 or not 1 <= args.script_timeout_ms <= 2000:
        parser.error('Use at most eight scripts and a timeout from 1 to 2000 ms')
    return args


def _create_physics_driver(args, script_runtime, walk_source=None):
    """Select a physics driver and share its controller with persistent Luau."""
    physics_trial = None
    walk_exercise = None
    report_key = 'experimental_physics'
    if args.physics:
        from live_character_physics import LiveCharacterPhysics
        kwargs = {'experimental_enabled': True,
                  'use_predicted_humanoid_state': True,
                  'use_predicted_rotation': True}
        if getattr(args, 'visual_mesh_collisions', False):
            kwargs['allow_visual_mesh_approximation'] = True
        physics_trial = LiveCharacterPhysics(**kwargs)
        report_key = 'character_physics'
        if getattr(args, 'walk_for_minute', False):
            from physics_walk_exercise import PhysicsWalkExercise
            if not walk_source:
                raise ValueError('The one-minute walk source must be loaded before starting the session')
            walk_exercise = PhysicsWalkExercise(walk_source)
    elif args.experimental_physics_fall or args.experimental_physics_walk:
        from live_physics_trial import LivePhysicsTrial, LivePhysicsWalk
        if args.experimental_physics_walk:
            from physics_walk_exercise import PhysicsWalkExercise
            physics_trial = LivePhysicsWalk(experimental_enabled=True,
                                            use_predicted_humanoid_state=True,
                                            use_predicted_rotation=True)
            walk_exercise = PhysicsWalkExercise(walk_source)
        else:
            physics_trial = LivePhysicsTrial(experimental_enabled=True,
                                            max_frames=3, max_duration=1.5,
                                            settle_ticks=3, halt_on_late_frame=False,
                                            use_predicted_humanoid_state=True,
                                            use_predicted_rotation=True)
    if physics_trial is not None and args.persistent_scripts:
        # Luau intentions and outgoing frames advance the same controller.
        script_runtime.movement_preview = physics_trial.prediction
        if args.physics:
            from owned_part_poses import OwnedPartPoses
            physics_trial.authored_parts = OwnedPartPoses(
                simulate=os.environ.get('RCR_OWNED_PART_GRAVITY') == '1')
            script_runtime.authored_part_poses = physics_trial.authored_parts
    return physics_trial, walk_exercise, report_key


def _run_session(args, *, ping_stats_provider=None, ping_status_provider=None, report_name='game-session'):
    if args.physics or args.experimental_physics_fall or args.experimental_physics_walk:
        # Load the codec before issuing a fresh allocation or opening a socket;
        # a cold FileProvider read must never stall an active game connection.
        from physics_packet import encode_physics_message
        from physics_history import CurrentRecord
        from physics_root_record import RootRecordEnvelope, encode_instance_reference, encode_client_current_body
        from physics_header import LAYOUT_SEQUENCE_THEN_TAG
    walk_source = (read_source(REPO_ROOT/'runtime/scripts/walk_for_minute.luau')
                   if args.experimental_physics_walk or getattr(args, 'walk_for_minute', False) else None)
    sources = [(path, read_source(path)) for path in args.script]
    early_sources = [(path, read_source(path)) for path in args.early_script]
    startup_labels = set(args.script+args.early_script)
    if args.refresh:
        with current().stage('allocation.refresh'), redirect_stdout(io.StringIO()):
            result = refresh_allocation()
        if result != 0:
            allocation_report = json.loads((ROOT / 'outputs/gamejoin/allocation-check.json').read_text())
            if allocation_report.get('user_privacy_blocks_join'):
                raise SessionError('Roblox refused the join: User privacy does not allow join.')
            raise SessionError("A fresh ready allocation was not issued")
    with current().stage('allocation.load'):
        session = NativeSession(duration=args.duration, capabilities=0x100000 if args.luau_range else 0)
    if current().enabled:
        session.report['diagnostic_log'] = str(current().path.relative_to(ROOT))
    from remote_client_rpc import RemoteClientRpc
    remote_client_rpc = RemoteClientRpc(session.capabilities) if args.persistent_scripts and args.luau_range else None
    from remote_server_events import RemoteServerEvents
    remote_server_events = RemoteServerEvents(session.capabilities) if remote_client_rpc is not None else None
    telemetry = getattr(session, 'ping_telemetry', None)
    telemetry_report_provider = None
    if telemetry is not None:
        if ping_stats_provider is None or ping_status_provider is None:
            telemetry_report_provider = telemetry.public_report
        if ping_stats_provider is None:
            ping_stats_provider = telemetry.replication_stats
        if ping_status_provider is None:
            ping_status_provider = telemetry.integrity_status
    ping_handler = SessionPingHandler(stats_provider=ping_stats_provider,
                                      status_provider=ping_status_provider,
                                      telemetry_report_provider=telemetry_report_provider)
    ping_handler.update_report(session)
    allocation_body = json.loads((ROOT / "secrets/last-join.json").read_text())["body"]
    join = allocation_body["joinScript"]
    from remote_server_rpc import RemoteServerRpc
    remote_server_rpc = RemoteServerRpc(join['UserId'], session.capabilities,
        disabled_reason=('InvokeServer is unavailable with legacy --framework-init'
                         if args.framework_init else None)) if remote_client_rpc is not None else None
    early_auth = issued_early_auth(join["ClientTicket"])
    bytecode_auth = BytecodeAuthHandler(join['GameId']) if args.bytecode_auth else None
    session.report['client_environment_program_execution_enabled'] = bytecode_auth is not None
    if bytecode_auth is not None:
        session.report['client_environment_auth'] = bytecode_auth.summary()
    world = None
    isr_receiver = None
    server_features = {}
    clock = TimeSyncProbe() if args.time_sync else None
    runtime_type = PersistentClientScriptRuntime if args.persistent_scripts else ClientScriptRuntime
    if args.persistent_scripts:
        script_runtime = runtime_type(lambda: world, join['UserId'], join['GameId'],
            memory_mb=args.memory_mb,
            session_stats_provider=(clock.runtime_statistics if clock is not None else None),
            allow_visual_mesh_approximation=args.visual_mesh_collisions)
    else:
        script_runtime = runtime_type(lambda: world, join['UserId'], join['GameId'])
    script_results = []
    last_state_check = 0.0
    milestones = set()
    markers = MarkerQueue()
    property_acks = None
    from session_wire_clock import SessionWireClock
    wire_clock = SessionWireClock()
    framework = None
    scripts_ran = False
    early_scripts_ran = False
    startup_scripts_ok = True
    console = None
    chat_console = None
    physics_monitor = PhysicsLiveMonitor()
    physics_trial = None
    physics_report_key = 'experimental_physics'
    isr_pose_sender = None
    physics_last_tick = None
    locomotion_animation = None
    locomotion_source_token = None
    animation_joint_model = None
    animation_updates = None
    animation_update_counts = {}
    walk_exercise = None
    last_runtime_diagnostics = 0.
    diagnostics_writer = None

    def queue_runtime_diagnostics():
        nonlocal diagnostics_writer
        if diagnostics_writer is None:
            diagnostics_writer = CoalescedPrivateSnapshotWriter()
        # RPC responses are finalized before delivery. Copy the mutable outer
        # lists/dicts; their nested native JSON values are retained read-only.
        diagnostics_writer.submit([
            (ROOT/'secrets/luau-persistent-stream.json',
             [dict(message) for message in script_runtime.messages]),
            (ROOT/'secrets/luau-script-last-results.json',
             [dict(result) for result in script_results])])
    if args.physics or args.experimental_physics_fall or args.experimental_physics_walk:
        physics_trial, walk_exercise, physics_report_key = _create_physics_driver(
            args, script_runtime, walk_source)
        if args.physics and os.environ.get('RCR_ISR_OWNED_POSES') == '1':
            from isr_sender import OwnedIsrSender
            isr_pose_sender = OwnedIsrSender(physics_trial.authored_parts,
                explicit_null_root=os.environ.get('RCR_ISR_EXPLICIT_NULL_ROOT') == '1')
            # The alternate sender owns this queue; avoid duplicate legacy
            # submissions of the same authored state during the experiment.
            physics_trial.authored_parts = None
        if args.persistent_scripts:
            from locomotion_animation import LocomotionAnimationDriver
            from animation_joint_model import AnimationJointModel
            from animation_native_updates import NativeAnimationUpdates
            locomotion_animation = LocomotionAnimationDriver()
            script_runtime.enable_animation_intents()
            animation_joint_model = AnimationJointModel(join['UserId'],
                lambda reference: script_runtime.animation_assets.pose_clip(reference)
                    if script_runtime.animation_assets is not None else None)
            animation_updates = NativeAnimationUpdates()
        # NativeSession invokes this during its own finally block, before its
        # single public report and history append. Do not advance the trial here.
        session.report_finalizer = lambda report: finalize_physics_reports(
            report, physics_trial, walk_exercise, now=time.monotonic(),
            report_key=physics_report_key,
            walk_report_key=('character_walk' if args.physics else 'experimental_physics_walk'))
    if args.framework_init:
        if session.place != 6252985844:
            raise SessionError('The verified framework request is specific to the selected Nothingness place')
        spec = json.loads((ROOT / 'secrets/private-client-framework-rpc.json').read_text())
        framework = FrameworkInitRpc(spec, join['UserId'], session.capabilities)
        session.report['framework_init_rpc'] = framework.summary()

    def milestone(name):
        if name not in milestones:
            milestones.add(name)
            current().emit('game.milestone',name=name,session_s=round(time.monotonic()-session.started,3))
            if args.progress:
                print(json.dumps({'milestone': name, 'place_id': session.place,
                                  'seconds': round(time.monotonic() - session.started, 3)}), flush=True)

    def flush_markers(client):
        for reply in markers.drain(world):
            client.send(1, reply)
            client.report['replication_markers_acknowledged'] = client.report.get('replication_markers_acknowledged', 0) + 1
            client.report['marker_reply_after_initial_world'] = True
            client.report['last_marker_reply_at_seconds'] = round(time.monotonic() - client.started, 3)
            milestone('initial_world_marker_replied')

    def advance_framework(client):
        if framework is None:
            return
        request = framework.prepare(world)
        if request is not None:
            client.send(1, request)
            client.report['framework_request_sent'] = True
            client.report['framework_request_at_seconds'] = round(time.monotonic() - client.started, 3)
            milestone('framework_state_requested')
        if framework.poll(world):
            client.report['framework_reply_at_seconds'] = round(time.monotonic() - client.started, 3)
            if framework.state == 'succeeded':
                # Keep returned state private. A successful RPC is not evidence
                # that all client scripts initialized or that a character spawned.
                client.report['framework_return_value_present'] = bool(framework.result and framework.result[0] is not None)
                milestone('framework_state_reply_received')
            else:
                milestone('framework_request_server_error')
        client.report['framework_init_rpc'] = framework.summary()

    def update_script_report(*, persist=True):
        if persist:
            if args.persistent_scripts:
                queue_runtime_diagnostics()
            else:
                write_private(ROOT/'secrets/luau-script-last-results.json', script_results)
        session.report['luau_scripts_executed'] = script_runtime.executions
        session.report['luau_scripts'] = [
            {'ok': r['ok'], 'returned_values': len(r.get('values', [])),
             'output_lines': len(r.get('output', '').splitlines()),
             'local_mutations': len(r.get('mutations', [])),
             'runtime_backend': r.get('runtime_backend', 'unknown'),
             'task_errors': len(r.get('task_errors', [])),
             'state': r.get('state', 'completed' if r['ok'] else 'failed')}
            for r in script_results]

    def execute_source(source, *, timeout_ms=1000, label='<console>'):
        result = script_runtime.execute(source, timeout_ms=timeout_ms)
        script_results.append({'script': label, **result})
        del script_results[:-32]
        update_script_report()
        return result

    def submit_locomotion_source(source, *, timeout_ms=250,
                                 label='<locomotion-animation>'):
        """Queue one animation source RPC without blocking the network tick."""
        nonlocal locomotion_source_token
        if locomotion_source_token is not None:
            return None
        token = script_runtime.queue_background_source(
            source, label=label, timeout_ms=timeout_ms)
        if token is not None:
            locomotion_source_token = token
        return token

    def run_scripts(client, evidence):
        nonlocal scripts_ran, early_scripts_ran, startup_scripts_ok
        selected=[]
        if early_sources and not early_scripts_ran and evidence['own_player_parented_to_players']:
            selected.extend(early_sources);early_scripts_ran=True
            client.report['luau_early_scripts_at_seconds']=round(time.monotonic()-client.started,3)
        if sources and not scripts_ran and evidence['player_spawned'] and 13 in world.tags:
            selected.extend(sources);scripts_ran=True
        for path, source in selected:
            try:
                script_result = execute_source(source, timeout_ms=args.script_timeout_ms, label=path)
                startup_scripts_ok = startup_scripts_ok and script_result['ok']
            except Exception as error:
                startup_scripts_ok = False
                script_results.append({'script': path, 'ok': False, 'values': [],
                                       'error_type': type(error).__name__})
                if args.persistent_scripts:
                    queue_runtime_diagnostics()
                else:
                    write_private(ROOT/'secrets/luau-script-last-results.json', script_results)
                client.report['luau_scripts'] = [{'ok': False, 'error_type': type(error).__name__}]
        if selected:milestone('luau_source_files_submitted' if args.persistent_scripts else 'luau_source_files_executed')

    def ready(client):
        milestone('transport_connected')
        wire_clock.initialize_replicator()
        client.report['wire_clock'] = wire_clock.report()
        if clock is not None:
            client.send(CONTROL_CHANNEL, b'\0\0', application=CLOCK_APPLICATION)
            client.open_channel(CLOCK_APPLICATION, 1)
            client.open_unreliable_channel(CLOCK_APPLICATION, 2)
            client.open_unreliable_channel(CLOCK_APPLICATION, CLOCK_CHANNEL)
            clock.start(time.monotonic())
            client.report.update(clock.public_report())
            client.report['time_sync_clock_offset_estimated'] = False
        client.send(1, early_auth)
        client.report["early_auth_sent"] = True
        if args.protocol_sync:
            bytecode_range = (13, 14) if args.luau_range else None
            if bytecode_range is not None and not int(client.report["server_capabilities"], 16) & 0x100000:
                raise SessionError("Server does not support bytecode-range negotiation")
            client.send(1, protocol_sync(join, allocation_body.get("joinTicket"), bytecode_range))
            client.report["protocol_sync_sent"] = True
            client.report["bytecode_range"] = bytecode_range
            client.report["imported_script_execution_enabled"] = False
        if args.ticket:
            client.send(1, verification_packet())
            client.send(1, ticket_packet(join))
            client.send(1, server_id_packet())
            client.report["full_client_ticket_sent"] = True

    def packet(client, application, channel, payload):
        nonlocal world, last_state_check, isr_receiver, server_features, property_acks
        if clock is not None and application == CLOCK_APPLICATION and channel == CLOCK_CHANNEL:
            if clock.receive(payload, time.monotonic(),
                             local_receive_us=wire_clock.microseconds(),
                             extended_timing=True):
                client.report.update(clock.public_report())
                milestone('native_time_sync_echo_received')
        elif application == 4 and channel == 3 and payload[:1] == b"\x83" and world is None:
            ping_handler.receive(client, payload)
            client.report['last_application_ping_at_seconds'] = round(time.monotonic() - client.started, 3)
        elif application == 4 and channel == 1 and payload[:1] == b"\x93":
            config = feature_configuration(payload)
            server_features = config
            if isr_receiver is not None:
                isr_receiver.legacy_pv_enabled = config.get('DebugAdaptivePVCompressor') == 'false'
            if chat_console is not None:
                chat_console.chat.configure_server_features(config)
            client.report["server_feature_configuration_received"] = True
            client.report["server_feature_count"] = len(config)
        elif application == 4 and channel == 1 and payload[:1] == b"\x9b":
            check = parse_program_check(payload)
            client.report['client_environment_check'] = check.summary()
            client.report['client_environment_challenges_received'] = client.report.get('client_environment_challenges_received', 0) + 1
            if bytecode_auth is None:
                client.report['client_environment_challenge_handling'] = 'not_implemented'
                milestone('client_environment_verification_unimplemented')
            else:
                try:
                    with current().stage('game.signed_program'):
                        response = bytecode_auth.handle(payload)
                except BytecodeAuthError as error:
                    client.report['client_environment_auth'] = bytecode_auth.summary()
                    client.report['client_environment_challenge_handling'] = 'failed'
                    if bytecode_auth.last_runtime_error:
                        write_private(ROOT / 'secrets/bytecode-runtime-last-error.json',
                                      bytecode_auth.last_runtime_error)
                    raise SessionError('Signed program verification/execution failed: ' + str(error)) from None
                client.send(1, response)
                client.report['client_environment_auth'] = bytecode_auth.summary()
                client.report['client_environment_responses_sent'] = client.report.get('client_environment_responses_sent', 0) + 1
                client.report['client_environment_challenge_handling'] = 'response_sent'
                client.report['client_environment_check'].update(
                    execution_implemented=True, response_implemented=True, response_bytes=len(response))
                milestone('signed_client_environment_program_answered')
        elif application == 4 and channel == 1 and payload[:1] == b"\x97":
            schema = parse_schema(payload)
            world = World(schema)
            world.allow_small_unsigned_scripts = (args.ticket
                and client.report.get('certificate_pin_verified') is True)
            property_acks = None
            isr_receiver = InstanceStateReceiver(world, legacy_pv_enabled=
                server_features.get('DebugAdaptivePVCompressor') == 'false')
            client.report["network_schema_decoded"] = True
            client.report["schema_classes"] = len(schema['classes'])
        elif application == 4 and channel == 1 and payload[:1] == b"\x81":
            if world is None: raise SessionError('Globals arrived before their schema')
            world.globals(payload)
            client.report['globals_decoded'] = True
            client.report['server_character_auto_loads'] = bool(world.global_flags[6])
            client.report['top_containers'] = len(world.top_containers)
        elif application == 4 and channel == 1 and payload[:1] == b"\x84":
            if world is None or world.client_scope is None:
                raise SessionError('Replication marker arrived before globals')
            markers.add(payload)
            flush_markers(client)
        elif application == 4 and channel == 5 and payload[:1] == b"\xa1":
            if isr_receiver is None:
                client.report['isr_packets_before_schema'] = client.report.get('isr_packets_before_schema', 0) + 1
            else:
                accepted = isr_receiver.receive(payload)
                if accepted and isr_pose_sender is not None:
                    isr_pose_sender.observe_remote(world, isr_receiver.last_timestamp)
                client.report['instance_state_replication'] = isr_receiver.summary()
        elif application == 4 and channel in (1, 3) and payload[:1] == b"\x83":
            if world is None:
                raise SessionError('World data arrived before its schema')
            # Channel 3 also carries ordinary replicated events. Decode item
            # kinds through the world parser instead of treating every message
            # as a ping-only frame. Reply only after the full packet validates.
            pings = world.packet(payload)
            if os.environ.get('RCR_PROPERTY_ACKS') == '1' and args.physics:
                if property_acks is None:
                    from property_acknowledgments import PropertyAcknowledgments
                    property_acks = PropertyAcknowledgments(world)
                property_acks.observe(local_step=physics_trial.prediction.simulation_step)
                client.report['property_acknowledgments'] = property_acks.summary()
            if remote_client_rpc is not None:
                remote_client_rpc.observe(world)
            if pings:
                ping_handler.receive_items(client, pings)
                client.report['last_application_ping_at_seconds'] = round(time.monotonic() - client.started, 3)
            flush_markers(client)
            advance_framework(client)
            client.report['world_packets_decoded'] = client.report.get('world_packets_decoded', 0) + 1
            client.report['world_instances'] = len(world.instances)
            now = time.monotonic()
            if now - last_state_check >= 0.1:
                last_state_check = now
                avatar = world.avatar(join['UserId'])
                evidence = avatar['evidence']
                client.report.update(evidence)
                client.report['physics_received'] = physics_monitor.observe(
                    own_character_monitor_snapshot(world, join['UserId'], avatar=avatar),
                    timestamp=now-client.started)
                if evidence['own_player_parented_to_players']:
                    milestone('own_player_in_players')
                if evidence['player_spawned']:
                    milestone('character_spawned')
                if evidence['player_spawned'] and 'spawn_verified_at_seconds' not in client.report:
                    client.report['spawn_verified_at_seconds'] = round(now - client.started, 3)
                run_scripts(client, evidence)
                if args.streaming_ready and evidence['spawn_region_received'] and not client.report.get('streaming_ready_sent'):
                    client.send(1, streaming_ready(world, join['UserId']))
                    client.report['streaming_ready_sent'] = True
                    client.report['streaming_ready_at_seconds'] = round(now - client.started, 3)
                if evidence['movement_ready'] and 'movement_ready_at_seconds' not in client.report:
                    client.report['movement_ready_at_seconds'] = round(now - client.started, 3)

    def tick(client, now):
        nonlocal startup_scripts_ok, physics_last_tick, last_runtime_diagnostics
        nonlocal locomotion_source_token
        remote_event_budget = 16
        with current().stage('game.ping_flush'):
            ping_handler.flush(client)
        if remote_client_rpc is not None:
            remote_client_rpc.observe(world)
            for _ in range(min(16, len(script_runtime.remote_client_replies))):
                remote_client_rpc.send_reply(world, script_runtime.remote_client_replies[0], client.send)
                script_runtime.remote_client_replies.popleft()
            client.report['remote_client_callbacks'] = remote_client_rpc.summary()
        if remote_server_events is not None:
            remote_event_budget -= remote_server_events.flush(
                world, script_runtime.remote_server_events, client.send,
                unreliable_transport=client.send_unreliable)
            client.report['remote_server_events'] = remote_server_events.summary()
        if remote_server_rpc is not None:
            remote_server_rpc.flush(world, script_runtime, client.send)
            client.report['remote_server_rpc'] = remote_server_rpc.summary()
        if chat_console is not None:
            with current().stage('game.chat'):
                chat_console.tick(client, world)
        if clock is not None:
            payload = clock.due(now, wire_clock.microseconds())
            if payload is not None:
                client.send_unreliable(CLOCK_CHANNEL, payload, application=CLOCK_APPLICATION)
                client.report.update(clock.public_report())
        if console is not None:
            with current().stage('game.console'):
                console.poll()
            client.report['luau_console_requests'] = console.requests
        if args.persistent_scripts:
            try:
                with current().stage('game.luau_scheduler'):
                    response=script_runtime.poll_background()
                if locomotion_animation is not None and locomotion_source_token is not None:
                    animation_result = script_runtime.take_background_source_result(
                        locomotion_source_token)
                    if animation_result is not None:
                        locomotion_animation.complete(locomotion_source_token,
                                                      animation_result)
                        locomotion_source_token = None
                if response is not None:
                    for result in script_results:
                        completed=script_runtime.results.get(result.get('job_id'))
                        if completed:
                            result.update(completed)
                            if result['script'] in startup_labels and not result['ok']:startup_scripts_ok=False
                    diagnostics_now = time.monotonic()
                    persist = diagnostics_now-last_runtime_diagnostics >= 1.
                    if persist:
                        queue_runtime_diagnostics()
                        last_runtime_diagnostics = diagnostics_now
                    update_script_report(persist=False)
                if diagnostics_writer is not None and diagnostics_writer.error_type is not None:
                    client.report['runtime_diagnostics_error_type'] = diagnostics_writer.error_type
                client.report['luau_runtime']={'backend':'rust-persistent','healthy':not script_runtime.failure,**script_runtime.stats}
            except Exception as error:
                current().exception('game.luau_error',error)
                startup_scripts_ok=False
                write_private(ROOT/'secrets/luau-persistent-failure.json',
                              {'error_type':type(error).__name__,'error':str(error),
                               'runtime_failure_context':script_runtime.failure_context,
                               'last_response':script_runtime.messages[-1] if script_runtime.messages else None})
                client.report['luau_runtime']={'backend':'rust-persistent','healthy':False,'error_type':type(error).__name__}
                # Runtime failure closes the shared prediction controller.
                # Do not restart that disposed controller in the network tick:
                # its new clock would invalidate the session's ISR timeline.
                if physics_trial is not None and script_runtime.failure:
                    physics_trial.stop('shared_script_runtime_failed')

        # A completed callback can produce an event during this tick. Use any
        # remaining budget now, preserving FIFO and the total 16-attempt limit.
        # Keep transport errors outside the Luau-error handler above.
        if (remote_server_events is not None and remote_event_budget
                and script_runtime.remote_server_events and not client.finished):
            remote_server_events.flush(
                world, script_runtime.remote_server_events, client.send,
                unreliable_transport=client.send_unreliable, max_events=remote_event_budget)
            client.report['remote_server_events'] = remote_server_events.summary()

        if property_acks is not None and not client.finished:
            property_acks.flush(client.send)
            client.report['property_acknowledgments'] = property_acks.summary()

        if physics_trial is not None and wire_clock.replicator_initialized:
            now = time.monotonic()
            delta = min(.25, max(0., now-physics_last_tick)) if physics_last_tick is not None else 0.
            physics_last_tick = now
            with current().stage('game.physics'):
                trial_report = physics_trial.tick(
                    world=world, own_user_id=join['UserId'], now=now, delta=delta,
                    timestamp_ms=wire_clock.physics_milliseconds(), connected=not client.finished,
                    send_unreliable=client.send_unreliable)
            client.report['wire_clock'] = wire_clock.report()
            client.report[physics_report_key] = {
                key: value for key, value in trial_report.items() if key != 'local_prediction'}
            if isr_pose_sender is not None and world is not None and not client.finished:
                client.report['isr_authored_poses'] = isr_pose_sender.tick_prediction(
                    world, trial_report.get('local_prediction'),
                    legacy_pv_enabled=server_features.get('DebugAdaptivePVCompressor') == 'false',
                    send_unreliable=client.send_unreliable, track_delivery=True,
                    send_reliable=client.send, now=now)
            if locomotion_animation is not None:
                client.report['local_locomotion_animation'] = locomotion_animation.tick(
                    world=world, own_user_id=join['UserId'], physics_report=trial_report,
                    now=now, submit_source=submit_locomotion_source,
                    connected=not client.finished)
            if animation_joint_model is not None:
                animation_entries = script_runtime.animation_outbox.drain()
                if animation_updates is not None and not client.finished:
                    try:
                        prepared = animation_updates.prepare(animation_entries, world=world,
                            user_id=join['UserId'], capability_bits=client.capabilities)
                        for update in prepared:
                            client.send(1, update['payload'])
                            operation = update['operation']
                            animation_update_counts[operation] = animation_update_counts.get(operation, 0) + 1
                        client.report['animation_replication'] = {
                            'status':'updates_submitted' if animation_update_counts else 'waiting_for_playback',
                            'producer':'ordinary_animation_track',
                            'operations_submitted':dict(animation_update_counts),
                            'server_animation_confirmed':False}
                    except (ValueError,TypeError,RuntimeError,KeyError) as error:
                        client.report['animation_replication'] = {
                            'status':'animation_update_failed','error_type':type(error).__name__,
                            'operations_submitted':dict(animation_update_counts),
                            'server_animation_confirmed':False}
                try:
                    posed = animation_joint_model.tick(world=world, physics_report=trial_report,
                        entries=animation_entries, now=time.monotonic(),
                        snapshot=(script_runtime.movement_preview.bridge.animation_snapshot()
                                  if script_runtime.movement_preview is not None else None))
                    script_runtime.local_animation_joint_pose = posed
                    if posed.get('engine_poses') is not None:
                        script_runtime.queue_engine_poses(**posed['engine_poses'])
                    client.report['local_animation_joints'] = {
                        key: posed[key] for key in ('status','source','resolved_bodyparts',
                            'rig_edges','root_fixed','sampled_tracks','joint_pose_changes',
                            'arm_pose_changes','leg_pose_changes','server_animation_confirmed')
                        if key in posed}
                except (ValueError,TypeError,RuntimeError,KeyError) as error:
                    script_runtime.local_animation_joint_pose = None
                    client.report['local_animation_joints'] = {
                        'status':'local_joint_evaluation_failed',
                        'error_type':type(error).__name__,'server_animation_confirmed':False}
            if trial_report['network_send_attempt_count']:
                if args.physics:
                    milestone('physics_updates_started')
                    milestone('physics_send_handoff')
                else:
                    milestone('experimental_physics_submitted')
            if trial_report['stop_reason'] is not None:
                milestone(('character_physics_stopped_' if args.physics else 'experimental_physics_fall_stopped_')
                          + trial_report['stop_reason'])
            if walk_exercise is not None:
                walk_report_key = ('character_walk' if args.physics else 'experimental_physics_walk')
                client.report[walk_report_key] = walk_exercise.tick(
                    now=time.monotonic(), trial_report=trial_report,
                    execute_source=execute_source, results=script_runtime.results,
                    connected=not client.finished, close=client.close)
                if client.report[walk_report_key]['submission_attempted']:
                    milestone('physics_walk_luau_submitted')
                if client.report[walk_report_key]['luau_completed']:
                    milestone('physics_walk_luau_completed')

    if args.script_console:
        from world_snapshot import make_world_snapshot
        from received_instance_diagnostics import inspect_received
        def export_snapshot():
            if world is None:
                raise ValueError("Client world is not ready")
            return make_world_snapshot(world, join["UserId"], job_id=join["GameId"])
        from browser_input import BrowserKeyboard
        console = ScriptConsole(ROOT/'secrets/client-script.sock', execute_source,
                                (lambda job_id: script_runtime.status(job_id, advance=False))
                                if args.persistent_scripts else None,
                                events=script_runtime.events if args.persistent_scripts else None,
                                user_chat=script_runtime.execute_user_chat if args.persistent_scripts else None,
                                display=script_runtime.update_display if args.persistent_scripts else None,
                                export_snapshot=export_snapshot,
                                render=script_runtime.render_frame if args.persistent_scripts else None,
                                gui_action=script_runtime.gui_action if args.persistent_scripts else None,
                                leave=session.close,
                                inspect_received=lambda path: inspect_received(world,path,getattr(script_runtime,'authored_part_poses',None)),
                                keyboard=BrowserKeyboard(script_runtime) if args.persistent_scripts else None)
        session.report['luau_console_enabled'] = True
    try:
        if args.chat_console:
            chat_console = ChatConsole(ROOT/'secrets/client-chat.sock', join['UserId'],
                                       capability_bits=session.capabilities)
            script_runtime.chat_bridge = chat_console
        observation_scope = telemetry.integrity.observe_containers() if telemetry is not None else nullcontext()
        with observation_scope, prevent_idle_sleep(session.report), current().stage('transport.loop'):
            result = session.run(ready, packet, report_name=report_name,
                                 on_tick=tick if clock is not None or console is not None or args.persistent_scripts or chat_console is not None or physics_trial is not None else None)
    finally:
        if chat_console is not None: chat_console.close()
        if console is not None: console.close()
        if args.persistent_scripts:
            script_runtime.close()
            if script_runtime.messages:
                queue_runtime_diagnostics()
                update_script_report(persist=False)
            if diagnostics_writer is not None:
                diagnostics_writer.close(flush=True, timeout=2)
    keys = ("certificate_pin_verified", "quic_handshake_completed", "webtransport_session_established",
            "early_auth_sent", "protocol_sync_sent", "full_client_ticket_sent", "bytecode_range", "server_feature_count",
            "game_account_accepted", "player_spawned", "streaming_ready_sent", "root_unanchored_by_server", "movement_ready", "walk_seconds_verified",
            "own_player_parented_to_players", "character_reference_received", "world_packets_decoded",
            "time_sync_requests_sent", "time_sync_echoed_responses", "wire_clock",
            "framework_request_sent", "framework_init_rpc", "framework_return_value_present", "remote_server_rpc",
            "client_environment_challenges_received", "client_environment_challenge_handling", "client_environment_check",
            "client_environment_auth", "client_environment_responses_sent",
            "luau_scripts_executed", "luau_scripts",
            "luau_console_enabled", "luau_console_requests",
            "luau_runtime", "luau_early_scripts_at_seconds", "local_locomotion_animation", "local_animation_joints", "animation_replication",
            "chat", "physics_received", "experimental_physics", "experimental_physics_walk", "character_physics", "character_walk",
            "application_pings_received", "application_ping_replies_implemented",
            "application_ping_reply_transport_implemented", "application_ping_missing_providers",
            "application_ping_requests_received", "application_ping_responses_received",
            "application_ping_replies_sent", "application_ping_replies_pending",
            "application_ping_requests_unsupported", "application_ping_queue_overflows",
            "application_ping_telemetry_blocks", "application_ping_telemetry_blocks_by_provider",
            "application_ping_last_telemetry_block", "application_ping_provider_callbacks_configured",
            "application_ping_session_telemetry", "application_close", "server_application_close_at_seconds",
            "termination", "duration_limit_reached", "elapsed_seconds")
    print(json.dumps({k: result[k] for k in keys if k in result}, indent=2))
    # Milestones come from server-replicated identity and character references.
    stage_complete = result.get("game_account_accepted", False) if args.protocol_sync else result.get("server_feature_configuration_received", False)
    if result.get('client_environment_challenges_received', 0):
        stage_complete = stage_complete and result.get('client_environment_challenge_handling') == 'response_sent'
    if framework is not None:
        stage_complete = stage_complete and framework.state == 'succeeded'
    if args.require_spawn:
        stage_complete = stage_complete and result.get('player_spawned', False)
    if walk_exercise is not None:
        walk_report_key = 'character_walk' if args.physics else 'experimental_physics_walk'
        stage_complete = stage_complete and result.get(walk_report_key, {}).get('luau_completed', False)
    if sources or early_sources:
        stage_complete = stage_complete and (not sources or scripts_ran) and (not early_sources or early_scripts_ran) and startup_scripts_ok
    return 0 if stage_complete and not result.get("application_close") and not result.get("error_type") else 2


def main(*, ping_stats_provider=None, ping_status_provider=None, report_name='game-session',
         account_root=None):
    # Keep CLI validation ahead of filesystem/network side effects. The lease
    # then covers allocation refresh, socket setup, the full session, and cleanup.
    args = parse_args()
    (ROOT / 'secrets').mkdir(parents=True, exist_ok=True)
    (ROOT / 'outputs/gamejoin').mkdir(parents=True, exist_ok=True)
    # Isolated validation runs still use the same account. Their output root
    # must not give them a separate lock from the ordinary terminal client.
    with session_logging(ROOT,level=args.log_level,duration_s=args.duration,
                         physics=args.physics,persistent_scripts=args.persistent_scripts,
                         walk_for_minute=args.walk_for_minute,
                         experimental_physics_walk=args.experimental_physics_walk) as diagnostics:
        with diagnostics.stage('account.acquire_lease'), acquire_session_lease(ROOT if account_root is None else account_root):
            with diagnostics.stage('session.setup'):
                result = _run_session(args, ping_stats_provider=ping_stats_provider,
                                      ping_status_provider=ping_status_provider,
                                      report_name=report_name)
            diagnostics.emit('process.exiting',exit_code=result)
            return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SessionLeaseBusy as error:
        print(json.dumps({'error_type': 'SessionLeaseBusy', 'error': str(error)}))
        raise SystemExit(1)
    except SessionError as error:
        print(json.dumps({'error_type': 'SessionError', 'error': str(error)}))
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1)
