"""Time slicing must never break code that cannot be suspended.

Roblox does not preempt script code. Rove's scheduler gives background tasks a short quantum and breaks them at it. A break that
reaches a thread inside a metamethod (or any C-call boundary) cannot be propagated: Luau raised "attempt to break across
metamethod/C-call boundary" there, which protected scripts observe (they run coroutine tests inside metamethods and fold the
outcome into their keys). The slice now lets such code run on, and a runaway is bounded by the engine's script-timeout error.

The task must be resumed by the scheduler to get a quantum: task.spawn runs its function immediately inside the calling job, so
each scenario starts with task.wait().
"""
import copy
import json
import os
import time
import unittest
from unittest import mock

from persistent_runtime import PersistentLuauHost, RUST_HOST
from roblox_session import ROOT

SNAPSHOT = json.loads((ROOT / 'tests/fixtures/world_snapshot.json').read_text())

# Long enough to outlive the scheduler's 2 ms quantum many times over.
HEAVY = 'local s = 0 for i = 1, 4e6 do s = s + i end return s'
HEAVY_RESULT = '8000002000000'
CHILD_UNDER_BOUNDARY = {
    'wrap in __index': 'local t = setmetatable({}, {__index = function() return coroutine.wrap(function() %s end)() end}) return t.x',
    'resume in __index': ('local t = setmetatable({}, {__index = function() local co = coroutine.create(function() %s end) '
                          'local ok, v = coroutine.resume(co) if not ok then error(v, 0) end return v end}) return t.x'),
    'wrap in __tostring': 'local t = setmetatable({}, {__tostring = function() return tostring(coroutine.wrap(function() %s end)()) end}) return tostring(t)',
    'wrap in gsub callback': 'return (string.gsub("a", ".", function() return tostring(coroutine.wrap(function() %s end)()) end))',
    'wrap in sort comparator': ('local n = 0 table.sort({3, 2, 1}, function(a, b) n += 1 '
                                'if n == 1 then coroutine.wrap(function() %s end)() end return a < b end) return "sorted"'),
}


def scenario(body):
    return ('local R = {} shared.R = R task.spawn(function() task.wait() local ok, v = pcall(function() %s end) '
            'R.ok, R.v, R.done = ok, tostring(v), true end)') % body


@unittest.skipUnless(RUST_HOST.is_file(), 'build the persistent worker first')
class UnbreakablePreemptionTests(unittest.TestCase):
    def outcome(self, source, environment=None, seconds=30):
        with mock.patch.dict(os.environ, environment or {}):
            host = PersistentLuauHost(copy.deepcopy(SNAPSHOT))
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': source, 'timeout_ms': 1000})
        self.assertTrue(result['ok'], result.get('error'))
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            host.call({'op': 'poll', 'timeout_ms': 100})
            probe = host.call({'op': 'execute', 'timeout_ms': 1000, 'source': 'local R = shared.R return R.done, R.ok, R.v'})
            values = probe.get('values') or []
            if values and values[0] is True:
                return values[1:]
            time.sleep(.01)
        self.fail('the task never finished')

    def test_a_preempted_child_coroutine_under_a_c_call_boundary_is_not_an_error(self):
        for name, body in CHILD_UNDER_BOUNDARY.items():
            with self.subTest(name):
                ok, value = self.outcome(scenario(body % HEAVY if '%s' in body else body))
                self.assertTrue(ok, 'the slice broke a coroutine whose parent cannot be suspended: %s' % value)
                self.assertIn(value, (HEAVY_RESULT, 'sorted'))

    def test_task_spawn_runs_the_child_to_its_end_and_the_thread_is_closable(self):
        # A protected script closes the thread task.spawn returns. Roblox never preempts the spawned function, so the thread is
        # finished (not "normal", which coroutine.close rejects) by the time spawn returns.
        body = ('local co = task.spawn(function() %s end) '
                'return coroutine.status(co) .. ":" .. tostring(coroutine.close(co))') % HEAVY
        ok, value = self.outcome(scenario(body))
        self.assertTrue(ok, value)
        self.assertEqual(value, 'dead:true')

    def test_a_runaway_inside_a_metamethod_is_bounded_by_the_script_timeout_error(self):
        started = time.monotonic()
        source = scenario('local t = setmetatable({}, {__index = function() while true do end end}) return t.x')
        ok, message = self.outcome(source, {'ROVE_UNBREAKABLE_OVERRUN_MS': '500'}, seconds=20)
        self.assertFalse(ok)
        self.assertIn('Script timeout: exhausted allowed execution time', message)
        self.assertLess(time.monotonic() - started, 15)


if __name__ == '__main__':
    unittest.main()
