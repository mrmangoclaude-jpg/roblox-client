from concurrent.futures import Future
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests' / 'scripts'))

import persistent_runtime
from persistent_runtime import PersistentClientScriptRuntime
from test_startup_runtime_budget import FakeHost, fake_world, ready_runtime
from world_snapshot import make_world_snapshot


def _schema_world():
    classes = [
        {'name': 'ReplicatedStorage', 'properties': []},
        {'name': 'Folder', 'properties': [0]},
        {'name': 'LocalScript', 'properties': [0]},
        {'name': 'Attachment', 'properties': [0]},
        {'name': 'MeshPart', 'properties': [0]},
        {'name': 'Workspace', 'properties': []},
        {'name': 'Part', 'properties': [0]},
    ]
    cls_idx = {c['name']: i for i, c in enumerate(classes)}
    props = [{'name': 'Name', 'type': 1}]
    instances = {
        (1, 1): {'class': cls_idx['ReplicatedStorage'], 'parent': None, 'properties': {'Name': b'ReplicatedStorage'}},
        (1, 2): {'class': cls_idx['Folder'], 'parent': (1, 1), 'properties': {'Name': b'Models'}},
        (1, 3): {'class': cls_idx['MeshPart'], 'parent': (1, 2), 'properties': {'Name': b'VisualMesh'}},
        (1, 4): {'class': cls_idx['Attachment'], 'parent': (1, 3), 'properties': {'Name': b'RigAttach'}},
        (1, 5): {'class': cls_idx['Folder'], 'parent': (1, 2), 'properties': {'Name': b'ScriptedFolder'}},
        (1, 6): {'class': cls_idx['LocalScript'], 'parent': (1, 5), 'properties': {'Name': b'KeepMe'}},
        (1, 7): {'class': cls_idx['Attachment'], 'parent': (1, 6), 'properties': {'Name': b'ScriptAttach'}},
        (1, 8): {'class': cls_idx['Workspace'], 'parent': None, 'properties': {'Name': b'Workspace'}},
        (1, 9): {'class': cls_idx['Attachment'], 'parent': (1, 8), 'properties': {'Name': b'WorkspaceAttach'}},
    }
    return SimpleNamespace(
        revision=9,
        tags=[13],
        shared={},
        actions=[],
        instances=instances,
        top_containers={(1, 1): instances[(1, 1)], (1, 8): instances[(1, 8)]},
        schema={'classes': classes, 'properties': props, 'events': []},
        creation={k: {'fresh': True, 'complete': True, 'ordinary': True} for k in instances},
        property_versions={},
        avatar=lambda user_id: {'player_key': None, 'character_key': None},
    )


class OversizedWorldSupportTests(unittest.TestCase):
    def test_snapshot_includes_place_and_game_ids_only_when_provided(self):
        world = _schema_world()
        world.instances[(1, 10)] = {
            'class': 5, 'parent': None, 'properties': {'Name': b'Players'}
        }
        world.schema['classes'].append({'name': 'Player', 'properties': [0]})
        world.instances[(1, 11)] = {
            'class': len(world.schema['classes']) - 1,
            'parent': (1, 10),
            'properties': {'Name': b'Hero', 'UserId': 123},
        }
        world.creation[(1, 10)] = {'fresh': True, 'complete': True, 'ordinary': True}
        world.creation[(1, 11)] = {'fresh': True, 'complete': True, 'ordinary': True}
        world.avatar = lambda user_id: {'player_key': (1, 11), 'character_key': None}

        plain = make_world_snapshot(world, 123, include_script_sources=False)
        plain_game = next(n for n in plain['nodes'] if n['id'] == 'game')
        self.assertNotIn('PlaceId', plain_game['properties'])
        self.assertNotIn('GameId', plain_game['properties'])

        with_ids = make_world_snapshot(
            world, 123, job_id='job-1', place_id=109983668079237, game_id=7709344486,
            include_script_sources=False,
        )
        game_node = next(n for n in with_ids['nodes'] if n['id'] == 'game')
        self.assertEqual(game_node['properties']['JobId'], 'job-1')
        self.assertEqual(game_node['properties']['PlaceId'], 109983668079237)
        self.assertEqual(game_node['properties']['GameId'], 7709344486)
        self.assertEqual(game_node['origins']['PlaceId'], 'issued_session')
        self.assertEqual(game_node['origins']['GameId'], 'issued_session')

    def test_snapshot_excluded_ids_and_max_nodes(self):
        world = _schema_world()
        world.avatar = lambda user_id: {'player_key': (1, 1), 'character_key': None}
        snap = make_world_snapshot(
            world, 123, include_script_sources=False,
            max_nodes=8, excluded_ids={(1, 3), (1, 4)},
        )
        ids = {n['id'] for n in snap['nodes']}
        self.assertNotIn('1:3', ids)
        self.assertNotIn('1:4', ids)
        self.assertIn('1:6', ids)

    def test_script_catalog_is_chunked_without_releasing_initial_ready_early(self):
        world = fake_world(revision=5, tags=[])
        runtime = ready_runtime(world, budget=30)
        world.tags.append(13)
        # Exceed _SCRIPT_CHUNK_MAX_ENTRIES (1024) so delivery splits cleanly into 2 batches
        large_catalog = {f'1:{i}': {'source': 'return 1'} for i in range(1, 1505)}

        with patch.object(persistent_runtime, 'script_catalog', return_value=large_catalog) as cat_mock:
            first = runtime.poll(force=True)
            self.assertTrue(first['ok'])
            second = runtime.poll(force=True)
            self.assertTrue(second['ok'])
            cat_mock.assert_called_once_with(world)

        update_calls = [c['delta'] for c in runtime.host.calls if c['op'] == 'update']
        self.assertEqual(len(update_calls), 2)
        self.assertEqual(len(update_calls[0]['script_sources']), 1024)
        self.assertFalse(update_calls[0]['initial_replication_complete'])
        self.assertEqual(len(update_calls[1]['script_sources']), 480)
        self.assertTrue(update_calls[1]['initial_replication_complete'])
        self.assertTrue(runtime.initial_replication_complete)
        self.assertIsNone(runtime._pending_script_catalog)
        self.assertEqual(len(runtime.script_catalog), 1504)
        runtime.close()

    def test_decorative_rs_pruning_only_triggers_above_threshold_and_preserves_scripts_and_workspace(self):
        world = _schema_world()
        runtime = ready_runtime(world, budget=30)
        actions = [
            {'kind': 'create', 'id': '1:3', 'node': {'id': '1:3', 'class_name': 'MeshPart', 'parent': '1:2'}},
            {'kind': 'create', 'id': '1:4', 'node': {'id': '1:4', 'class_name': 'Attachment', 'parent': '1:3'}},
            {'kind': 'create', 'id': '1:6', 'node': {'id': '1:6', 'class_name': 'LocalScript', 'parent': '1:5'}},
            {'kind': 'create', 'id': '1:9', 'node': {'id': '1:9', 'class_name': 'Attachment', 'parent': '1:8'}},
            {'kind': 'set', 'id': '1:4', 'fields': {'Visible': False}},
            {'kind': 'set', 'id': '1:9', 'fields': {'Visible': False}},
        ]
        # Below threshold: nothing pruned
        unfiltered = runtime._filter_oversized_actions(world, actions)
        self.assertEqual([a['id'] for a in unfiltered], ['1:3', '1:4', '1:6', '1:9', '1:4', '1:9'])

        # Simulate > 25,000 instances
        for extra in range(100, 25120):
            world.instances[(2, extra)] = {'class': 1, 'parent': (1, 1), 'properties': {'Name': b'Extra'}}
        runtime._vm_protected_ancestors = None
        filtered = runtime._filter_oversized_actions(world, actions)
        self.assertEqual([a['id'] for a in filtered], ['1:6', '1:9', '1:9'])
        self.assertIn('1:3', runtime._vm_pruned_ids)
        self.assertIn('1:4', runtime._vm_pruned_ids)
        self.assertNotIn('1:6', runtime._vm_pruned_ids)
        self.assertNotIn('1:9', runtime._vm_pruned_ids)
        runtime.close()

    def test_world_update_single_pass_pruning_skips_decorative_records(self):
        world = _schema_world()
        for extra in range(100, 25120):
            world.instances[(2, extra)] = {'class': 1, 'parent': (1, 1), 'properties': {'Name': b'Extra'}}
        world.actions = [
            {
                'sequence': 10, 'kind': 'create', 'key': (1, 3),
                'instance': world.instances[(1, 3)],
                'creation': world.creation[(1, 3)], 'property_revisions': {},
            },
            {
                'sequence': 11, 'kind': 'create', 'key': (1, 4),
                'instance': world.instances[(1, 4)],
                'creation': world.creation[(1, 4)], 'property_revisions': {},
            },
            {
                'sequence': 12, 'kind': 'create', 'key': (1, 6),
                'instance': world.instances[(1, 6)],
                'creation': world.creation[(1, 6)], 'property_revisions': {},
            },
            {
                'sequence': 13, 'kind': 'set', 'key': (1, 4),
                'class': world.instances[(1, 4)]['class'],
                'fields': {'Name': b'PrunedSet'},
            },
        ]
        world.revision = 13
        runtime = ready_runtime(world, budget=30)
        runtime.revision = 9
        delta, initial_ready, _, caught_up = runtime._world_update(world)
        self.assertEqual([a['id'] for a in delta['actions']], ['1:6'])
        self.assertEqual(delta['sequence'], 13)
        self.assertTrue(caught_up)
        self.assertTrue(initial_ready)
        self.assertIn('1:3', runtime._vm_pruned_ids)
        self.assertIn('1:4', runtime._vm_pruned_ids)
        self.assertNotIn('1:6', runtime._vm_pruned_ids)
        runtime.close()

    def test_large_pruned_delta_defers_script_catalog_in_synchronize_and_poll_background(self):
        actions = [{'sequence': 10, 'kind': 'set', 'id': 'scope:part', 'fields': {'Name': 'X'}}] * 70
        for mode in ('synchronize', 'poll_background'):
            world = fake_world(revision=5, tags=[])
            runtime = ready_runtime(world, budget=30)
            runtime._vm_pruned_ids = {'1:99'}
            world.revision = 10
            world.tags.append(13)

            def fake_delta(w, seq, **kw):
                return {'version': 1, 'delta': True, 'sequence': 10,
                        'actions': (list(actions) if seq < 10 else [])}

            try:
                with patch.object(persistent_runtime, 'make_world_delta', side_effect=fake_delta), \
                     patch.object(persistent_runtime, 'script_catalog',
                                  return_value={'scope:script': {'source': 'return 1'}}) as cat_mock:
                    if mode == 'synchronize':
                        runtime.synchronize()
                    else:
                        runtime.last_poll = 0.0
                        runtime.poll_background()
                        runtime._finish_background(wait=True)
                        runtime.last_poll = 0.0
                        runtime.poll_background()
                        runtime._finish_background(wait=True)
                    cat_mock.assert_called_once_with(world)

                update_calls = [c['delta'] for c in runtime.host.calls if c['op'] == 'update']
                self.assertEqual(len(update_calls), 2, mode)
                self.assertEqual(len(update_calls[0]['actions']), 70, mode)
                self.assertNotIn('script_sources', update_calls[0], mode)
                self.assertFalse(update_calls[0]['initial_replication_complete'], mode)
                self.assertEqual(update_calls[1]['actions'], [], mode)
                self.assertEqual(update_calls[1]['script_sources'], {'scope:script': {'source': 'return 1'}}, mode)
                self.assertTrue(update_calls[1]['initial_replication_complete'], mode)
                self.assertTrue(runtime.initial_replication_complete, mode)
                self.assertFalse(runtime._catalog_catchup_needed, mode)
            finally:
                runtime.close()

    def test_world_update_bounds_pruned_batch_to_384_once_scripts_active(self):
        world = _schema_world()
        world.revision = 10
        runtime = ready_runtime(world, budget=30)
        runtime.revision = 9
        runtime._vm_pruned_ids = {'1:99'}
        captured = []

        def fake_delta(w, seq, **kw):
            captured.append((kw.get('max_actions'), kw.get('max_bytes')))
            return {'version': 1, 'delta': True, 'sequence': 10, 'actions': []}

        try:
            with patch.object(persistent_runtime, 'make_world_delta', side_effect=fake_delta):
                runtime.initial_replication_complete = False
                runtime.stats['script_runtime'] = {}
                runtime._world_update(world)

                runtime.initial_replication_complete = True
                runtime._world_update(world)

                runtime.initial_replication_complete = False
                runtime.stats['script_runtime'] = {'modules_loaded': 1}
                runtime._world_update(world)

            self.assertEqual(captured, [
                (1536, 1536 * 1024),
                (384, 384 * 1024),
                (384, 384 * 1024),
            ])
        finally:
            runtime.close()

    def test_catalog_needs_refresh_coalesces_partial_queue_completions(self):
        world = _schema_world()
        runtime = ready_runtime(world, budget=30)
        pending = {}
        for i in range(20):
            fut = Future()
            if i == 0:
                fut.set_result(None)
            pending[(1, 100 + i)] = ({}, fut)
        world._script_preparation_queue = SimpleNamespace(pending=pending, close=lambda: None)
        try:
            runtime.initial_replication_complete = True
            runtime.shared_entry_count = 0
            runtime._last_catalog_queue_refresh = time.monotonic()

            self.assertTrue(runtime._catalog_needs_refresh(
                world, {'actions': []}, True, coalesce_queue=False))
            self.assertFalse(runtime._catalog_needs_refresh(
                world, {'actions': []}, True, coalesce_queue=True))

            runtime._last_catalog_queue_refresh = time.monotonic() - 0.5
            self.assertTrue(runtime._catalog_needs_refresh(
                world, {'actions': []}, True, coalesce_queue=True))

            runtime._last_catalog_queue_refresh = time.monotonic()
            for _, fut in pending.values():
                if not fut.done():
                    fut.set_result(None)
            self.assertTrue(runtime._catalog_needs_refresh(
                world, {'actions': []}, True, coalesce_queue=True))
        finally:
            runtime.close()

    def test_pre_initial_replication_partial_catchup_does_not_release_script_catalog_early(self):
        world = _schema_world()
        world.tags.clear()
        world.revision = 5
        runtime = ready_runtime(world, budget=30)
        runtime.revision = 1
        runtime.initial_replication_complete = False
        world.revision = 10

        batches = [
            {'version': 1, 'delta': True, 'sequence': 7,
             'actions': [{'sequence': 7, 'kind': 'set', 'id': 'scope:part', 'fields': {'Name': 'A'}}]},
            {'version': 1, 'delta': True, 'sequence': 10,
             'actions': [{'sequence': 10, 'kind': 'set', 'id': 'scope:part', 'fields': {'Name': 'B'}}]},
            {'version': 1, 'delta': True, 'sequence': 15,
             'actions': [{'sequence': 15, 'kind': 'set', 'id': 'scope:part', 'fields': {'Name': 'C'}}]},
        ]
        idx = {'i': 0}

        def fake_delta(w, seq, **kw):
            batch = batches[idx['i']]
            idx['i'] += 1
            return batch

        try:
            with patch.object(persistent_runtime, 'make_world_delta', side_effect=fake_delta), \
                 patch.object(persistent_runtime, 'script_catalog',
                              return_value={'1:2': {'source': 'return 1'}}) as cat_mock:
                # Synchronize before tag 13 across chunked batches: must not call script_catalog or latch catchup
                runtime.synchronize()
                cat_mock.assert_not_called()
                self.assertFalse(runtime._catalog_catchup_needed)
                self.assertFalse(runtime.initial_replication_complete)

                # Tag 13 arrives: next synchronize must load the catalog and complete initial replication
                world.revision = 15
                world.tags.append(13)
                runtime.synchronize()
                cat_mock.assert_called_once_with(world)
                self.assertTrue(runtime.initial_replication_complete)
        finally:
            runtime.close()


if __name__ == '__main__':
    unittest.main()
