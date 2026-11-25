#!/usr/bin/env python3
"""Run pinned UniversalSynSaveInstance and extract a validated export.

UniversalSynSaveInstance https://discord.gg/wx4ThpAsmw
Upstream source and license are retained in vendor/UniversalSynSaveInstance.
This adapter serializes only the current runtime's available instance data.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 65536
FORMATS = {'.rbxl': (True, False), '.rbxlx': (False, False),
           '.rbxm': (True, True), '.rbxmx': (False, True)}


def resolve_export_path(output):
    """Resolve relative export names inside the project's default export folder."""
    output = Path(output).expanduser()
    if not output.is_absolute():
        output = ROOT / 'rove exports' / output
    return output.resolve()


class ExportSession:
    def __init__(self, *, host=None, socket=None, deadline=180):
        self.host, self.socket, self.deadline = host, socket, deadline
        self.output = []
        self.decompiled_sources = {}
        self.decompilation_report = None

    def _check(self, result):
        if result.get('output'):
            value = result['output']
            self.output.append(value if isinstance(value, str) else json.dumps(value))
        if not result.get('ok'):
            raise RuntimeError(result.get('error', 'Luau export operation failed'))
        if result.get('task_errors'):
            raise RuntimeError('Luau background error: ' + str(result['task_errors']))

    def execute(self, source):
        from script_console import send_source, send_request
        if self.host:
            result = self.host.call({'op': 'execute', 'source': source, 'timeout_ms': 2000})
        else:
            result = send_source(self.socket, source, timeout_ms=2000)
        self._check(result)
        if result.get('completed', True):
            return result
        job = result['job_id']
        deadline = time.monotonic() + self.deadline
        while time.monotonic() < deadline:
            time.sleep(.01)
            if self.host:
                response = self.host.call({'op': 'poll', 'timeout_ms': 2000})
                self._check(response)
                result = next((x for x in response.get('completed_jobs', [])
                               if x.get('job_id') == job), None)
            else:
                result = send_request(self.socket, {'op': 'status', 'job_id': job})
            if result:
                self._check(result)
                if result.get('completed'):
                    return result
        raise TimeoutError(f'USSI operation did not finish within {self.deadline} seconds')

    def upload(self, name, data):
        quoted = json.dumps(name)
        self.execute(f'writefile({quoted}, ""); return true')
        for start in range(0, len(data), CHUNK):
            encoded = base64.b64encode(data[start:start + CHUNK]).decode('ascii')
            self.execute(f'appendfile({quoted},crypt.base64decode("{encoded}")); return true')

    def extract(self, virtual_path, output):
        quoted = json.dumps(virtual_path)
        size = self.execute(f'return getfileinfo({quoted})')['values'][0]
        if type(size) not in (int, float) or size != int(size) or not 0 < size <= 64*1024*1024:
            raise RuntimeError('USSI did not produce a bounded, nonempty output file')
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=output.name + '.', suffix='.partial', dir=output.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                for offset in range(0, int(size), CHUNK):
                    length = min(CHUNK, int(size) - offset)
                    result = self.execute(f'return crypt.base64encode(readfilechunk({quoted},{offset},{length}))')
                    data = base64.b64decode(result['values'][0], validate=True)
                    if len(data) != length:
                        raise RuntimeError('Incomplete workspace export chunk')
                    stream.write(data)
            return Path(temporary)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


def prepare(session):
    session.execute('setworkspacequota(64*1024*1024,128*1024*1024); makefolder("ussi_bundle"); makefolder("ussi_cache"); return true')
    files = {
        'ussi_bundle/saveinstance.luau': ROOT/'vendor/UniversalSynSaveInstance/saveinstance.luau',
        'ussi_bundle/StreamBuffer.luau': ROOT/'vendor/SomeHub/StreamBuffer.luau',
        'ussi_bundle/UniversalMethodFinder.luau': ROOT/'vendor/SomeHub/UniversalMethodFinder.luau',
        'ussi_bundle/api.json': ROOT/'vendor/UniversalSynSaveInstance-reference/Serialization-API-Dump.json',
    }
    manifest = json.loads((ROOT/"vendor/ussi-bundle.json").read_text())
    for target, path in files.items():
        data = path.read_bytes()
        # The pinned manifest was generated with LF line endings. Windows
        # checkouts use CRLF, so normalize before hashing and uploading; an
        # actual content change is still caught (it changes the LF hash too).
        data = data.replace(b'\r\n', b'\n')
        relative = path.relative_to(ROOT).as_posix()
        if hashlib.sha256(data).hexdigest() != manifest["files"][relative]:
            raise RuntimeError("Bundled dependency checksum mismatch: " + relative)
        session.upload(target, data)
    session.upload('ussi_bundle/recovered.json', json.dumps(session.decompiled_sources).encode())
    session.execute('''
local versionName="UNKNOWN"
if not pcall(function()versionName=version()end) then
 if not pcall(function()versionName=settings():GetService("DebugSettings").RobloxVersion end) then
  if not pcall(function()versionName=game:GetService("RunService"):GetRobloxVersion()end) then versionName="UNKNOWN" end
 end
end
local http=game:GetService("HttpService")
local classes=http:JSONDecode(readfile("ussi_bundle/api.json")).Classes
writefile("ussi_cache/API_DUMP.json",http:JSONEncode({[versionName]=classes}))
return true
''')


def export_source(virtual_path, *, binary, model, object_path=None, offline=True):
    segments = object_path.split('/') if object_path else []
    if any(not s for s in segments):
        raise ValueError('Object path must contain nonempty slash-separated instance names')
    # JSON is compatible with the strings/arrays/booleans used by this source.
    path = '{' + ','.join(json.dumps(s, ensure_ascii=False) for s in segments) + '}'
    return '''
local originalHttpGet=httpget
local originalNamedHttpGet=HttpGet
local originalDecompile=decompile
local recovered=game:GetService("HttpService"):JSONDecode(readfile("ussi_bundle/recovered.json"))
local function localDecompile(instance)
 local bytes=getscriptbytecode(instance)
 local source=recovered[crypt.base64encode(bytes)]
 assert(source,"Local decompilation unavailable or failed; see export report")
 return source
end
decompile=localDecompile
local bundled={
 ["https://raw.githubusercontent.com/luau/SomeHub/main/StreamBuffer.luau"]="ussi_bundle/StreamBuffer.luau",
 ["https://raw.githubusercontent.com/luau/SomeHub/main/UniversalMethodFinder.luau"]="ussi_bundle/UniversalMethodFinder.luau",
}
local function fetch(url,cache)
 local file=bundled[url]
 if file then return readfile(file) end
 if OFFLINE then error("Unbundled optional dependency: "..tostring(url)) end
 return originalHttpGet(url,cache)
end
httpget=fetch
HttpGet=fetch
local ok,err=xpcall(function()
 local save=assert(loadstring(readfile("ussi_bundle/saveinstance.luau"),"=UniversalSynSaveInstance"))()
 local object=nil
 local segments=OBJECT_PATH
 if #segments>0 then
  object=game
  for _,name in ipairs(segments) do
   object=assert(object:FindFirstChild(name),"Object path missing: "..name)
  end
 end
 local sources={}
 local root=object or game
 local candidates=root:GetDescendants()
 table.insert(candidates,1,root)
 for _,instance in ipairs(candidates) do
  if instance:IsA("LuaSourceContainer") then
   local hasSource,source=pcall(function()return instance.Source end)
   if hasSource and type(source)=="string" and #source>0 then sources[instance]=source end
  end
 end
 save({FilePath=VIRTUAL_PATH,Binary=BINARY,IsModel=MODEL,Object=object,
  mode="full",ShowStatus=false,AntiIdle=false,SafeMode=false,ReadMe=false,
  Decompile=true,RecoverScriptsFromAssets=false,SourceCache=sources,
  IgnoreDefaultProperties=false,AvoidFileOverwrite=false,
  RiskyServicesDisabled={UGC=true,Encoding=true,Reflection=true}})
 assert(isfile(VIRTUAL_PATH),"USSI returned without producing a file; inspect export warnings")
 assert(getfileinfo(VIRTUAL_PATH)>32,"USSI output is incomplete")
end,function(message)return tostring(message)end)
if httpget==fetch then httpget=originalHttpGet end
if HttpGet==fetch then HttpGet=originalNamedHttpGet end
if decompile==localDecompile then decompile=originalDecompile end
assert(ok,err)
return getfileinfo(VIRTUAL_PATH)
'''.replace('OFFLINE', str(offline).lower()).replace('OBJECT_PATH', path).replace(
        'VIRTUAL_PATH', json.dumps(virtual_path)).replace('BINARY', str(binary).lower()).replace('MODEL', str(model).lower())


def run_export(session, output, *, object_path=None, offline=True, expectations=None):
    from validate_ussi_export import parse_export, validate
    output = resolve_export_path(output)
    if output.suffix.lower() not in FORMATS:
        raise ValueError('Output extension must be .rbxl, .rbxlx, .rbxm or .rbxmx')
    binary, model = FORMATS[output.suffix.lower()]
    if model and not object_path:
        raise ValueError('Model export requires --object, for example Workspace/MyModel')
    virtual = '__ussi_export_' + uuid.uuid4().hex + output.suffix.lower()
    temporary = None
    try:
        prepare(session)
        session.execute(export_source(virtual, binary=binary, model=model,
                                      object_path=object_path, offline=offline))
        temporary = session.extract(virtual, output)
        # Reader inspects the actual file; a returned save function is not proof.
        checked = validate(parse_export(temporary), expectations)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        size = temporary.stat().st_size
        os.replace(temporary, output)
        return {'ok': True, 'output': str(output), 'bytes': size, 'sha256': digest,
                'validation': checked, 'decompilation': session.decompilation_report}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        # Remove VM output even after validation failure. Cleanup must not mask
        # the original failure or report a validated published file as failed.
        try:
            session.execute(f'if isfile({json.dumps(virtual)}) then delfile({json.dumps(virtual)}) end; return true')
        except Exception:
            pass


def capture_console_snapshot(socket_path):
    """Capture immutable replicated state without advancing the scripting VM."""
    from script_console import send_request
    result = send_request(socket_path, {'op': 'export_snapshot'})
    if not result.get('ok'):
        message = result.get('error', 'Could not capture export snapshot')
        if message == 'Invalid source request':
            message = 'Restart the running client once to enable fresh-snapshot exports'
        raise RuntimeError(message)
    token = result['token']
    try:
        size = result['bytes']
        if type(size) is not int or not 0 < size <= 8*1024*1024:
            raise RuntimeError('Invalid export snapshot size')
        data = bytearray()
        for offset in range(0, size, CHUNK):
            chunk = send_request(socket_path, {'op': 'export_snapshot_chunk',
                                               'token': token, 'offset': offset})
            if not chunk.get('ok'):
                raise RuntimeError(chunk.get('error', 'Snapshot transfer failed'))
            decoded = base64.b64decode(chunk['data'], validate=True)
            if len(decoded) != min(CHUNK, size-offset):
                raise RuntimeError('Incomplete export snapshot chunk')
            data.extend(decoded)
        if hashlib.sha256(data).hexdigest() != result['sha256']:
            raise RuntimeError('Export snapshot checksum mismatch')
        return json.loads(data)
    finally:
        try:
            send_request(socket_path, {'op': 'export_snapshot_release', 'token': token})
        except (OSError, ValueError):
            pass  # Server also expires abandoned snapshots after 60 seconds.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--socket', type=Path, help='Existing custom-client console; does not join a game')
    source.add_argument('--snapshot', type=Path, help='Offline owned snapshot')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--object', dest='object_path')
    parser.add_argument('--expect', type=Path)
    parser.add_argument('--network', action='store_true', help='Permit upstream optional public dependency fetches')
    parser.add_argument('--fixture-source', action='store_true', help='Populate the owned USSI fixture ModuleScript source')
    parser.add_argument('--memory-mb', type=int, default=64)
    parser.add_argument('--no-decompile', action='store_true', help='Skip local bytecode reconstruction')
    args = parser.parse_args()
    host = None
    session = None
    try:
        from persistent_runtime import PersistentLuauHost
        snapshot = (json.loads(args.snapshot.read_text()) if args.snapshot
                    else capture_console_snapshot(args.socket))
        host = PersistentLuauHost(snapshot, memory_mb=args.memory_mb)
        session = ExportSession(host=host)
        if args.fixture_source:
            if not args.snapshot:
                raise ValueError('--fixture-source is only available with an offline snapshot')
            session.execute('workspace.ExportFixture.SourceProbe.Source="return 17"; return true')
        if not args.no_decompile:
            from luau_decompiler import prepare_sources
            def validate_source(source):
                result = session.execute('local f,e=loadstring(' + json.dumps(source) + '); return f~=nil,e')
                if not result['values'][0]:
                    raise ValueError('Recovered source failed the runtime compiler check')
            session.decompiled_sources, session.decompilation_report = prepare_sources(
                snapshot, validate_source, object_path=args.object_path)
        expected = json.loads(args.expect.read_text()) if args.expect else None
        result = run_export(session, args.output, object_path=args.object_path,
                            offline=not args.network, expectations=expected)
        print(json.dumps(result, ensure_ascii=True))
    except Exception as error:
        if session and session.output:
            print(''.join(session.output)[-12000:])
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=True))
        return 1
    finally:
        if host:
            host.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
