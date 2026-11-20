"""CPU scheduling for protected game scripts: the burst slice and the per-task CPU cap."""
import copy
import json
import time
import unittest

from persistent_runtime import PersistentClientScriptRuntime, PersistentLuauHost, RUST_HOST
from roblox_session import ROOT

SNAPSHOT = json.loads((ROOT / 'tests/fixtures/world_snapshot.json').read_text())


class BurstBudgetTests(unittest.TestCase):
    def runtime(self, **options):
        return PersistentClientScriptRuntime(lambda: None, 1, **options)

    def test_ordinary_budget_without_a_burst_option(self):
        runtime = self.runtime()
        runtime.stats['slice_exhausted'] = True
        self.assertEqual(runtime._background_step_budget(), runtime.background_budget_ms)

    def test_burst_applies_only_while_the_host_used_its_whole_slice(self):
        runtime = self.runtime(cpu_burst_ms=400)
        self.assertEqual(runtime._background_step_budget(), 50)
        runtime.stats['slice_exhausted'] = False
        self.assertEqual(runtime._background_step_budget(), 50)
        runtime.stats['slice_exhausted'] = True
        self.assertEqual(runtime._background_step_budget(), 400)
        runtime.stats['slice_exhausted'] = False
        self.assertEqual(runtime._background_step_budget(), 50)

    def test_options_are_validated(self):
        for bad in (50, 2001, '400', 0, True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.runtime(cpu_burst_ms=bad)
        for bad in (999, 3600001, '30000', True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.runtime(task_cpu_limit_ms=bad)
        self.runtime(task_cpu_limit_ms=30000, cpu_burst_ms=400)


BURN = '''
local state = {done = false}
task.spawn(function()
 local started = os.clock()
 while os.clock() - started < 2.6 do end
 state.done = true
end)
local deadline = os.clock() + 6
while not state.done and os.clock() < deadline do task.wait(.05) end
return state.done
'''


@unittest.skipUnless(RUST_HOST.is_file(), 'build the persistent worker first')
class TaskCpuLimitTests(unittest.TestCase):
    def run_burn(self, **options):
        host = PersistentLuauHost(copy.deepcopy(SNAPSHOT), **options)
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': BURN, 'timeout_ms': 1000})
        self.assertTrue(result['ok'], result.get('error'))
        errors = list(result.get('task_errors') or [])
        job = result['job_id']
        end = time.monotonic() + 20
        while time.monotonic() < end:
            result = host.call({'op': 'poll', 'timeout_ms': 100})
            self.assertTrue(result['ok'], result.get('error'))
            errors += result.get('task_errors') or []
            for done in result.get('completed_jobs', []):
                if done['job_id'] == job:
                    return done['values'], errors
            time.sleep(.005)
        self.fail('script did not finish')

    def test_default_profile_stops_a_task_that_never_yields_for_two_seconds(self):
        values, errors = self.run_burn()
        self.assertEqual(values, [False])
        self.assertTrue(any('CPU step budget' in error for error in errors), errors)

    def test_a_larger_cap_lets_the_same_task_finish(self):
        values, errors = self.run_burn(task_cpu_limit_ms=10000)
        self.assertEqual(values, [True])
        self.assertFalse(errors, errors)

    def test_the_cap_must_be_in_range(self):
        for bad in (500, 4000000):
            with self.assertRaises(Exception):
                self.run_burn(task_cpu_limit_ms=bad)


if __name__ == '__main__':
    unittest.main()
