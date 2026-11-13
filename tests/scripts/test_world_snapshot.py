import copy
import struct
import unittest

from game_wire import encode_unsigned
from wire_reader import Reader
from world_replication import World
from world_snapshot import make_world_snapshot, make_world_delta


def fixture():
    names = ['Players', 'Player', 'Model', 'Part', 'Humanoid', 'Workspace']
    schema = {'classes': [{'name': n, 'properties': []} for n in names],
              'properties': [{'name': 'Character', 'type': 28},
                             {'name': 'PrimaryPart', 'type': 28},
                             {'name': 'Name', 'type': 2}, {'name': 'Anchored', 'type': 9},
                             {'name': 'CFrame', 'type': 27}]}
    schema['classes'][1]['properties'] = [0]
    schema['classes'][2]['properties'] = [1]
    schema['classes'][3]['properties'] = [2, 3, 4]
    w = World(schema)
    players, player, model, root, humanoid, workspace = [(1, n) for n in range(1, 7)]
    w.instances = {
        players: {'class': 0, 'parent': None, 'properties': {}},
        player: {'class': 1, 'parent': players, 'properties': {'UserId': 123, 'Character': model}},
        model: {'class': 2, 'parent': workspace, 'properties': {'PrimaryPart': root}},
        humanoid: {'class': 4, 'parent': model, 'properties': {}},
        workspace: {'class': 5, 'parent': None, 'properties': {}},
    }
    w.top_containers = {players: {}, workspace: {}}
    def guid(key): return encode_unsigned(key[0]) + struct.pack('<I', key[1])
    name = b'HumanoidRootPart'
    packet = guid(root) + struct.pack('<H', 3) + b'\0' + encode_unsigned(len(name)) + name
    packet += b'\xff\xff' + guid(model)
    w.new_instance(Reader(packet))
    w.instances[root]['properties']['CFrame'] = {'position': [1., 2., 3.], 'rotation_id': 1}
    return w, root


class WorldSnapshotTests(unittest.TestCase):
    def test_private_collision_group_exports_name_and_revision_without_mutation(self):
        w,key=fixture()
        w.instances[key]['properties']['CollisionGroupReplicate']=b'\x01Ghost'
        w.touch(key,['CollisionGroupReplicate'])
        before=copy.deepcopy(w.instances)
        node=self.node(make_world_snapshot(w,123),key)
        self.assertEqual(node['properties']['CollisionGroup'],'Ghost')
        self.assertEqual(node['origins']['CollisionGroup'],'derived_received')
        self.assertEqual(node['property_revisions']['CollisionGroup'],w.revision)
        self.assertEqual(w.instances,before)
        w.instances[key]['properties']['CollisionGroupReplicate']=b'\x01\xff'
        node=self.node(make_world_snapshot(w,123),key)
        self.assertNotIn('CollisionGroup',node['properties'])
        self.assertEqual(node['properties']['CollisionGroupReplicate'],{'$bytes_hex':'01ff'})

    def test_collision_group_binary_survives_snapshot_and_delta(self):
        # Masks commonly contain non-UTF-8 bytes. Neither export path may
        # decode them lossily or silently invent a Default-only matrix.
        w, _ = fixture()
        key = (1, 6)
        initial = bytes.fromhex('01010004ffffffff0744656661756c74')
        w.instances[key]['properties']['CollisionGroupData'] = initial
        before = copy.deepcopy(w.instances)
        node = self.node(make_world_snapshot(w, 123), key)
        self.assertEqual(node['properties']['CollisionGroupData'], {'$bytes_hex':initial.hex()})
        self.assertEqual(node['origins']['CollisionGroupData'], 'received')
        self.assertEqual(w.instances, before)
        cursor = w.revision
        # A zero mask is valid UTF-8 binary data and uses the string export.
        updated = bytes.fromhex('01010004000000000744656661756c74')
        w.instances[key]['properties']['CollisionGroupData'] = updated
        w.touch(key, ['CollisionGroupData'])
        delta = make_world_delta(w, cursor)
        field = delta['actions'][0]['fields']['CollisionGroupData']
        self.assertEqual(field.encode('utf-8'), updated)
        self.assertEqual(w.instances[key]['properties']['CollisionGroupData'], updated)

    def test_exported_pose_is_detached_from_the_received_vector(self):
        w, key = fixture()
        node = self.node(make_world_snapshot(w, 123), key)
        w.instances[key]['properties']['CFrame']['position'][0] = 99.
        self.assertEqual(node['properties']['Position']['$vector3'], [1.,2.,3.])
        self.assertEqual(node['properties']['CFrame']['$cframe']['position'], [1.,2.,3.])

    def test_network_size_vector_is_available_through_canonical_size(self):
        w, key = fixture()
        pi = len(w.schema['properties'])
        w.schema['properties'].append({'name':'size','type':22})
        w.schema['classes'][3]['properties'].append(pi)
        w.instances[key]['properties']['size'] = [2., 3., 1.]
        node = self.node(make_world_snapshot(w, 123), key)
        self.assertEqual(node['properties']['Size'], {'$vector3':[2.,3.,1.]})
        self.assertEqual(node['origins']['Size'], 'derived_received')
        self.assertNotIn('Size', w.instances[key]['properties'])

    def test_received_identity_orientation_is_available_to_luau_without_mutating_wire(self):
        w, key = fixture()
        w.instances[key]['properties']['CFrame']['rotation_id'] = 2
        before = copy.deepcopy(w.instances)
        frame = self.node(make_world_snapshot(w, 123), key)['properties']['CFrame']['$cframe']
        self.assertEqual(frame['rotation'], [1.,0.,0.,0.,1.,0.,0.,0.,1.])
        self.assertEqual(frame['rotation_selector'], 2)
        self.assertEqual(w.instances, before)

    def node(self, snapshot, key):
        return next(n for n in snapshot['nodes'] if n['id'] == f'{key[0]}:{key[1]}')

    def test_fresh_complete_creation_reconstructs_verified_class_default(self):
        w, key = fixture()
        self.assertNotIn('Anchored', w.instances[key]['properties'])
        node = self.node(make_world_snapshot(w, 123), key)
        self.assertIs(node['properties']['Anchored'], False)
        self.assertEqual(node['origins']['Anchored'], 'class_default')
        self.assertEqual(node['properties']['Position'], {'$vector3': [1., 2., 3.]})

    def test_explicit_values_override_defaults_without_altering_wire_dictionary(self):
        w, key = fixture()
        w.instances[key]['properties']['Anchored'] = True
        before = copy.deepcopy(w.instances)
        node = self.node(make_world_snapshot(w, 123), key)
        self.assertIs(node['properties']['Anchored'], True)
        self.assertEqual(node['origins']['Anchored'], 'received')
        self.assertEqual(w.instances, before)

    def test_incomplete_reused_and_unmeasured_creation_do_not_guess(self):
        for field in ('fresh', 'complete', 'ordinary'):
            w, key = fixture()
            w.creation[key][field] = False
            self.assertNotIn('Anchored', self.node(make_world_snapshot(w, 123), key)['properties'])

    def test_fresh_single_list_creation_preserves_constructor_provenance(self):
        w, _ = fixture()
        key, parent = (1, 80), (1, 6)
        guid = lambda value: encode_unsigned(value[0]) + struct.pack('<I', value[1])
        packet = guid(key) + struct.pack('<H', 3) + b'\xff' + guid(parent)
        w.new_instance(Reader(packet), lists=1, inline_shared=False)
        before = copy.deepcopy(w.instances)
        node = self.node(make_world_snapshot(w, 123), key)
        self.assertTrue(node['constructor_defaults_known'])
        self.assertFalse(w.creation[key]['ordinary'])
        self.assertEqual(w.instances, before)
        self.assertNotIn('Massless', node['properties'])
        for field in ('fresh', 'complete'):
            saved = w.creation[key][field]
            w.creation[key][field] = False
            self.assertFalse(self.node(make_world_snapshot(w, 123), key)['constructor_defaults_known'])
            w.creation[key][field] = saved

    def test_local_player_services_and_forward_references_are_preserved(self):
        w, key = fixture()
        snapshot = make_world_snapshot(w, 123)
        self.assertEqual(snapshot['local_player'], '1:2')
        self.assertEqual(snapshot['services']['Players'], '1:1')
        self.assertEqual(self.node(snapshot, (1, 2))['properties']['Character'], {'$ref': '1:3'})
        self.assertEqual(self.node(snapshot, (1, 3))['properties']['PrimaryPart'], {'$ref': '1:4'})
        self.assertEqual(self.node(snapshot, (1, 6))['parent'], 'game')

    def test_receipt_journal_preserves_intermediate_values(self):
        w,key=fixture();cursor=w.revision
        for name in (b'first',b'second'):
            w.instances[key]['properties']['Name']=name;w.touch(key,['Name'])
        delta=make_world_delta(w,cursor)
        self.assertEqual([a['fields']['Name'] for a in delta['actions']],['first','second'])
        self.assertLess(delta['actions'][0]['sequence'],delta['actions'][1]['sequence'])

    def test_latest_received_physics_frame_drives_source_pose(self):
        w,key=fixture()
        w.instances[key]['properties']['ReplicationPV']={'position':[4.,5.,6.], 'rotation_id':1}
        w.touch(key,['ReplicationPV'])
        node=self.node(make_world_snapshot(w,123),key)
        self.assertEqual(node['properties']['Position'],{'$vector3':[4.,5.,6.]})
        self.assertEqual(node['properties']['CFrame']['$cframe']['position'],[4.,5.,6.])
        self.assertEqual(node['origins']['CFrame'],'derived_received')
        self.assertEqual(w.instances[key]['properties']['CFrame']['position'],[1.,2.,3.])

    def test_journal_overrun_is_reported_instead_of_silently_losing_events(self):
        import collections
        w,key=fixture();cursor=w.revision;w.actions=collections.deque(maxlen=1)
        w.touch(key,['Name']);w.touch(key,['Name'])
        with self.assertRaisesRegex(ValueError,'overrun'):make_world_delta(w,cursor)

    def test_snapshot_exposes_client_services_and_known_defaults(self):
        w, _ = fixture()
        snapshot = make_world_snapshot(w, 123)
        self.assertIn('ContentProvider', snapshot['services'])
        self.assertIn('PathfindingService', snapshot['services'])
        self.assertIsNone(snapshot['defaults']['Player']['Character'])
        self.assertEqual(snapshot['defaults']['Player']['CameraMinZoomDistance'], 0.5)
        self.assertEqual(snapshot['defaults']['Player']['CameraMaxZoomDistance'], 400.0)
        self.assertEqual(snapshot['default_origins']['ScreenGui']['ZIndexBehavior'], 'class_default')


if __name__ == '__main__':
    unittest.main()
