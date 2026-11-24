"""Native regression for timers starving behind an expensive world pump."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


RUNTIME = Path(__file__).resolve().parents[2] / 'runtime'
VENDOR = RUNTIME.parent / 'vendor' / 'luau'
BUILD = Path(os.environ.get('RCR_LUAU_NATIVE_BUILD', str(RUNTIME / 'build')))
ARCHIVES = ('Luau.Compiler', 'Luau.VM', 'Luau.Bytecode', 'Luau.Config',
            'Luau.Ast', 'Luau.Common')


class SchedulerFairnessTests(unittest.TestCase):
    def test_ready_callbacks_and_expired_timer_run_before_expensive_pump(self):
        includes = [VENDOR / 'VM' / 'include', VENDOR / 'Compiler' / 'include',
                    VENDOR / 'Ast' / 'include', VENDOR / 'Config' / 'include',
                    VENDOR / 'Common' / 'include', VENDOR / 'Bytecode' / 'include', VENDOR / 'VM' / 'src',
                    RUNTIME / 'vendor', RUNTIME]
        libraries = [BUILD / f'lib{name}.a' for name in ARCHIVES]
        if (not VENDOR.is_dir() or not all(path.is_file() for path in libraries)):
            self.skipTest('pinned Luau source and static libraries are unavailable')
        with tempfile.TemporaryDirectory(prefix='luau-scheduler-fairness-') as directory:
            binary = Path(directory) / 'scheduler-fairness'
            command = [os.environ.get('CXX', 'c++'), '-std=c++17', '-O2']
            if sys.platform == 'darwin':
                # An Intel Python running under Rosetta otherwise makes clang
                # target x86_64 even when the pinned libraries are ARM-only.
                architectures = subprocess.check_output(
                    ['lipo', '-archs', str(libraries[0])], text=True).split()
                if len(architectures) == 1:
                    command += ['-arch', architectures[0]]
            for include in includes:
                command += ['-I', str(include)]
            command += [str(Path(__file__).with_suffix('.cpp')),
                        str(RUNTIME / 'source_scheduler.cpp'), str(RUNTIME / 'closure_bindings.cpp'),
                        str(RUNTIME / 'api_trace.cpp')]
            command += [str(path) for path in libraries]
            command += ['-pthread', '-o', str(binary)]
            subprocess.run(command, check=True, timeout=180)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
