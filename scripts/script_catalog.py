"""Prepare source, signed code, or native short code from a pinned game session."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from session_integrity import bind_container_observer, container_candidate_probe

MAX_CODE = 128 * 1024
MAX_CATALOG = 3 * 1024 * 1024


def _referenced_shared(value, shared, out, depth=0):
    if depth > 3 or not shared:
        return
    if isinstance(value, dict) and isinstance(value.get('shared'), str):
        try:
            k = bytes.fromhex(value['shared'])
        except ValueError:
            return
        if k in shared and k not in out:
            raw = shared[k]
            out[k] = raw
            _referenced_shared(raw, shared, out, depth + 1)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _referenced_shared(item, shared, out, depth + 1)


class CodePreparationQueue:
    """Bounded background verifier; never stall the network event loop."""
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='script-code')
        self.pending = {}

    def resolve(self, key, digest, properties, shared, *, allow_small_unsigned=False):
        previous = self.pending.get(key)
        if previous:
            old_digest, future = previous
            if old_digest != digest:
                future.cancel()
                del self.pending[key]
            elif future.done():
                del self.pending[key]
                try:return future.result()
                except Exception:return {'reason':'code_preparation_failed'}
            else:return None
        if len(self.pending) < 64:
            code = {name: properties.get(name) for name in ('Source','Bytecode','ScriptBytecode')}
            needed_shared = {}
            for v in code.values():
                _referenced_shared(v, shared, needed_shared)
            policy = {'allow_small_unsigned': True} if allow_small_unsigned else {}
            job = bind_container_observer(prepare_script, code, needed_shared, **policy)
            self.pending[key] = (digest, self.executor.submit(job))
        return None

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.pending.clear()


def _candidates(value, shared, depth=0):
    if depth > 3:
        return
    if isinstance(value, bytes):
        yield value
    elif isinstance(value, dict) and isinstance(value.get('shared'), str):
        try:
            raw = shared.get(bytes.fromhex(value['shared']))
        except ValueError:
            return
        if raw is not None:
            yield from _candidates(raw, shared, depth + 1)
    elif isinstance(value, (tuple, list)):
        blocks = [item for item in value if isinstance(item, bytes) and item]
        if len(blocks) == 2 and sum(map(len, blocks)) <= MAX_CODE:
            yield b''.join(blocks)
        for item in value:
            yield from _candidates(item, shared, depth + 1)


def prepare_script(properties, shared=None, *, verify=None, unpack=None, normalize=None,
                   allow_small_unsigned=False):
    shared = shared or {}
    source = properties.get('Source')
    if isinstance(source, str):
        if len(source.encode('utf-8')) > MAX_CODE:
            return {'reason': 'source_size_limit'}
        return {'source': source, 'provenance': 'source'}
    # A plain text Source is compiled locally; protected binary strings use the
    # existing signature verifier before opcode conversion or VM loading.
    if isinstance(source, bytes):
        try:
            text = source.decode('utf-8')
            if len(source) <= MAX_CODE and all(ord(c) >= 32 or c in '\t\r\n' for c in text):
                return {'source': text, 'provenance': 'source'}
        except UnicodeError:
            pass
    candidates = []
    for name in ('Source', 'Bytecode', 'ScriptBytecode'):
        candidates.extend(_candidates(properties.get(name), shared))
    if not candidates:
        return {'reason': 'code_unavailable'}
    from bytecode_container import unpack_container, standardize_opcodes
    from bytecode_signature import verify_signed_bytecode
    verify, unpack = verify or verify_signed_bytecode, unpack or unpack_container
    # These are authenticated Roblox script payloads, whose opcode bytes use
    # the Roblox multiplier (227, with inverse 203 modulo 256). Inferring an
    # arbitrary encoding from a small constant-only module is ambiguous and
    # can reject valid code, or mistake encoded instructions for plain Luau.
    # Keep generic format inference in bytecode_container for unknown inputs.
    normalize = normalize or (lambda original: standardize_opcodes(original, '203'))
    reason = 'unsupported_protected_code'
    for raw in candidates[:8]:
        if not 0 < len(raw) <= MAX_CODE:
            reason = 'bytecode_size_limit'
            continue
        originals = [raw]
        unpacked = None
        try:
            # Candidates may be raw signed bytecode or alternate fragments.
            # A failed format probe is not an authoritative RSB rejection.
            with container_candidate_probe():
                unpacked = unpack(raw)
                originals.insert(0, unpacked)
        except ValueError:
            pass
        for original in originals:
            try:
                # The pinned native admission policy treats unsigned short
                # programs separately (1013F942C result 1 -> 1013F91D4).
                # This branch is confined to checksum-valid RSB containers
                # received over the pinned session, and never claims a V1
                # signature. Requiring no trailer prevents treating a damaged
                # or truncated signature envelope as an unsigned module.
                if allow_small_unsigned is True and original is unpacked and 0 < len(original) < 256:
                    standard, metadata = normalize(original)
                    if (metadata.get('bytecode_version') in (13, 14)
                            and metadata.get('type_version') == 3
                            and metadata.get('trailer_bytes') == 0
                            and metadata.get('prototype_extension_bytes') == 0
                            and len(standard) == len(original)):
                        return {'bytecode_hex': standard.hex(), 'signature_verified': False,
                                'provenance': 'session_small_bytecode',
                                'admission': 'pinned_session_rsb_luau13_14_no_trailer_under_256',
                                'digest': hashlib.sha256(original).hexdigest()}
                    raise ValueError('invalid_short_script_bytecode')
                verified = verify(original)
                if verified.get('verification') is not True:
                    raise ValueError('signature_not_verified')
                standard, metadata = normalize(original)
                if len(standard) > MAX_CODE:
                    raise ValueError('bytecode_size_limit')
                return {'bytecode_hex': standard.hex(), 'signature_verified': True,
                        'provenance': 'verified_bytecode',
                        'digest': hashlib.sha256(original).hexdigest()}
            except (ValueError, OSError) as error:
                reason = getattr(error, 'reason', 'invalid_script_bytecode')
    return {'reason': reason}


def _script_priority(world, key, instance, class_name):
    props = instance['properties']
    if props.get('Disabled') is True or props.get('Enabled') is False:
        return 4
    if class_name == 'Script' and props.get('RunContext') != 2:
        return 5
    cur = instance.get('parent')
    hops = 0
    top_name = ''
    while cur and hops < 16:
        hops += 1
        parent = world.instances.get(cur)
        if not parent:
            break
        nxt = parent.get('parent')
        if not nxt or nxt not in world.instances:
            top_name = world.schema['classes'][parent['class']]['name']
            break
        cur = nxt
    if class_name in ('LocalScript', 'Script'):
        if top_name in ('ReplicatedFirst', 'StarterPlayer', 'StarterGui', 'StarterPack', 'Players'):
            return 0
        return 1
    if top_name in ('ReplicatedFirst', 'StarterPlayer', 'StarterGui', 'Players'):
        return 1
    return 2


def script_catalog(world):
    """Cache by each script's actual code/shared-string inputs, not world traffic."""
    cache = getattr(world, '_script_catalog_cache', {})
    current, next_cache, budget = {}, {}, 0
    allow_small_unsigned = getattr(world, 'allow_small_unsigned_scripts', False) is True
    policy = {'allow_small_unsigned': True} if allow_small_unsigned else {}
    classes = world.schema['classes']
    script_items = []
    for key, instance in world.instances.items():
        cname = classes[instance['class']]['name']
        if cname in ('Script', 'LocalScript', 'ModuleScript'):
            script_items.append((_script_priority(world, key, instance, cname), key, instance))
    if len(script_items) > 4096:
        raise ValueError('Script catalog exceeds 4096 entries')
    script_items.sort(key=lambda item: item[0])
    for _, key, instance in script_items:
        properties = instance['properties']
        # repr is only an in-memory fingerprint input; it is never printed/saved.
        fingerprint = hashlib.sha256()
        fingerprint.update(bytes((allow_small_unsigned,)))
        for name in ('Source', 'Bytecode', 'ScriptBytecode'):
            value = properties.get(name)
            fingerprint.update(repr(value).encode())
            for candidate in _candidates(value, world.shared):
                fingerprint.update(candidate)
        digest = fingerprint.digest()
        old = cache.get(key)
        if old and old[0] == digest:
            entry = old[1]
            length = old[2] if len(old) > 2 else len(json.dumps(entry, ensure_ascii=True).encode()) + 128
        else:
            queue = getattr(world, '_script_preparation_queue', None)
            source = properties.get('Source')
            plain = isinstance(source, str)
            if isinstance(source, bytes):
                try:plain = all(ord(c)>=32 or c in '\t\r\n' for c in source.decode('utf-8'))
                except UnicodeError:plain = False
            if queue is not None and not plain and any(next(_candidates(properties.get(name), world.shared), None) is not None
                    for name in ('Source','Bytecode','ScriptBytecode')):
                entry = queue.resolve(key, digest, properties, world.shared, **policy)
                if entry is None:
                    current[f'{key[0]}:{key[1]}'] = {'reason':'verification_pending'}
                    continue
            else:
                entry = prepare_script(properties, world.shared, **policy)
            length = len(json.dumps(entry, ensure_ascii=True).encode()) + 128
        if budget + length > MAX_CATALOG:
            entry = {'reason': 'catalog_size_limit'}
            length = 128
        else:
            next_cache[key] = (digest, entry, length)
        current[f'{key[0]}:{key[1]}'] = entry
        budget += length
    world._script_catalog_cache = next_cache
    queue = getattr(world, '_script_preparation_queue', None)
    if queue is not None:
        for key in set(queue.pending)-set(world.instances):
            queue.pending.pop(key)[1].cancel()
    return current
