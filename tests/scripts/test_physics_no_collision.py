"""NoCollisionConstraint exclusions in real received and authored prediction."""
import copy
import unittest
from unittest import mock
import test_cframe_transforms as transforms
from test_physics_collision_groups import received_world
from test_physics_controller import intent
from physics_runtime_prediction import RuntimePhysicsPrediction
from world_snapshot import make_world_snapshot, _node_snapshot


def ready_world(enabled=True):
    world,root=received_world(wall_group='Default')
    world.schema['classes'].append({'name':'NoCollisionConstraint','properties':[]})
    pair=(1,101)
    world.instances[pair]={'class':6,'parent':(1,6),'properties':{
        'Name':b'Pair','Enabled':enabled,'Part0':root,'Part1':(1,91)}}
    world.instances[(1,91)]['properties']['Name']=b'Wall'
    return world,root,pair


def sources(engine):return {c.source for c in engine.bridge.controller.geometry.colliders}


class PairPredictionTests(unittest.TestCase):
    def test_fresh_constraint_omitted_enabled_uses_constructor_default(self):
        world,root,pair=ready_world();world.instances[pair]['properties'].pop('Enabled')
        world.creation[pair]={'fresh':True,'complete':True,'ordinary':True}
        before=copy.deepcopy(world.instances)
        engine=RuntimePhysicsPrediction();result=engine.advance(world,123,10.)
        self.assertIsNotNone(result['predicted_position'])
        self.assertNotIn((1,91),sources(engine))
        node=_node_snapshot(world,pair,world.instances[pair])
        self.assertIs(node['properties']['Enabled'],True)
        self.assertEqual(node['origins']['Enabled'],'class_default')
        self.assertEqual(world.instances,before)

    def test_constraint_defaults_require_complete_fresh_ordinary_creation(self):
        for missing in ('fresh','complete','ordinary'):
            world,root,pair=ready_world();world.instances[pair]['properties'].pop('Enabled')
            world.creation[pair]={flag:flag!=missing for flag in ('fresh','complete','ordinary')}
            result=RuntimePhysicsPrediction().advance(world,123,10.)
            self.assertIsNone(result['predicted_position'])
            self.assertNotIn('Enabled',_node_snapshot(world,pair,world.instances[pair])['properties'])

    def test_network_constructor_defaults_allow_fresh_complete_constraint_without_ordinary(self):
        world,root,pair=ready_world();world.instances[pair]['properties'].pop('Enabled')
        world.creation[pair]={'fresh':True,'complete':True,'ordinary':False}
        engine=RuntimePhysicsPrediction(allow_network_constructor_defaults=True)
        result=engine.advance(world,123,10.)
        self.assertIsNotNone(result['predicted_position'])
        self.assertNotIn((1,91),sources(engine))

    def test_fresh_constraint_keeps_explicit_disabled_and_null_endpoint(self):
        world,root,pair=ready_world(False)
        world.creation[pair]={'fresh':True,'complete':True,'ordinary':True}
        engine=RuntimePhysicsPrediction();engine.advance(world,123,10.)
        self.assertIn((1,91),sources(engine))
        self.assertIs(_node_snapshot(world,pair,world.instances[pair])['properties']['Enabled'],False)
        world.instances[pair]['properties'].pop('Enabled')
        world.instances[pair]['properties'].pop('Part1')
        world.touch(pair,['Enabled','Part1'])
        result=engine.advance(world,123,10.01)
        self.assertIsNotNone(result['predicted_position'])
        self.assertIn((1,91),sources(engine))
        self.assertIsNone(_node_snapshot(world,pair,world.instances[pair])['properties']['Part1'])

    def test_received_pair_excludes_wall_but_keeps_other_collisions(self):
        world,root,pair=ready_world();before=copy.deepcopy(world.instances)
        engine=RuntimePhysicsPrediction();engine.advance(world,123,10.)
        self.assertNotIn((1,91),sources(engine));self.assertIn((1,90),sources(engine))
        engine.advance(world,123,10.,[intent(1,instance_id='1:5')])
        self.assertAlmostEqual(engine.advance(world,123,10.25)['predicted_position'][0],4.)
        self.assertEqual(world.instances,before)

    def test_enable_and_endpoint_changes_are_immediate(self):
        world,root,pair=ready_world(False)
        engine=RuntimePhysicsPrediction();engine.advance(world,123,10.);geometry=engine._geometry
        self.assertIn((1,91),sources(engine))
        props=world.instances[pair]['properties'];props['Enabled']=True;world.touch(pair,['Enabled'])
        engine.advance(world,123,10.01)
        self.assertIs(engine._geometry,geometry);self.assertNotIn((1,91),sources(engine))
        props['Part1']=(1,90);world.touch(pair,['Part1']);engine.advance(world,123,10.02)
        self.assertIn((1,91),sources(engine));self.assertNotIn((1,90),sources(engine))

    def test_parent_nil_and_worldmodel_constraint_do_not_register(self):
        world,root,pair=ready_world()
        world.instances[pair]['parent']=None
        engine=RuntimePhysicsPrediction();engine.advance(world,123,10.)
        self.assertIn((1,91),sources(engine))
        world.instances[pair]['parent']=root;world.touch(pair,['Parent']);engine.advance(world,123,10.01)
        self.assertNotIn((1,91),sources(engine))
        world.schema['classes'].append({'name':'WorldModel','properties':[]})
        world.instances[(1,110)]={'class':7,'parent':(1,6),'properties':{}}
        world.touch((1,110),created=True)
        world.instances[pair]['parent']=(1,110);world.touch(pair,['Parent']);engine.advance(world,123,10.02)
        self.assertIn((1,91),sources(engine))

    def test_received_create_remove_and_local_received_override(self):
        world,root,pair=ready_world();record=world.instances.pop(pair)
        engine=RuntimePhysicsPrediction();engine.advance(world,123,10.)
        self.assertIn((1,91),sources(engine))
        world.instances[pair]=record;world.touch(pair,created=True);engine.advance(world,123,10.01)
        self.assertNotIn((1,91),sources(engine))
        engine.advance(world,123,10.02,mutations=[{'kind':'set','id':'1:101','property':'Enabled','value':False}])
        self.assertIn((1,91),sources(engine))
        world.touch(pair,['Enabled']);engine.advance(world,123,10.03)
        self.assertNotIn((1,91),sources(engine))
        world.instances.pop(pair);world.touch(pair,deleted=True);engine.advance(world,123,10.04)
        self.assertIn((1,91),sources(engine))

    def test_local_destroy_of_received_constraint_persists_until_record_disappears(self):
        world,root,pair=ready_world();engine=RuntimePhysicsPrediction();engine.advance(world,123,10.)
        engine.advance(world,123,10.01,mutations=[{'kind':'destroy','ids':['1:101']}])
        self.assertIn((1,91),sources(engine))
        world.touch(root,['CFrame']);engine.advance(world,123,10.02)
        self.assertIn((1,91),sources(engine))
        world.instances.pop(pair);world.touch(pair,deleted=True);engine.advance(world,123,10.03)
        self.assertNotIn('1:101',engine.bridge._force_state.removed)

    def test_missing_enabled_or_endpoint_suspends_instead_of_ignoring_pair(self):
        world,root,pair=ready_world();world.instances[pair]['properties'].pop('Enabled')
        engine=RuntimePhysicsPrediction();result=engine.advance(world,123,10.)
        self.assertIsNone(result['predicted_position'])
        self.assertIn('NoCollisionConstraint.Enabled',result['controller']['collision_filter']['error'])
        world.instances[pair]['properties']['Enabled']=True
        world.instances[pair]['properties']['Part1']=(9,99)
        world.touch(pair,['Enabled','Part1']);result=engine.advance(world,123,10.01)
        self.assertIn('unresolved',result['controller']['collision_filter']['error'])

    def test_pose_updates_do_not_refilter_unchanged_constraint_topology(self):
        world,root,pair=ready_world();engine=RuntimePhysicsPrediction();engine.advance(world,123,10.)
        old=engine.bridge.controller.geometry
        world.touch(root,['CFrame']);engine.advance(world,123,10.01)
        self.assertIs(engine.bridge.controller.geometry,old)


class NativePairBridgeTests(unittest.TestCase):
    run_script=transforms.CFrameTransformTests.run_script

    def test_real_luau_constraint_create_and_destroy_changes_walk_collisions(self):
        world,root,pair=ready_world(False);world.instances.pop(pair)
        before=copy.deepcopy(world.instances)
        results=self.run_script('''
local root=game:GetService("Players").LocalPlayer.Character.HumanoidRootPart
local pair=Instance.new("NoCollisionConstraint",workspace)
pair.Part0=root;pair.Part1=workspace.Wall
assert(#root:GetNoCollisionConstraints()==1)
''',make_world_snapshot(world,123))
        for result in results:
            engine=RuntimePhysicsPrediction();engine.advance(world,123,10.)
            engine.advance(world,123,10.01,mutations=result['mutations'])
            self.assertNotIn((1,91),sources(engine))
            local_id=next(k for k,n in engine.bridge._force_state.local_nodes.items() if n['class_name']=='NoCollisionConstraint')
            engine.advance(world,123,10.02,mutations=[{'kind':'destroy','ids':[local_id]}])
            self.assertIn((1,91),sources(engine))
        self.assertEqual(world.instances,before)


if __name__=='__main__':unittest.main()
