import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from script_catalog import prepare_script, script_catalog, CodePreparationQueue
import threading
import time
from test_world_snapshot import fixture


class ScriptCatalogTests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).resolve().parents[2] / 'runtime/build/luau-source-to-bytecode').is_file(),
                         'build the local fixture compiler')
    def test_authenticated_roblox_path_decodes_ambiguous_constant_module(self):
        from bytecode_container import _inspector, standardize_opcodes
        compiler = Path(__file__).resolve().parents[2] / 'runtime/build/luau-source-to-bytecode'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'source.luau').write_text('return {a=1,b=2,c=3}')
            subprocess.run([str(compiler), str(folder / 'source.luau'), str(folder / 'code')],
                           check=True, capture_output=True, timeout=5)
            plain = (folder / 'code').read_bytes()
        module, _ = _inspector().inspect(plain, '1')
        encoded = bytearray(plain)
        for prototype in module['prototypes']:
            for instruction in prototype['instructions']:
                offset = prototype['code_offset'] + instruction['pc'] * 4
                encoded[offset] = (instruction['opcode'] * 227) & 255
        encoded = bytes(encoded)
        with self.assertRaisesRegex(ValueError, 'Cannot uniquely infer opcode multiplier'):
            standardize_opcodes(encoded)
        # Auth is mocked only for this locally compiled unit fixture. Genuine
        # captured signatures are checked separately; this never signs code.
        result = prepare_script({'Bytecode': encoded},
                                unpack=Mock(side_effect=ValueError()),
                                verify=Mock(return_value={'verification': True}))
        self.assertEqual(bytes.fromhex(result['bytecode_hex']), plain)
        self.assertEqual(result['digest'], hashlib.sha256(encoded).hexdigest())

    def test_text_sources_and_missing_code(self):
        self.assertEqual(prepare_script({'Source': b'return 42'})['source'], 'return 42')
        self.assertEqual(prepare_script({'Source': 'return "hello"'})['source'], 'return "hello"')
        self.assertEqual(prepare_script({}), {'reason': 'code_unavailable'})
        self.assertEqual(prepare_script({'Source': 'x' * (128*1024+1)})['reason'], 'source_size_limit')
        self.assertEqual(prepare_script({'Bytecode': b''})['reason'], 'code_unavailable')
        self.assertEqual(prepare_script({'Bytecode': b'x' * (1024*1024+1)})['reason'], 'bytecode_size_limit')

    def test_large_signed_bytecode_is_admitted_after_verification(self):
        big = b'\x0e\x03' + b'x' * (600 * 1024)
        calls = []
        def verify(raw): calls.append('verify'); return {'verification': True}
        result = prepare_script({'Bytecode': b'container'}, unpack=lambda raw: big, verify=verify,
                                normalize=lambda raw: (raw, {}))
        self.assertTrue(result['signature_verified'])
        self.assertEqual(len(bytes.fromhex(result['bytecode_hex'])), len(big))
        self.assertEqual(calls, ['verify'])

    def test_large_signed_bytecode_in_code_and_signature_blocks_is_a_candidate(self):
        blocks = [1, 0, b'c' * (300 * 1024), b's' * 64]
        seen = []
        def unpack(raw): seen.append(len(raw)); return b'\x0e\x03' + raw
        result = prepare_script({'Source': blocks}, unpack=unpack, verify=lambda raw: {'verification': True},
                                normalize=lambda raw: (raw, {}))
        self.assertTrue(result['signature_verified'])
        self.assertEqual(seen, [300 * 1024 + 64])

    def test_oversized_standard_bytecode_is_rejected_after_normalization(self):
        result = prepare_script({'Bytecode': b'container'}, unpack=lambda raw: b'orig',
                                verify=lambda raw: {'verification': True},
                                normalize=lambda raw: (b'x' * (1024*1024+1), {}))
        self.assertEqual(result, {'reason': 'invalid_script_bytecode'})

    def test_signature_verification_precedes_normalization(self):
        calls=[]
        def unpack(raw):calls.append('unpack');return b'signed-original'
        def verify(raw):calls.append(('verify', raw));return {'verification': True}
        def normalize(raw):calls.append(('normalize', raw));return b'\x0e\x03converted', {}
        result=prepare_script({'Bytecode': b'container'}, unpack=unpack, verify=verify, normalize=normalize)
        self.assertTrue(result['signature_verified'])
        self.assertEqual(bytes.fromhex(result['bytecode_hex']), b'\x0e\x03converted')
        self.assertEqual(calls, ['unpack', ('verify', b'signed-original'), ('normalize', b'signed-original')])

    def test_invalid_signatures_never_reach_the_converter(self):
        convert=Mock()
        result=prepare_script({'Source': [1, 0, b'bad-code', b'bad-signature']},
                              unpack=Mock(side_effect=ValueError()),
                              verify=Mock(side_effect=ValueError()), normalize=convert)
        self.assertNotIn('bytecode_hex', result)
        convert.assert_not_called()

    def test_protected_shared_strings_are_resolved_before_verification(self):
        key=bytes.fromhex('12'*16)
        verify=Mock(return_value={'verification': True})
        result=prepare_script({'Source': {'shared': key.hex()}}, {key: b'signed'},
                              unpack=Mock(side_effect=ValueError()), verify=verify,
                              normalize=lambda raw: (b'code', {}))
        self.assertTrue(result['signature_verified'])
        verify.assert_called_once_with(b'signed')

    def test_verifier_must_report_actual_success(self):
        converter=Mock()
        result=prepare_script({'Bytecode': b'code'}, unpack=Mock(side_effect=ValueError()),
                              verify=lambda raw: {'verification': False}, normalize=converter)
        self.assertIn('reason', result)
        converter.assert_not_called()

    def test_per_script_cache_updates_when_source_or_shared_data_changes(self):
        world,_=fixture();world.schema['classes'].append({'name':'ModuleScript','properties':[]})
        key=(1,20);world.instances[key]={'class':len(world.schema['classes'])-1,'parent':(1,6),'properties':{'Source':'return 1'}}
        with patch('script_catalog.prepare_script', wraps=prepare_script) as prepare:
            self.assertEqual(script_catalog(world)['1:20']['source'], 'return 1')
            script_catalog(world)
            self.assertEqual(prepare.call_count, 1)
            world.instances[key]['properties']['Source']='return 2'
            self.assertEqual(script_catalog(world)['1:20']['source'], 'return 2')
            self.assertEqual(prepare.call_count, 2)
        del world.instances[key]
        self.assertEqual(script_catalog(world), {})

    def test_background_verification_does_not_stall_world_updates(self):
        world,_=fixture();world.schema['classes'].append({'name':'ModuleScript','properties':[]})
        world.instances[(1,20)]={'class':len(world.schema['classes'])-1,'parent':(1,6),'properties':{'Bytecode':b'encoded'}}
        queue=CodePreparationQueue();world._script_preparation_queue=queue
        self.addCleanup(queue.close)
        release=threading.Event();self.addCleanup(release.set)
        def prepare(*_):release.wait(2);return {'source':'return 42'}
        with patch('script_catalog.prepare_script',side_effect=prepare):
            started=time.monotonic();first=script_catalog(world)
            self.assertLess(time.monotonic()-started,.5)
            self.assertEqual(first['1:20']['reason'],'verification_pending')
            release.set()
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                result=script_catalog(world)['1:20']
                if 'source' in result:break
                time.sleep(.005)
            self.assertEqual(result['source'],'return 42')

    def test_code_only_updates_refresh_catalog_without_putting_code_in_world_delta(self):
        from world_snapshot import make_world_delta
        from persistent_runtime import PersistentClientScriptRuntime
        world,_=fixture();world.schema['classes'].append({'name':'ModuleScript','properties':[]})
        key=(1,20);world.instances[key]={'class':len(world.schema['classes'])-1,'parent':(1,6),'properties':{'Source':'return 1'}}
        cursor=world.revision
        world.instances[key]['properties']['Source']='return 2';world.touch(key,['Source'])
        delta=make_world_delta(world,cursor)
        self.assertTrue(delta['actions'][0]['script_code_changed'])
        self.assertNotIn('Source',delta['actions'][0]['fields'])
        runtime=PersistentClientScriptRuntime(lambda:world,123)
        runtime.initial_replication_complete=True;runtime.shared_entry_count=len(world.shared)
        runtime.script_catalog={}
        self.assertTrue(runtime._catalog_needs_refresh(world,delta,True))

    def test_archivable_default_requires_a_complete_constructor_record(self):
        from world_snapshot import make_world_snapshot
        world,_=fixture();world.schema['classes'].append({'name':'ModuleScript','properties':[]})
        key=(1,20);world.instances[key]={'class':len(world.schema['classes'])-1,'parent':(1,6),'properties':{}}
        world.creation[key]={'fresh':True,'complete':True,'ordinary':True}
        node=next(n for n in make_world_snapshot(world,123)['nodes'] if n['id']=='1:20')
        self.assertTrue(node['properties']['Archivable'])
        self.assertEqual(node['origins']['Archivable'],'class_default')
        world.creation[key]['complete']=False
        node=next(n for n in make_world_snapshot(world,123)['nodes'] if n['id']=='1:20')
        self.assertNotIn('Archivable',node['properties'])


if __name__=='__main__':unittest.main()
