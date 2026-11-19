import copy
import unittest
from types import SimpleNamespace
from unittest import mock

import physics_runtime_prediction as physics_snapshot
from physics_runtime_prediction import (RuntimePhysicsPrediction, own_character_snapshot,
                                        own_character_monitor_snapshot,
                                        _received_surface_velocities)
from physics_ground import AABB, GroundGeometry
from mesh_asset_decoder import DecodedMeshAsset
from physics_live_monitor import PhysicsLiveMonitor
from test_world_snapshot import fixture


class RuntimePredictionTests(unittest.TestCase):
    def test_avatar_rebind_preserves_completed_session_clock_without_advancing_gap(self):
        world, _ = fixture()
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world,123,10.)
        predictor.advance(world,123,10.1)
        previous = predictor.simulation_step
        self.assertGreater(previous,0)
        predictor.clear_binding()
        self.assertEqual(predictor.simulation_step,previous)
        self.assertIsNone(predictor.bridge.controller)
        predictor.prepare(world,123,20.)
        predictor.advance(world,123,25.)
        self.assertEqual(predictor.simulation_step,previous)
        predictor.advance(world,123,25.1)
        self.assertGreater(predictor.simulation_step,previous)
        replacement,_=fixture()
        predictor.clear_binding()
        predictor.advance(replacement,123,30.)
        self.assertEqual(predictor.simulation_step,0)
        predictor.advance(replacement,123,30.1)
        predictor.clear()
        self.assertEqual(predictor.simulation_step,0)

    def test_dynamic_support_geometry_excludes_own_character_parts(self):
        world, root = fixture()
        for name, kind in [('Size', 22), ('CanCollide', 9), ('Shape', 7)]:
            world.schema['classes'][3]['properties'].append(len(world.schema['properties']))
            world.schema['properties'].append({'name': name, 'type': kind})
        world.schema['enums'] = [{'name': 'PartType'}]
        world.schema['properties'][-1]['enum'] = 0
        properties = world.instances[root]['properties']
        properties.update(Anchored=False, CanCollide=True, Size=[2., 4., 2.], Shape=1)
        properties['CFrame']['rotation_id'] = 2
        other = (1, 90)
        world.instances[other] = {'class': 3, 'parent': (1, 6), 'properties': {
            'Anchored': False, 'CanCollide': True, 'Size': [4., 2., 4.], 'Shape': 1,
            'CFrame': {'position': [20., 0., 0.], 'rotation_id': 2}}}
        world.touch(root, ['Anchored', 'CanCollide', 'Size', 'Shape', 'CFrame'])
        world.touch(other, created=True)
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)
        sources = {collider.source for collider in predictor._geometry.colliders}
        self.assertNotIn(root, sources)
        self.assertIn(other, sources)
        predictor.advance(world, 123, 10.01, [{'sequence': 1, 'kind': 'Move',
            'instance_id': '1:5', 'vector': [1., 0., 0.], 'relative_to_camera': False}])
        moved = predictor.advance(world, 123, 10.11)
        self.assertGreater(moved['predicted_position'][0], 1.)
        self.assertFalse(moved['controller']['body_collision']['initial_overlap'])

    def test_prepare_warms_caches_without_counting_load_time_as_gravity(self):
        world, _ = fixture()
        predictor = RuntimePhysicsPrediction()
        prepared = predictor.prepare(world, 123, 10.)
        first_frame = predictor.advance(world, 123, 15.)
        self.assertEqual(first_frame['predicted_position'], prepared['predicted_position'])
        self.assertEqual(first_frame['simulated_seconds'], 0.)
        second_frame = predictor.advance(world, 123, 15.05)
        self.assertLess(second_frame['predicted_position'][1], first_frame['predicted_position'][1])
        retained = predictor.prepare(world, 123, 16.)
        self.assertEqual(retained['predicted_position'], second_frame['predicted_position'])
        self.assertEqual(retained['simulated_seconds'], second_frame['simulated_seconds'])

    def test_spawn_falls_without_script_intent_and_preserves_received_world(self):
        world, root = fixture()
        before = copy.deepcopy(world.instances)
        predictor = RuntimePhysicsPrediction()
        initial = predictor.advance(world, 123, 10.)
        later = predictor.advance(world, 123, 10.1)
        self.assertLess(later['predicted_position'][1], initial['predicted_position'][1])
        self.assertEqual(world.instances, before)
        self.assertFalse(later['server_confirmed'])
        self.assertEqual(later['network_packets_sent'], 0)

    def test_refresh_anchor_stops_prediction_and_despawn_drops_controller(self):
        world, root = fixture()
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)
        world.instances[root]['properties']['Anchored'] = True
        world.touch(root, ['Anchored'])
        result = predictor.advance(world, 123, 10.1)
        self.assertIsNone(result['predicted_position'])
        world.instances[(1, 2)]['properties']['Character'] = None
        world.touch((1, 2), ['Character'])
        result = predictor.advance(world, 123, 10.2)
        self.assertFalse(result['connected'])

    def test_compact_snapshot_omits_other_players_and_code_catalog(self):
        world, root = fixture()
        world.instances[(1, 99)] = {'class': 1, 'parent': (1, 1),
                                    'properties': {'UserId': 999}}
        snapshot = own_character_snapshot(world, 123)
        self.assertEqual(len(snapshot['nodes']), 4)
        self.assertNotIn('1:99', {node['id'] for node in snapshot['nodes']})
        self.assertNotIn('script_sources', snapshot)

    def test_nested_character_descendants_are_cached_for_force_sources(self):
        world, root = fixture()
        nested = (1, 80)
        source = (1, 81)
        world.instances[nested] = {'class': 2, 'parent': root, 'properties': {}}
        world.touch(nested, created=True)
        world.instances[source] = {'class': 2, 'parent': nested, 'properties': {}}
        world.touch(source, created=True)
        snapshot = own_character_snapshot(world, 123)
        ids = {node['id'] for node in snapshot['nodes']}
        self.assertIn('1:80', ids)
        self.assertIn('1:81', ids)
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)
        self.assertIn(source, predictor._character_children)

    def test_snapshot_descendant_index_uses_receipts_and_tracks_removals(self):
        world, root = fixture()
        with mock.patch.object(physics_snapshot, '_descendant_keys',
                               wraps=physics_snapshot._descendant_keys) as scan:
            own_character_snapshot(world, 123)
            own_character_snapshot(world, 123)
            self.assertEqual(scan.call_count, 1)

            child = (1, 820)
            world.instances[child] = {'class': 2, 'parent': root, 'properties': {}}
            world.touch(child, created=True)
            own_character_snapshot(world, 123)
            self.assertEqual(scan.call_count, 2)

            world.remove_tree(child)
            snapshot = own_character_snapshot(world, 123)
            ids = {node['id'] for node in snapshot['nodes']}
            self.assertNotIn('1:820', ids)
            self.assertEqual(scan.call_count, 2)

    def test_snapshot_descendant_index_rebuilds_on_reparent_and_journal_gap(self):
        world, root = fixture()
        own_character_snapshot(world, 123)
        child = (1, 821)
        world.instances[child] = {'class': 2, 'parent': root, 'properties': {}}
        world.touch(child, created=True)
        own_character_snapshot(world, 123)

        # Moving the node out of the character subtree is reflected on the next snapshot.
        world.instances[child]['parent'] = (1, 6)
        world.touch(child, ['Parent'])
        snapshot = own_character_snapshot(world, 123)
        self.assertNotIn('1:821', {node['id'] for node in snapshot['nodes']})

        # Missing receipt history cannot be applied incrementally; rebuild from the world.
        world.actions.clear()
        world.instances[child]['parent'] = root
        world.touch(child, ['Parent'])
        snapshot = own_character_snapshot(world, 123)
        self.assertIn('1:821', {node['id'] for node in snapshot['nodes']})

    def test_snapshot_node_encodings_reuse_and_invalidate_receipted_projections(self):
        world, root = fixture()
        with mock.patch.object(physics_snapshot, '_node_snapshot',
                               wraps=physics_snapshot._node_snapshot) as encode:
            first = own_character_snapshot(world, 123)
            first_count = encode.call_count
            self.assertGreater(first_count, 0)

            second = own_character_snapshot(world, 123)
            self.assertEqual(encode.call_count, first_count)
            # Returned nodes preserve mutable snapshot behavior but are detached.
            second['nodes'][0]['properties']['cache_probe'] = True
            third = own_character_snapshot(world, 123)
            self.assertNotIn('cache_probe', third['nodes'][0]['properties'])
            self.assertEqual(encode.call_count, first_count)
            readonly = own_character_snapshot(world, 123, read_only=True)
            self.assertIsInstance(readonly['nodes'][0], dict)
            with self.assertRaises(TypeError):
                readonly['nodes'][0]['properties']['cache_probe'] = True

            world.instances[root]['properties']['Name'] = 'RenamedRoot'
            world.touch(root, ['Name'])
            changed = own_character_snapshot(world, 123)
            root_node = next(node for node in changed['nodes'] if node['id'] == '1:4')
            self.assertEqual(root_node['name'], 'RenamedRoot')
            self.assertGreater(encode.call_count, first_count)

    def test_snapshot_node_cache_clears_on_schema_instance_replacement_and_gap(self):
        world, _ = fixture()
        with mock.patch.object(physics_snapshot, '_node_snapshot',
                               wraps=physics_snapshot._node_snapshot) as encode:
            own_character_snapshot(world, 123)
            count = encode.call_count
            world.schema['properties'].append({'name': 'NewSchemaField', 'type': 1})
            own_character_snapshot(world, 123)
            self.assertGreater(encode.call_count, count)

            count = encode.call_count
            world.instances = copy.deepcopy(world.instances)
            world.instances.pop((1, 5), None)
            own_character_snapshot(world, 123)
            self.assertGreater(encode.call_count, count)

            count = encode.call_count
            world.actions.clear()
            world.revision += 1
            own_character_snapshot(world, 123)
            self.assertGreater(encode.call_count, count)

    def test_monitor_snapshot_preserves_all_physics_monitor_outputs(self):
        world, root = fixture()
        humanoid = (1, 5)
        world.instances[root]['properties'].update(
            Anchored=False, AssemblyLinearVelocity=[0., 0., 0.],
            AssemblyAngularVelocity=[0., 0., 0.])
        world.instances[humanoid]['properties'].update(WalkSpeed=16., Health=100.)
        world.touch(root, ['Anchored', 'AssemblyLinearVelocity', 'AssemblyAngularVelocity'])
        world.touch(humanoid, ['WalkSpeed'])
        full_monitor, compact_monitor = PhysicsLiveMonitor(), PhysicsLiveMonitor()
        avatar = world.avatar(123)
        for index, (height, velocity) in enumerate(((3., 10.), (4., 4.), (3.5, -8.))):
            world.instances[root]['properties']['CFrame']['position'][1] = height
            world.instances[root]['properties']['AssemblyLinearVelocity'][1] = velocity
            world.touch(root, ['CFrame', 'AssemblyLinearVelocity'])
            full = own_character_snapshot(world, 123, read_only=True)
            compact = own_character_monitor_snapshot(world, 123, avatar=avatar)
            self.assertEqual(len(compact['nodes']), 4)
            compact_root = next(node for node in compact['nodes'] if node['id'] == '1:4')
            compact_humanoid = next(node for node in compact['nodes'] if node['id'] == '1:5')
            self.assertEqual(compact_root['properties']['Anchored'], False)
            self.assertEqual(compact_root['properties']['CFrame']['$cframe']['position'][1], height)
            self.assertEqual(compact_root['properties']['AssemblyLinearVelocity'][1], velocity)
            self.assertEqual(compact_humanoid['properties']['Health'], 100.)
            self.assertEqual(full_monitor.observe(full, timestamp=index + 1),
                             compact_monitor.observe(compact, timestamp=index + 1))

    def test_runtime_applies_only_received_nested_bodyforce(self):
        world, root = fixture()
        classes = world.schema['classes']
        body_force_class = {'name': 'BodyForce', 'properties': []}
        world.schema['properties'].append({'name': 'Force', 'type': 22})
        force_property = len(world.schema['properties']) - 1
        body_force_class['properties'] = [force_property]
        classes.append(body_force_class)
        force_key = (1, 91)
        world.instances[root]['properties'].update(Anchored=False, AssemblyMass=2.)
        world.instances[force_key] = {'class': len(classes)-1, 'parent': root,
                                      'properties': {'Force': [20., 0., 0.]}}
        world.touch(root, ['Anchored', 'AssemblyMass'])
        world.touch(force_key, created=True)
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)
        moved = predictor.advance(world, 123, 10.1)['predicted_position']
        self.assertAlmostEqual(moved[0], 1.05)
        self.assertEqual(world.instances[root]['properties']['CFrame']['position'], [1., 2., 3.])

    def test_runtime_extracts_received_truss_and_applies_climbing_input(self):
        world, _ = fixture()
        world.schema['properties'].extend([
            {'name': 'Size', 'type': 22}, {'name': 'Position', 'type': 22}])
        size_index, position_index = len(world.schema['properties'])-2, len(world.schema['properties'])-1
        world.schema['classes'].append({'name': 'TrussPart',
                                        'properties': [size_index, position_index]})
        truss = (1, 92)
        world.instances[truss] = {'class': len(world.schema['classes'])-1,
            'parent': (1, 6), 'properties': {'Size': [4., 4., 4.], 'Position': [1., 2., 3.]}}
        world.touch(truss, created=True)
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)
        humanoid_id = '1:5'
        predictor.advance(world, 123, 10.1, intents=[{
            'sequence': 1, 'kind': 'Move', 'instance_id': humanoid_id, 'vector': [0., 1., 0.]}])
        result = predictor.advance(world, 123, 10.2)
        state = result['controller']['predicted_state']
        self.assertEqual(state['humanoid_state']['name'], 'Climbing')
        self.assertGreater(state['position'][1], 2.)

    def test_visual_mesh_approximation_is_opt_in_and_uses_completed_queue_assets(self):
        class OfflineQueue:
            def __init__(self):
                self.submitted = set()
                self.pending = set()
                self.cache = {}

            def submit(self, references):
                self.submitted.update(references)

            def drain(self):
                return dict(self.cache)

            def errors(self):
                return {}

        world, _ = fixture()
        world.schema['properties'].extend([
            {'name': 'MeshContent', 'type': 61}, {'name': 'CanCollide', 'type': 9},
            {'name': 'Anchored', 'type': 9}, {'name': 'size', 'type': 22},
            {'name': 'CFrame', 'type': 27}])
        mesh_properties = list(range(len(world.schema['properties']) - 5,
                                     len(world.schema['properties'])))
        world.schema['classes'].append({'name': 'MeshPart', 'properties': mesh_properties})
        mesh_key = (1, 94)
        world.instances[mesh_key] = {'class': len(world.schema['classes']) - 1,
            'parent': (1, 6), 'properties': {'MeshContent': b'rbxassetid://123',
                'Anchored': True, 'CanCollide': True, 'size': [2., 2., 2.],
                'CFrame': {'position': [5., 0., 5.], 'rotation_id': 2}}}
        world.touch(mesh_key, created=True)

        default = RuntimePhysicsPrediction()
        default.advance(world, 123, 10.)
        self.assertFalse(default.report()['visual_mesh_approximation']['enabled'])
        self.assertEqual(default.report()['ground_collider_count'], 0)

        queue = OfflineQueue()
        predictor = RuntimePhysicsPrediction(allow_visual_mesh_approximation=True,
                                             mesh_asset_queue=queue)
        first = predictor.advance(world, 123, 10.)
        self.assertIn(b'rbxassetid://123', queue.submitted)
        self.assertEqual(first['ground_collider_count'], 0)
        queue.cache[b'rbxassetid://123'] = DecodedMeshAsset(
            ((0., 0., 0.), (2., 0., 0.), (0., 0., 2.)), ((0, 1, 2),),
            'version 2.00', 'b' * 64)
        # The queue completes asynchronously; advancing drains it and rebuilds
        # geometry using only the explicitly opted-in visual approximation.
        result = predictor.advance(world, 123, 10.3)
        self.assertEqual(result['ground_collider_count'], 1)
        self.assertTrue(any('opt-in visual mesh approximation' in assumption.lower()
                            for assumption in result['geometry_assumptions']))
        self.assertTrue(result['visual_mesh_approximation']['enabled'])

    def test_persistent_runtime_config_forwards_visual_mesh_opt_in(self):
        from persistent_runtime import PersistentClientScriptRuntime
        from unittest.mock import patch
        class Preview:
            def advance(self,*args,**kwargs): pass
            def report(self): return {'accepted_intents': [], 'rejected_intents': []}
            def close(self): pass
        world,_=fixture(); preview=Preview()
        runtime=PersistentClientScriptRuntime(lambda:world,123,
            allow_visual_mesh_approximation=True)
        runtime.world=world
        with patch('persistent_runtime.RuntimePhysicsPrediction',return_value=preview) as factory:
            runtime._record({})
        self.assertTrue(runtime.allow_visual_mesh_approximation)
        self.assertTrue(factory.call_args.kwargs['allow_visual_mesh_approximation'])
        runtime.close()

    def test_world_replacement_resets_elapsed_prediction(self):
        world, _ = fixture()
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)
        predictor.advance(world, 123, 10.1)
        replacement, _ = fixture()
        result = predictor.advance(replacement, 123, 100.)
        self.assertEqual(result['simulated_seconds'], 0.)
        self.assertEqual(result['predicted_position'], [1., 2., 3.])

    def test_shape_and_replication_pv_updates_invalidate_ground_cache(self):
        for field in ('Shape', 'shape', 'NetworkShape', 'PartType',
                      'PrimitiveType', 'ReplicationPV', 'size', 'MeshContent',
                      'PhysicsData', 'SolidMeshHolder', 'AeroMeshData',
                      'PhysicalConfigData', 'Materials', 'SmoothVoxelsUpgraded'):
            with self.subTest(field=field):
                world, root = fixture()
                if field in ('ReplicationPV', 'size', 'MeshContent', 'PhysicsData',
                             'SolidMeshHolder', 'AeroMeshData', 'PhysicalConfigData',
                             'Materials', 'SmoothVoxelsUpgraded'):
                    # Pose and size are geometry inputs only for an anchored
                    # Part, matching extract_ground's collider predicate.
                    world.instances[root]['properties']['Anchored'] = True
                predictor = RuntimePhysicsPrediction()
                predictor.advance(world, 123, 10.)
                world.instances[root]['properties'][field] = (
                    {'position': [3., 4., 5.], 'rotation_id': 1}
                    if field == 'ReplicationPV' else b'asset-data'
                    if field in ('MeshContent', 'PhysicsData', 'SolidMeshHolder',
                                 'AeroMeshData', 'PhysicalConfigData', 'Materials',
                                 'SmoothVoxelsUpgraded') else 1)
                world.touch(root, [field])
                _, full_refresh, geometry_dirty = predictor._changes_since(world)
                self.assertFalse(full_refresh)
                self.assertTrue(geometry_dirty)

    def test_unanchored_avatar_pose_updates_skip_geometry_rescan(self):
        world, root = fixture()
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)
        world.instances[root]['properties']['ReplicationPV'] = {
            'position': [4., 5., 6.], 'rotation_id': 1}
        world.touch(root, ['ReplicationPV'])
        _, full_refresh, geometry_dirty = predictor._changes_since(world)
        self.assertFalse(full_refresh)
        self.assertFalse(geometry_dirty)

    def test_anchoring_change_and_then_anchored_pose_still_invalidate(self):
        world, root = fixture()
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)

        world.instances[root]['properties']['Anchored'] = True
        world.touch(root, ['Anchored'])
        _, full_refresh, geometry_dirty = predictor._changes_since(world)
        self.assertFalse(full_refresh)
        self.assertTrue(geometry_dirty)

        # Advance the journal cursor, then move the now-anchored candidate.
        predictor.advance(world, 123, 10.1)
        world.instances[root]['properties']['CFrame'] = {
            'position': [2., 3., 4.], 'rotation_id': 1}
        world.touch(root, ['CFrame'])
        _, full_refresh, geometry_dirty = predictor._changes_since(world)
        self.assertFalse(full_refresh)
        self.assertTrue(geometry_dirty)

    def test_part_subclass_creation_and_removal_invalidate_ground_cache(self):
        names = ('Seat', 'SpawnLocation', 'FlagStand', 'SkateboardPlatform')
        for index, name in enumerate(names):
            with self.subTest(class_name=name):
                world, _ = fixture()
                class_id = len(world.schema['classes'])
                world.schema['classes'].append({'name': name, 'properties': []})
                predictor = RuntimePhysicsPrediction()
                predictor.advance(world, 123, 10.)

                key = (1, 90 + index)
                world.instances[key] = {'class': class_id, 'parent': (1, 6), 'properties': {}}
                world.touch(key, created=True)
                self.assertTrue(predictor._changes_since(world)[2])
                predictor.advance(world, 123, 10.1)

                world.remove_tree(key)
                self.assertTrue(predictor._changes_since(world)[2])

    def test_part_subclass_anchored_pose_and_collision_updates_invalidate(self):
        world, _ = fixture()
        class_id = len(world.schema['classes'])
        world.schema['classes'].append({'name': 'Seat', 'properties': []})
        key = (1, 90)
        world.instances[key] = {
            'class': class_id, 'parent': (1, 6),
            'properties': {'Anchored': True, 'CanCollide': True},
        }
        world.touch(key, created=True)
        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)

        world.instances[key]['properties']['CFrame'] = {
            'position': [5., 2., 5.], 'rotation_id': 1}
        world.touch(key, ['CFrame'])
        self.assertTrue(predictor._changes_since(world)[2])
        predictor.advance(world, 123, 10.1)

        world.instances[key]['properties']['CanCollide'] = False
        world.touch(key, ['CanCollide'])
        self.assertTrue(predictor._changes_since(world)[2])

    def test_surface_velocity_requires_typed_received_collidability_and_velocity(self):
        schema = {'classes': [{'name': 'Part', 'properties': [0, 1, 2]}],
                  'properties': [{'name': 'CanCollide', 'type': 9},
                                 {'name': 'AssemblyLinearVelocity', 'type': 22},
                                 {'name': 'Velocity', 'type': 22}]}
        key = 'support'
        node = {'class': 0, 'properties': {'CanCollide': True,
            'AssemblyLinearVelocity': [3., 0., 1.], 'Velocity': [1., 0., 0.]}}
        geometry = GroundGeometry((AABB((0., 0., 0.), (1., 1., 1.), source=key),), ())
        world = SimpleNamespace(schema=schema, instances={key: node},
                                property_versions={key: {'CanCollide': 1,
                                    'Velocity': 2, 'AssemblyLinearVelocity': 3}})
        self.assertEqual(_received_surface_velocities(world, geometry)[key], (3., 0., 1.))
        world.property_versions[key].pop('CanCollide')
        self.assertNotIn(key, _received_surface_velocities(world, geometry))
        world.property_versions[key]['CanCollide'] = 4
        world.property_versions[key].pop('AssemblyLinearVelocity')
        self.assertEqual(_received_surface_velocities(world, geometry)[key], (1., 0., 0.))
        world.schema['properties'][0]['type'] = 2
        self.assertNotIn(key, _received_surface_velocities(world, geometry))

    def test_non_workspace_instances_excluded_and_reparent_refreshes(self):
        world, _ = fixture()
        world.schema['classes'].extend([
            {'name': 'ReplicatedStorage', 'properties': []},
            {'name': 'Folder', 'properties': []},
            {'name': 'Weld', 'properties': []},
        ])
        rs_cid, folder_cid, weld_cid = len(world.schema['classes']) - 3, len(world.schema['classes']) - 2, len(world.schema['classes']) - 1
        rs = (1, 100)
        folder = (1, 101)
        rs_part = (1, 102)
        rs_weld = (1, 103)
        ws_part = (1, 104)
        world.instances[rs] = {'class': rs_cid, 'parent': None, 'properties': {}}
        world.instances[folder] = {'class': folder_cid, 'parent': rs, 'properties': {}}
        world.instances[rs_part] = {
            'class': 3, 'parent': folder,
            'properties': {'Anchored': True, 'CanCollide': True,
                           'CFrame': {'position': [10., 0., 0.], 'rotation_id': 1}},
        }
        world.instances[rs_weld] = {'class': weld_cid, 'parent': folder, 'properties': {}}
        world.instances[ws_part] = {
            'class': 3, 'parent': (1, 6),
            'properties': {'Anchored': True, 'CanCollide': True,
                           'CFrame': {'position': [0., -5., 0.], 'rotation_id': 1}},
        }
        world.touch(ws_part, created=True)

        predictor = RuntimePhysicsPrediction()
        predictor.advance(world, 123, 10.)
        self.assertIn(ws_part, predictor._geometry_keys)
        self.assertNotIn(rs_part, predictor._geometry_keys)
        self.assertNotIn(rs_weld, predictor._environment_keys)

        # Mutating an RS part or creating a child under RS does not dirty geometry or env.
        world.instances[rs_part]['properties']['CFrame'] = {'position': [20., 0., 0.], 'rotation_id': 1}
        world.touch(rs_part, ['CFrame'])
        _, full_refresh, geometry_dirty = predictor._changes_since(world)
        self.assertFalse(full_refresh)
        self.assertFalse(geometry_dirty)
        self.assertFalse(predictor._env_dirty)
        predictor.advance(world, 123, 10.1)

        # Moving an anchored Workspace part sets geometry_dirty without setting _env_dirty.
        world.instances[ws_part]['properties']['CFrame'] = {'position': [1., -5., 0.], 'rotation_id': 1}
        world.touch(ws_part, ['CFrame'])
        _, full_refresh, geometry_dirty = predictor._changes_since(world)
        self.assertFalse(full_refresh)
        self.assertTrue(geometry_dirty)
        self.assertFalse(predictor._env_dirty)
        predictor.advance(world, 123, 10.4)

        # Reparenting Folder from ReplicatedStorage into Workspace picks up all descendants.
        world.instances[folder]['parent'] = (1, 6)
        world.touch(folder, ['Parent'])
        predictor.advance(world, 123, 10.5)
        self.assertIn(rs_part, predictor._geometry_keys)
        self.assertIn(rs_weld, predictor._environment_keys)

if __name__ == '__main__':
    unittest.main()
