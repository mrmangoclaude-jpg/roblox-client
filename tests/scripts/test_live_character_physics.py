"""Continuous own-root gravity policy contracts."""
import unittest

from live_character_physics import LiveCharacterPhysics
from physics_runtime_prediction import RuntimePhysicsPrediction
from test_live_physics_trial import PredictionStub, ready_world


class TrackingPrediction(PredictionStub):
    def __init__(self):
        super().__init__()
        self.clears = 0

    def clear(self):
        self.clears += 1


class LiveCharacterPhysicsTests(unittest.TestCase):
    def test_visual_mesh_approximation_is_forwarded_to_prediction_queue(self):
        from unittest.mock import patch
        with patch('live_character_physics.RuntimePhysicsPrediction') as prediction:
            LiveCharacterPhysics(allow_visual_mesh_approximation=True)
        prediction.assert_called_once_with(allow_network_constructor_defaults=False,
                                          allow_visual_mesh_approximation=True)

    def test_initial_bind_starts_at_received_pose_then_falls_without_intent(self):
        from physics_runtime_prediction import RuntimePhysicsPrediction
        world, root = ready_world()
        world.instances[root]['properties']['CFrame']['position'] = [0., 100., 0.]
        world.touch(root, ['CFrame'])
        prediction = RuntimePhysicsPrediction()
        # A persistent VM can already have advanced the shared local model
        # before the sender's first eligible binding.
        prediction.advance(world, 123, 1.)
        prediction.advance(world, 123, 1.2)
        self.assertLess(prediction.report()['controller']['predicted_state']['position'][1], 100.)
        driver = LiveCharacterPhysics(experimental_enabled=True, prediction=prediction,
                                      use_predicted_humanoid_state=True,
                                      use_predicted_rotation=True)
        sent = []
        first = self.tick(driver, world, lambda *a, **k: sent.append(a), 2.)
        self.assertEqual(first['predicted_position'], [0., 100., 0.])
        following = self.tick(driver, world, lambda *a, **k: sent.append(a), 2.05)
        self.assertLess(following['predicted_position'][1], 100.)
        self.assertEqual(following['effective_d76c_flags'] & 31, 5)
        self.assertEqual(len(sent), 2)
        self.assertEqual(world.instances[root]['properties']['CFrame']['position'], [0., 100., 0.])

    def test_real_controller_jump_apex_fall_and_landing_reach_composed_wire_transform(self):
        """A real controller jump/fall/landing sequence survives packet composition."""
        from physics_packet import decode_transform_component
        from physics_root_record import encode_instance_reference
        from physics_controller import OwnCharacterPhysicsController
        from physics_ground import AABB, GroundGeometry
        from test_physics_controller import snapshot, intent

        class ControllerPrediction:
            def __init__(self):
                self.controller = None
                self.last_now = None

            def clear(self):
                self.controller = OwnCharacterPhysicsController(
                    snapshot((0., 4., 0.)),
                    geometry=GroundGeometry((AABB((-5., -1., -5.),
                                                   (5., 1., 5.), 'received_floor'),), ()))
                self.last_now = None

            def advance(self, world, user_id, now):
                if self.controller is None:
                    self.clear()
                dt = 0. if self.last_now is None else min(.25, now - self.last_now)
                self.last_now = now
                report = self.controller.step(dt, timestamp=now)
                return {'controller': report, 'last_reason': None,
                        'server_confirmed': False, 'network_packets_sent': 0}

        world, root = ready_world()
        prediction = ControllerPrediction()
        driver = LiveCharacterPhysics(experimental_enabled=True, prediction=prediction,
                                      d76c_flags=0x60, use_predicted_humanoid_state=True)
        packets = []
        send = lambda channel, payload, **kw: packets.append(payload)
        reports = [self.tick(driver, world, send, 1.)]
        prediction.controller.consume([intent(1, 'Jump', instance_id='humanoid')])
        for i in range(1, 16):
            reports.append(self.tick(driver, world, send, 1. + i * .05))

        modeled = [r['local_prediction']['controller']['predicted_state'] for r in reports]
        names = [state['humanoid_state']['name'] for state in modeled]
        self.assertIn('Jumping', names)
        self.assertIn('Freefall', names)
        self.assertEqual(names[-1], 'Running')
        self.assertGreater(max(state['position'][1] for state in modeled), 4.)
        self.assertAlmostEqual(modeled[-1]['position'][1], 4.)
        self.assertTrue(any('Landed' in state['humanoid_state_events'] for state in modeled))

        prefix = encode_instance_reference(world.client_scope, root) + b'\x00\x01'
        flags_offset = 18 + len(prefix)
        self.assertEqual(len(packets), len(modeled))
        sent_state_values = [packet[flags_offset] & 0x1f for packet in packets]
        modeled_state_values = [state['humanoid_state']['value'] for state in modeled]
        self.assertEqual(sent_state_values, modeled_state_values)
        self.assertIn(3, sent_state_values)  # Jumping
        self.assertIn(5, sent_state_values)  # Freefall
        self.assertEqual(sent_state_values[-1], 8)  # Stable post-landing Running
        decoded = []
        for packet in packets:
            self.assertEqual(packet[18:flags_offset], prefix)
            decoded.append(decode_transform_component(packet[flags_offset + 2:-2],
                                                       velocity_mode='short'))
        for item, expected in zip(decoded, modeled):
            self.assertAlmostEqual(item.position[1], expected['position'][1], delta=.08)
            self.assertIsNotNone(item.linear_velocity)
            self.assertAlmostEqual(item.linear_velocity.vector[1],
                                   expected['linear_velocity'][1], delta=1.)
        self.assertEqual(driver.report()['humanoid_states_submitted'],
                         {str(value): modeled_state_values.count(value)
                          for value in sorted(set(modeled_state_values))})
        self.assertFalse(driver.report()['server_acceptance_confirmed'])

    def tick(self, driver, world, send, now, delta=.05, connected=True):
        return driver.tick(world=world, own_user_id=123, now=now, delta=delta,
                           timestamp_ms=int(now * 1000), connected=connected,
                           send_unreliable=send)

    def test_continues_past_walk_limits_and_caps_late_frame_integration(self):
        world, _ = ready_world()
        driver = LiveCharacterPhysics(experimental_enabled=True,
                                      prediction=TrackingPrediction())
        sent = []
        send = lambda channel, payload, **kw: sent.append(payload)
        for i in range(1602):
            result = self.tick(driver, world, send, 1. + i * .05)
        self.assertEqual(result['network_send_count'], 1602)
        self.assertIsNone(result['max_duration_seconds'])
        self.assertIsNone(result['max_frames'])
        self.assertTrue(result['continuous_mode'])
        self.assertFalse(result['server_acceptance_confirmed'])
        late = self.tick(driver, world, send, 100., delta=.25)
        self.assertEqual(late['network_send_count'], 1603)
        self.assertEqual(late['late_frame_count'], 1)
        self.assertEqual(late['local_prediction']['controller']['predicted_state']['position'][1], -159.3)

    def test_root_and_ownership_loss_wait_then_regain_without_stale_send(self):
        world, root = ready_world()
        prediction = TrackingPrediction()
        driver = LiveCharacterPhysics(experimental_enabled=True,
                                      prediction=prediction)
        sent = []
        send = lambda channel, payload, **kw: sent.append(payload)
        self.tick(driver, world, send, 1.)
        world.instances[root]['properties']['NetworkOwnerV3'] = 9
        world.touch(root, ['NetworkOwnerV3'])
        blocked = self.tick(driver, world, send, 1.05)
        self.assertEqual(blocked['status'], 'observed_owner_scope_mismatch')
        self.assertEqual(len(sent), 1)
        self.assertEqual(prediction.clears, 2)
        # Server replication moves the same root during the ownership gap.
        world.instances[root]['properties']['CFrame']['position'] = [20., 30., 40.]
        world.instances[root]['properties']['NetworkOwnerV3'] = world.client_scope
        world.touch(root, ['NetworkOwnerV3', 'CFrame'])
        regained = self.tick(driver, world, send, 1.1)
        self.assertEqual(len(sent), 2)
        self.assertEqual(prediction.clears, 3)
        self.assertEqual(regained['received_position'], (20., 30., 40.))

        world.instances[root]['properties']['Anchored'] = True
        world.touch(root, ['Anchored'])
        blocked = self.tick(driver, world, send, 1.15)
        self.assertEqual(blocked['status'], 'received_anchored_state_not_known_false')
        self.assertEqual(len(sent), 2)
        world.instances[root]['properties']['Anchored'] = False
        world.touch(root, ['Anchored'])
        self.tick(driver, world, send, 1.2)
        self.assertEqual(len(sent), 3)

        del world.instances[root]
        missing = self.tick(driver, world, send, 1.25)
        self.assertEqual(missing['status'], 'waiting_for_received_own_root')
        self.assertEqual(len(sent), 3)

    def test_real_prediction_restarts_from_replicated_pose_after_owner_loss(self):
        world, root = ready_world()
        prediction = RuntimePhysicsPrediction()
        driver = LiveCharacterPhysics(experimental_enabled=True, prediction=prediction)
        sent = []
        send = lambda channel, payload, **kw: sent.append(payload)
        first = self.tick(driver, world, send, 1.)
        old_local = first['local_prediction']['controller']['predicted_state']['position']

        world.instances[root]['properties']['NetworkOwnerV3'] = 9
        world.touch(root, ['NetworkOwnerV3'])
        blocked = self.tick(driver, world, send, 1.05)
        self.assertEqual(blocked['status'], 'observed_owner_scope_mismatch')
        self.assertIsNone(prediction._world)
        # The enclosing persistent runtime may still step this shared object.
        prediction.advance(world, 123, 1.075)

        fresh_received = [20., 30., 40.]
        world.instances[root]['properties']['CFrame']['position'] = fresh_received
        world.instances[root]['properties']['NetworkOwnerV3'] = world.client_scope
        world.touch(root, ['CFrame', 'NetworkOwnerV3'])
        resumed = self.tick(driver, world, send, 1.1)
        new_local = resumed['local_prediction']['controller']['predicted_state']['position']
        self.assertEqual(resumed['received_position'], tuple(fresh_received))
        self.assertGreater(sum(abs(a - b) for a, b in zip(new_local, old_local)), 20.)
        self.assertEqual(resumed['network_send_count'], 2)
        self.assertEqual(len(sent), 2)

    def test_own_character_root_replacement_rebinds_and_preserves_sequence(self):
        world, old_root = ready_world()
        driver = LiveCharacterPhysics(experimental_enabled=True,
                                      prediction=PredictionStub())
        sent = []
        send = lambda channel, payload, **kw: sent.append(payload)
        self.tick(driver, world, send, 1.)
        # New legitimate root is a received Part parented to the own Character.
        new_root = (1, 33)
        world.instances[new_root] = {
            'class': 3, 'parent': (1, 3), 'properties': {
                'Name': b'HumanoidRootPart', 'Anchored': False,
                'NetworkOwnerV3': world.client_scope,
                'CFrame': {'position': [4., 5., 6.], 'rotation_id': 1}}}
        world.touch(new_root, created=True)
        world.instances[(1, 3)]['properties']['PrimaryPart'] = new_root
        world.touch((1, 3), ['PrimaryPart'])
        world.instances[(1, 2)]['properties']['Character'] = (1, 3)
        world.touch((1, 2), ['Character'])
        del world.instances[old_root]
        changed = self.tick(driver, world, send, 1.05)
        self.assertEqual(changed['network_send_count'], 2)
        self.assertEqual(changed['sequence'], 3)
        self.assertTrue(changed['own_root_evidence_observed'])

    def test_disconnect_and_send_error_are_sticky(self):
        world, _ = ready_world()
        driver = LiveCharacterPhysics(experimental_enabled=True,
                                      prediction=PredictionStub())
        calls = []
        send = lambda *a, **kw: calls.append(1)
        self.tick(driver, world, send, 1.)
        disconnected = self.tick(driver, world, send, 1.05, connected=False)
        self.assertEqual(disconnected['stop_reason'], 'disconnected')
        self.tick(driver, world, send, 1.1, connected=True)
        self.assertEqual(len(calls), 1)

        world, _ = ready_world()
        driver = LiveCharacterPhysics(experimental_enabled=True,
                                      prediction=PredictionStub())
        failures = []
        def fail(*a, **kw):
            failures.append(1)
            raise OSError('ambiguous transport')
        first = self.tick(driver, world, fail, 1.)
        second = self.tick(driver, world, fail, 1.05)
        self.assertEqual(first['stop_reason'], 'send_result_ambiguous_no_retry')
        self.assertEqual(second['network_send_attempt_count'], 1)
        self.assertEqual(len(failures), 1)

    def test_single_list_root_without_explicit_anchored_uses_proven_constructor_default(self):
        world, root = ready_world()
        del world.instances[root]['properties']['Anchored']
        world.creation[root] = {'fresh': True, 'complete': True, 'ordinary': False}
        driver = LiveCharacterPhysics(experimental_enabled=True,
                                      prediction=PredictionStub())
        sent = []
        result = self.tick(driver, world, lambda c, p, **kw: sent.append(p), 1.0)
        self.assertEqual(result['network_send_count'], 1)
        self.assertEqual(result['status'], 'client_send_returned_server_acceptance_unconfirmed')


if __name__ == '__main__':
    unittest.main()
