"""Build the optional native replication decoder (native/wire_native.cpp) into scripts/_wire_native.pyd.

Uses the stable Python ABI (Py_LIMITED_API) and the mingw g++ the runtime already builds with. Without the module the Python
decoder is used unchanged. Usage: python scripts/build_native_wire.py [--gxx PATH]
"""
import argparse
import os
import pathlib
import subprocess
import sys
import sysconfig

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gxx', default=os.environ.get('GXX', 'g++'))
    args = parser.parse_args()
    include = sysconfig.get_paths()['include']
    stable_dll = pathlib.Path(sys.base_prefix) / 'python3.dll'
    out = ROOT / 'scripts' / '_wire_native.pyd'
    command = [args.gxx, '-std=c++17', '-O2', '-shared', '-DPy_LIMITED_API=0x030B0000', '-I', include,
               str(ROOT / 'native' / 'wire_native.cpp'), '-o', str(out), str(stable_dll),
               '-static', '-static-libgcc', '-static-libstdc++']
    print(' '.join(command))
    subprocess.run(command, check=True)
    print('built', out)


if __name__ == '__main__':
    main()
