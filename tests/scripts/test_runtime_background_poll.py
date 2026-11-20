import threading
import time
import unittest
from unittest.mock import patch

from persistent_runtime import PersistentClientScriptRuntime
from test_world_snapshot import fixture


def ok(**extra):
    return {'ok': True, 'values': [], **extra}


class GatedHost:
    def __init__(self, before_return=None, *, failure=None):
        self.before_return = before_return
        self.failure = failure
        self.calls = []
        self.threads = []
        self.closed = False
        self.finished = threading.Event()
        self.lock = threading.Lock()

    def call(self, command):
        with self.lock:
            self.calls.append(command)
            self.threads.append(threading.get_ident())
        try:
            if self.before_return:
                self.before_return(command)
            if self.failure:
                raise self.failure
            return ok()
        finally:
            self.finished.set()

    def close(self):
        self.closed = True


class RuntimeBackgroundPollTests(unittest.TestCase):
    def test_native_failure_stage_survives_background_rpc_failure(self):
        class FailedReplyHost(GatedHost):
            def call(self, command):
                return {'ok':False,'values':[], 'error':'loadstring:175: missing',
                        'runtime_failure_context':{'operation':'poll','stage':'script_reconcile_final'}}
        runtime,_,_=self.make_runtime(FailedReplyHost())
        runtime.poll_background()
        with self.assertRaisesRegex(RuntimeError,'loadstring:175'):
            self.drain_completed(runtime)
        self.assertEqual(runtime.failure_context,
            {'operation':'poll','stage':'script_reconcile_final'})

    def test_native_remote_reply_is_queued_once_for_session_owner(self):
        runtime,_,_=self.make_runtime(GatedHost())
        reply={'node':'1:77','request_id':3,'ok':True,'values':[None,42]}
        runtime._record(ok(remote_client_replies=[reply]))
        runtime._record(ok(remote_client_replies=[]))
        self.assertEqual(list(runtime.remote_client_replies),[reply])

    def test_authored_test_slice_applies_without_event_backpressure(self):
        for profile,active,expected in [('0',1,50),('1',0,50),('1',1,250)]:
            for update in (False,True):
                with self.subTest(profile=profile,active=active,update=update):
                    host=GatedHost();runtime,world,key=self.make_runtime(host)
                    runtime.stats.update(pending_events=0,active_jobs=active)
                    if update:self.touch_name(world,key,b'changed')
                    with patch.dict('os.environ',{'RCR_LUAU_LARGE_TEST':profile}):
                        runtime.poll_background();self.drain_completed(runtime)
                    self.assertEqual(host.calls[0]['timeout_ms'],expected)
                    self.assertEqual(host.calls[0]['op'],'update' if update else 'poll')

    def test_longer_backpressure_slice_requires_test_profile_and_active_authored_job(self):
        for profile,active,expected in [('0',1,50),('1',0,50),('1',1,250)]:
            with self.subTest(profile=profile,active=active):
                host=GatedHost();runtime,_,_=self.make_runtime(host)
                runtime.stats.update(pending_events=512,active_jobs=active)
                with patch.dict('os.environ',{'RCR_LUAU_LARGE_TEST':profile}):
                    runtime.poll_background();self.drain_completed(runtime)
                self.assertEqual(host.calls[0],{'op':'poll','timeout_ms':expected})

    def test_large_test_slice_returns_to_background_budget_only_when_all_jobs_wait(self):
        cases = [
            ('sleeping', ['sleeping', 'waiting'], 50),
            ('mixed', ['sleeping', 'ready'], 250),
            ('executing', ['sleeping', 'executing'], 250),
            ('unknown_state', ['sleeping', 'unknown'], 250),
            ('missing_diagnostic', ['sleeping', None], 250),
        ]
        for name, states, expected in cases:
            with self.subTest(case=name):
                host=GatedHost();runtime,world,key=self.make_runtime(host)
                runtime.stats.update(active_jobs=len(states),pending_events=0)
                runtime.submitted={job_id:{'state':'running','diagnostic':(
                    {'job_id':job_id,'scheduler_state':state} if state is not None else None)}
                    for job_id,state in enumerate(states,1)}
                if name=='missing_diagnostic':
                    runtime.submitted[2].pop('diagnostic')
                self.touch_name(world,key,b'changed')
                with patch.dict('os.environ',{'RCR_LUAU_LARGE_TEST':'1'}):
                    runtime.poll_background();self.drain_completed(runtime)
                self.assertEqual(host.calls[0]['timeout_ms'],expected)

    def test_large_test_budget_uses_latest_active_job_set_after_completion(self):
        host=GatedHost();runtime,world,key=self.make_runtime(host)
        runtime.stats.update(active_jobs=1,pending_events=0)
        runtime.submitted[1]={'state':'running','diagnostic':
            {'job_id':1,'scheduler_state':'sleeping'}}
        runtime._record(ok(job_id=2,state='running',active_jobs=1,
            completed_jobs=[{'job_id':1,'completed':True,'ok':True,'state':'completed','values':[]}],
            job_diagnostics=[{'job_id':2,'scheduler_state':'ready'}]))
        self.touch_name(world,key,b'changed')
        with patch.dict('os.environ',{'RCR_LUAU_LARGE_TEST':'1'}):
            runtime.poll_background();self.drain_completed(runtime)
        scheduling=next(call for call in host.calls if call['op'] in ('poll','update'))
        self.assertEqual(scheduling['timeout_ms'],250)

    def test_large_test_budget_discards_stale_scheduler_diagnostics(self):
        host=GatedHost();runtime,_,_=self.make_runtime(host)
        runtime.stats.update(active_jobs=1,pending_events=0)
        runtime.submitted[1]={'state':'running','diagnostic':
            {'job_id':1,'scheduler_state':'sleeping'}}
        runtime._record(ok(active_jobs=1))
        self.assertNotIn('diagnostic',runtime.submitted[1])
        with patch.dict('os.environ',{'RCR_LUAU_LARGE_TEST':'1'}):
            self.assertEqual(runtime._background_step_budget(),250)

    def test_large_test_budget_treats_invalid_active_count_as_unknown(self):
        runtime,_,_=self.make_runtime(GatedHost())
        with patch.dict('os.environ',{'RCR_LUAU_LARGE_TEST':'1'}):
            for active in (True,-1,'1',None):
                with self.subTest(active=active):
                    runtime.stats['active_jobs']=active
                    self.assertEqual(runtime._background_step_budget(),250)

    def test_failed_runtime_does_not_report_cached_jobs_as_still_ready(self):
        runtime,_,_=self.make_runtime(GatedHost())
        runtime.submitted[4]={'ok':True,'state':'running','completed':False,
                              'diagnostic':{'scheduler_state':'ready'}}
        runtime.failure='local event queue limit exceeded'
        result=runtime.status(4,advance=False)
        self.assertFalse(result['ok']);self.assertEqual(result['state'],'failed')
        self.assertTrue(result['completed']);self.assertNotIn('diagnostic',result)
        self.assertIn(runtime.failure,result['error'])
        runtime.results[4]={'ok':True,'completed':True,'state':'completed','values':[42]}
        self.assertEqual(runtime.status(4,advance=False)['values'],[42])

    def test_event_backpressure_drains_before_acknowledging_more_world_actions(self):
        host=GatedHost()
        runtime,world,root_key=self.make_runtime(host)
        before=runtime.revision
        self.touch_name(world,root_key,b'first')
        runtime.stats['pending_events']=512
        runtime.poll_background();self.drain_completed(runtime)
        self.assertEqual(host.calls[0]['op'],'poll')
        self.assertEqual(runtime.revision,before)
        self.touch_name(world,root_key,b'second')
        runtime.stats['pending_events']=0;runtime.last_poll=0
        runtime.poll_background();self.drain_completed(runtime)
        scheduling=[c for c in host.calls if c['op'] in ('poll','update')]
        self.assertEqual([c['op'] for c in scheduling],['poll','update'])
        actions=scheduling[1]['delta']['actions']
        self.assertEqual([a['fields']['Name'] for a in actions],['first','second'])
        self.assertEqual(runtime.revision,world.revision)

    def make_runtime(self, host):
        world, root_key = fixture()
        runtime = PersistentClientScriptRuntime(lambda: world, 123)
        runtime.host = host
        runtime.world = world
        runtime.revision = world.revision
        runtime.script_catalog = {}
        runtime.initial_replication_complete = False
        runtime.shared_entry_count = len(world.shared)
        self.addCleanup(runtime.close)
        return runtime, world, root_key

    @staticmethod
    def touch_name(world, root_key, value):
        world.instances[root_key]['properties']['Name'] = value
        world.touch(root_key, ['Name'])

    @staticmethod
    def drain_completed(runtime):
        # Polling is intentionally nonblocking; wait only inside this test after
        # releasing its host Event until the future completion is observable.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = runtime.poll_background()
            if result is not None:
                return result
            time.sleep(.001)
        raise AssertionError('background RPC did not complete after its gate opened')

    def test_poll_background_returns_while_host_call_is_gated(self):
        started, release = threading.Event(), threading.Event()

        def gate(command):
            started.set()
            release.wait()

        host = GatedHost(gate)
        runtime, world, root_key = self.make_runtime(host)
        self.touch_name(world, root_key, b'updated')
        caller = threading.get_ident()
        response = runtime.poll_background()
        self.assertIsNone(response)
        self.assertTrue(started.wait(1))
        self.assertNotEqual(host.threads[0], caller)
        # The network/caller thread may return while the host remains blocked.
        self.assertIsNone(runtime._background_lane.take())
        release.set()
        self.assertIsNotNone(self.drain_completed(runtime))
        self.assertFalse(runtime.failure)

    def test_inflight_update_commits_only_captured_revision_and_keeps_later_actions(self):
        started, release = threading.Event(), threading.Event()
        update_count = 0
        count_lock = threading.Lock()
        second_started = threading.Event()

        def gate(command):
            nonlocal update_count
            if command['op'] != 'update':
                return
            with count_lock:
                update_count += 1
                index = update_count
            if index == 1:
                started.set()
                release.wait()
            elif index == 2:
                second_started.set()

        host = GatedHost(gate)
        runtime, world, root_key = self.make_runtime(host)
        self.touch_name(world, root_key, b'first')
        captured_revision = world.revision
        self.assertIsNone(runtime.poll_background())
        self.assertTrue(started.wait(1))
        self.touch_name(world, root_key, b'second')
        later_revision = world.revision
        release.set()
        completed = self.drain_completed(runtime)
        self.assertTrue(completed['ok'])
        self.assertEqual(runtime.revision, captured_revision)
        self.assertLess(runtime.revision, later_revision)

        # Bypass the normal 50 ms cadence to inspect the next queued receipt
        # immediately; the cursor must start after the acknowledged revision.
        runtime.last_poll = 0
        self.assertIsNone(runtime.poll_background())
        self.assertTrue(second_started.wait(1))
        second = next(call for call in host.calls if call['op'] == 'update' and
                      call['delta']['sequence'] == later_revision)
        self.assertEqual([a['fields']['Name'] for a in second['delta']['actions']], ['second'])
        self.assertEqual(second['delta']['actions'][0]['sequence'], later_revision)
        self.assertTrue(self.drain_completed(runtime)['ok'])
        self.assertEqual(runtime.revision, later_revision)

    def test_foreground_execute_drains_update_before_execution(self):
        update_started, release_update, execute_started = (
            threading.Event(), threading.Event(), threading.Event())

        def gate(command):
            if command['op'] == 'update':
                update_started.set()
                release_update.wait()
            elif command['op'] == 'execute':
                execute_started.set()

        host = GatedHost(gate)
        runtime, world, root_key = self.make_runtime(host)
        self.touch_name(world, root_key, b'changed')
        runtime.poll_background()
        self.assertTrue(update_started.wait(1))

        done = threading.Event()
        outcome = []

        def foreground():
            try:
                outcome.append(runtime.execute('return 7'))
            except Exception as error:
                outcome.append(error)
            finally:
                done.set()

        thread = threading.Thread(target=foreground)
        thread.start()
        self.assertFalse(execute_started.is_set())
        release_update.set()
        self.assertTrue(execute_started.wait(1))
        self.assertTrue(done.wait(1))
        thread.join()
        self.assertEqual([call['op'] for call in host.calls
                          if call['op'] in ('update', 'execute')], ['update', 'execute'])
        self.assertTrue(outcome[0]['ok'])
        update_index=next(i for i,call in enumerate(host.calls) if call['op']=='update')
        execute_index=next(i for i,call in enumerate(host.calls) if call['op']=='execute')
        self.assertNotEqual(host.threads[update_index], host.threads[execute_index])

    def test_chat_callbacks_and_record_run_on_caller_thread(self):
        started, release = threading.Event(), threading.Event()
        caller = threading.get_ident()
        callback_threads = []

        def gate(command):
            started.set()
            release.wait()

        host = GatedHost(gate)
        runtime, _, _ = self.make_runtime(host)

        class Chat:
            ready_sent = True

        class Bridge:
            chat = Chat()

            def runtime_submit(self, request):
                callback_threads.append(threading.get_ident())
                return {'message_id': 51}

            def runtime_status(self, message_id):
                callback_threads.append(threading.get_ident())
                return {'state': 'server_success', 'response': {'status': 'ok'}}

        runtime.chat_bridge = Bridge()
        runtime.chat_jobs['request-1'] = {
            'request': {'request_id': 'request-1'}, 'message_id': None}
        record_threads = []
        original_record = runtime._record

        def record(result):
            record_threads.append(threading.get_ident())
            return original_record(result)

        runtime._record = record
        runtime.poll_background()
        self.assertTrue(started.wait(1))
        self.assertEqual(callback_threads, [caller, caller])
        self.assertNotEqual(host.threads[0], caller)
        release.set()
        self.assertTrue(self.drain_completed(runtime)['ok'])
        self.assertEqual(record_threads, [caller])

    def test_queued_source_runs_on_singleflight_worker_and_records_on_owner(self):
        host = GatedHost()
        runtime, _, _ = self.make_runtime(host)
        caller = threading.get_ident()
        record_threads = []
        original_record = runtime._record

        def record(result):
            record_threads.append(threading.get_ident())
            return original_record(result)

        runtime._record = record
        token = runtime.queue_background_source(
            'return "animation-transition"', label='<locomotion-animation>', timeout_ms=250)
        self.assertIsInstance(token, int)
        self.assertIsNone(runtime.queue_background_source('return false'))
        self.assertIsNone(runtime.poll_background())
        self.assertTrue(host.finished.wait(1))
        self.assertNotEqual(host.threads[0], caller)
        result = self.drain_completed(runtime)
        self.assertTrue(result['ok'])
        self.assertEqual([call['op'] for call in host.calls if call['op'] == 'execute'],
                         ['execute'])
        self.assertEqual(record_threads, [caller])
        self.assertEqual(runtime.take_background_source_result(token), result)
        self.assertIsNone(runtime.take_background_source_result(token))

    def test_queued_source_waits_for_receipt_update_before_submission(self):
        update_started, release_update = threading.Event(), threading.Event()

        def gate(command):
            if command['op'] == 'update':
                update_started.set()
                release_update.wait()

        host = GatedHost(gate)
        runtime, world, root_key = self.make_runtime(host)
        self.touch_name(world, root_key, b'received-before-animation')
        token = runtime.queue_background_source('return true')
        runtime.poll_background()
        self.assertTrue(update_started.wait(1))
        self.assertEqual([call['op'] for call in host.calls], ['update'])
        release_update.set()
        self.assertTrue(self.drain_completed(runtime)['ok'])

        runtime.last_poll = 0
        runtime.poll_background()
        self.assertTrue(host.finished.wait(1))
        self.assertTrue(self.drain_completed(runtime)['ok'])
        self.assertEqual([call['op'] for call in host.calls
                          if call['op'] in ('update', 'execute')], ['update', 'execute'])
        self.assertIsNotNone(runtime.take_background_source_result(token))

    def test_source_at_captured_watermark_is_not_starved_by_continuous_new_data(self):
        update_started, release_update, execute_started, later_update_started = (
            threading.Event(), threading.Event(), threading.Event(), threading.Event())
        update_count = 0

        def gate(command):
            nonlocal update_count
            if command['op'] == 'update':
                update_count += 1
                if update_count == 1:
                    update_started.set()
                    release_update.wait()
                else:
                    later_update_started.set()
            elif command['op'] == 'execute':
                execute_started.set()

        class AnimationQueue:
            def __init__(self): self.calls = 0
            def drain(self):
                self.calls += 1
                return [{'asset_batch': self.calls}]
            def close(self): pass

        host = GatedHost(gate)
        runtime, world, root_key = self.make_runtime(host)
        runtime.animation_assets = AnimationQueue()
        pose_batches = []

        def take_poses(_world):
            pose_batches.append(len(pose_batches) + 1)
            return {'pose_batch': pose_batches[-1]}

        runtime._take_engine_poses = take_poses
        self.touch_name(world, root_key, b'captured-before-animation')
        token = runtime.queue_background_source('return "jump-track"')
        runtime.poll_background()
        self.assertTrue(update_started.wait(1))
        captured_update = next(call for call in host.calls if call['op'] == 'update')
        self.assertEqual(captured_update['delta']['animation_responses'], [{'asset_batch': 1}])
        self.assertEqual(captured_update['delta']['engine_poses'], {'pose_batch': 1})

        # Keep receiving changes while the first captured update is in flight.
        for index in range(5):
            self.touch_name(world, root_key, f'later-{index}'.encode())
        release_update.set()
        self.assertTrue(self.drain_completed(runtime)['ok'])

        runtime.last_poll = 0
        runtime.poll_background()
        self.assertTrue(execute_started.wait(1))
        self.assertEqual([call['op'] for call in host.calls
                          if call['op'] in ('update', 'execute')], ['update', 'execute'])
        # Choosing the queued source did not drain either side queue.
        self.assertEqual(runtime.animation_assets.calls, 1)
        self.assertEqual(pose_batches, [1])
        self.assertTrue(self.drain_completed(runtime)['ok'])
        self.assertIsNotNone(runtime.take_background_source_result(token))

        runtime.last_poll = 0
        runtime.poll_background()
        self.assertTrue(later_update_started.wait(1))
        later_update = next(call for call in reversed(host.calls) if call['op'] == 'update')
        self.assertEqual(later_update['delta']['animation_responses'], [{'asset_batch': 2}])
        self.assertEqual(later_update['delta']['engine_poses'], {'pose_batch': 2})
        self.assertEqual([action['fields']['Name'] for action in later_update['delta']['actions']],
                         [f'later-{index}' for index in range(5)])
        self.assertTrue(self.drain_completed(runtime)['ok'])

    def test_queued_source_is_discarded_if_own_character_changes_before_dispatch(self):
        host = GatedHost()
        runtime, world, _ = self.make_runtime(host)
        avatar = world.avatar(123)
        player_key = avatar['player_key']
        old_character = avatar['character_key']
        token = runtime.queue_background_source('return "old-character-track"')
        world.instances[player_key]['properties']['Character'] = None
        world.touch(player_key, ['Character'])
        runtime.last_poll = 0
        runtime.poll_background()
        result = runtime.take_background_source_result(token)
        self.assertEqual(result, {'ok': False, 'values': [], 'error_type': 'StaleCharacter'})
        self.assertFalse(runtime.failure)
        self.assertFalse(any(call['op'] == 'execute' for call in host.calls))
        self.assertIn(old_character, world.instances)

    def test_queued_source_error_is_delivered_without_failing_persistent_runtime(self):
        class SourceErrorHost(GatedHost):
            def call(self, command):
                with self.lock:
                    self.calls.append(command)
                    self.threads.append(threading.get_ident())
                self.finished.set()
                if command.get('op') == 'execute':
                    return {'ok': False, 'values': [], 'error_type': 'LuaSyntaxError'}
                return ok()

        host = SourceErrorHost()
        runtime, _, _ = self.make_runtime(host)
        token = runtime.queue_background_source('local =')
        runtime.poll_background()
        self.assertTrue(host.finished.wait(1))
        result = self.drain_completed(runtime)
        self.assertFalse(result['ok'])
        self.assertIsNone(runtime.failure)
        self.assertFalse(runtime.take_background_source_result(token)['ok'])

    def test_host_failure_marks_runtime_failed_without_overlapping_calls(self):
        started, release = threading.Event(), threading.Event()
        active = 0
        max_active = 0
        guard = threading.Lock()

        def gate(command):
            nonlocal active, max_active
            with guard:
                active += 1
                max_active = max(max_active, active)
            started.set()
            release.wait()
            with guard:
                active -= 1

        host = GatedHost(gate, failure=ValueError('host RPC failed'))
        runtime, world, root_key = self.make_runtime(host)
        self.touch_name(world, root_key, b'changed')
        self.assertIsNone(runtime.poll_background())
        self.assertTrue(started.wait(1))
        self.assertIsNone(runtime.poll_background())
        self.assertEqual(len(host.calls), 1)
        release.set()
        self.assertTrue(host.finished.wait(1))
        error = None
        for _ in range(10000):
            try:
                runtime.poll_background()
            except ValueError as caught:
                error = caught
                break
        self.assertIsNotNone(error)
        self.assertIn('host RPC failed', str(error))
        self.assertIn('host RPC failed', runtime.failure)
        self.assertTrue(host.closed)
        self.assertEqual(runtime.poll_background(), None)
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(max_active, 1)


if __name__ == '__main__':
    unittest.main()
