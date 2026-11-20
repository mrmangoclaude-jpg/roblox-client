import struct
import unittest

from game_wire import encode_unsigned
from world_replication import World


class CountedInstances(dict):
    scans = 0

    def items(self):
        self.scans += 1
        return super().items()


class RemovalBatchTests(unittest.TestCase):
    def world(self, parents):
        world=World({'classes':[{'name':'Folder'}]})
        world.instances=CountedInstances({key:{'class':0,'parent':parent,'properties':{}}
                                          for key,parent in parents.items()})
        return world

    def test_large_batched_removal_indexes_world_once(self):
        roots=[(1,i) for i in range(1,10001)]
        world=self.world({**{key:None for key in roots}, (2,1):None})
        packet=b'\x83\x1b'+struct.pack('<I',len(roots))
        packet+=b''.join(encode_unsigned(k[0])+struct.pack('<I',k[1]) for k in roots)+b'\0'
        world.packet(packet)
        self.assertEqual(set(world.instances),{(2,1)})
        self.assertEqual(world.instances.scans,1)
        self.assertEqual([a['key'] for a in world.actions],roots)
        self.assertEqual(world.revision,10000)

    def test_overlapping_roots_remove_descendants_once_and_preserve_root_order(self):
        world=self.world({(1,1):None,(1,2):(1,1),(1,3):(1,2),(1,4):None})
        world.creation={key:{} for key in world.instances}
        world.property_versions={key:{} for key in world.instances}
        world.remove_trees([(1,2),(1,1),(1,2)])
        self.assertEqual([a['key'] for a in world.actions],[(1,2),(1,3),(1,1)])
        self.assertEqual(set(world.creation),{(1,4)})
        self.assertEqual(set(world.property_versions),{(1,4)})

    def test_consecutive_packets_reuse_index_and_reparent_keeps_it_current(self):
        # The index used to be discarded on a reparent, so every later removal rescanned the whole world.
        world=self.world({(1,i):None for i in range(1,201)})
        for i in range(1,101):world.remove_tree((1,i))
        self.assertEqual(world.instances.scans,1)
        world.instances[(1,200)]['parent']=(1,199)
        world.touch((1,200),['Parent'])
        world.remove_tree((1,199))
        self.assertEqual(world.instances.scans,1)
        self.assertNotIn((1,200),world.instances)
        self.assertIn((1,150),world.instances)

    def test_creation_keeps_cached_index_current(self):
        world=self.world({(1,1):None,(1,2):None})
        world.remove_tree((1,1))
        world.instances[(1,3)]={'class':0,'parent':(1,2),'properties':{}}
        world.touch((1,3),created=True)
        world.remove_tree((1,2))
        self.assertFalse(world.instances)
        self.assertEqual(world.instances.scans,1)

    def test_a_reparented_instance_is_no_longer_removed_with_its_old_parent(self):
        world=self.world({(1,1):None,(1,2):(1,1),(1,3):None})
        world.remove_tree((1,3))   # builds the index
        world.instances[(1,2)]['parent']=(1,3+10)
        world.instances[(1,13)]={'class':0,'parent':None,'properties':{}}
        world.touch((1,13),created=True)
        world.touch((1,2),['Parent'])
        world.remove_tree((1,1))
        self.assertEqual(set(world.instances),{(1,2),(1,13)})
        world.remove_tree((1,13))
        self.assertFalse(world.instances)

    def test_empty_removals_do_not_scan_the_world(self):
        world=self.world({(1,1):None})
        world.remove_trees([]);world.remove_tree(None)
        self.assertEqual(world.instances.scans,0)
        self.assertEqual(world.revision,0)

    def test_missing_root_still_removes_received_children_and_cycles_terminate(self):
        world=self.world({(1,2):(1,1),(1,3):(1,2),(1,4):(1,5),(1,5):(1,4)})
        world.remove_trees([None,(1,1),(1,4)])
        self.assertFalse(world.instances)
        self.assertEqual(world.revision,4)


if __name__ == '__main__':unittest.main()
