"""Incremental, data-only world model. Never executes replicated scripts."""
import collections
import copy
import hashlib
import math

from wire_reader import Reader, WireError, decompress_stream, decompress_bytes
from replication_ping import read_ping
from received_attributes import attribute_update
from world_action_journal import WorldActionJournal

try:  # optional native decoder (scripts/build_native_wire.py); the Python decoder below is the reference implementation
    import _wire_native as _native
except ImportError:
    _native = None


def _copy(value):
    """copy.deepcopy for the plain data the decoder produces; the native copy defers to deepcopy for anything unusual."""
    native = _native
    if native is not None:
        try:
            return native.copy_tree(value)
        except native.Fallback:
            pass
    return copy.deepcopy(value)


_NO_PARENT_INDEXED = object()


class World:
    def __init__(self, schema):
        self.schema = schema
        self.instances = {}
        # Knowledge of the empty string's digest is not a server registration.
        # Start with no received entries so its first wire definition is consumed.
        self.shared = {}
        self.items = collections.Counter()
        self.context = None
        self._native_props = {}
        self._avatar_cache = {}
        self.tags = []
        self.guid_batches = []
        self.replication_foci = {}
        self.replication_frusta = {}
        self.stream_pin_data = []
        self.prefetch_data_info = []
        self.prefetch_requests = []
        self.persistent_player_changes = []
        self.qos_changes = []
        self.replicator_data = []
        self.instance_intents = []
        self.statistics = []
        self.regions = []
        self.last_region = None
        self.received_regions = set()
        # Arguments can contain private account/game data. Keep a bounded local
        # journal for protocol analysis; public reports expose only structure.
        self.events = collections.deque(maxlen=4096)
        self.pings = collections.deque(maxlen=256)
        self.client_scope = None
        self.global_flags = None
        self.top_containers = {}
        # Separate from explicit properties: enables faithful, provenance-aware
        # class defaults only after a fresh native creation record completes.
        self.creation = {}
        self.revision = 0
        self.property_versions = {}
        self.changes = collections.deque(maxlen=100000)
        self.event_sequence = 0
        self.event_journal = collections.deque(maxlen=4096)
        self.actions = WorldActionJournal()
        self._removal_children = None
        self._removal_parent = None
        self._removal_instances = None
        # Published only after an entire ordinary replication packet validates.
        # These are received wire changes, not local property revisions.
        self.received_property_changes = ()

    def touch(self, key, fields=(), *, deleted=False, created=False):
        fields = tuple(fields)
        if 'AttributesReplicate' in fields and not deleted:
            self.instances[key].pop('attributes',None)
        if (created or 'Parent' in fields) and self._removal_children is not None and not deleted:
            # Keep the removal index current instead of discarding it: a rebuild scans every instance, and one stream-out
            # packet after each create used to cost a full rescan (three quarters of the time spent building a 180k-action world).
            instance = self.instances.get(key)
            if instance is not None:
                new_parent = instance.get('parent')
                old_parent = self._removal_parent.get(key, _NO_PARENT_INDEXED)
                if old_parent is not new_parent and old_parent != new_parent:
                    if old_parent is not _NO_PARENT_INDEXED:
                        siblings = self._removal_children.get(old_parent)
                        if siblings is not None: siblings.discard(key)
                    self._removal_children[new_parent].add(key)
                    self._removal_parent[key] = new_parent
        self.revision += 1
        if not deleted:
            versions = self.property_versions.setdefault(key, {})
            for name in fields: versions[name] = self.revision
        self.changes.append((self.revision, key, deleted))
        action = {'sequence': self.revision, 'key': key,
                  'kind': 'remove' if deleted else 'create' if created else 'set'}
        if created:
            action['instance'] = _copy(self.instances[key])
            action['creation'] = dict(self.creation.get(key, {}))
            action['property_revisions'] = dict(self.property_versions.get(key, {}))
        elif not deleted:
            instance = self.instances[key]
            action['class'] = instance['class']
            action['fields'] = {name: _copy(instance.get('parent') if name == 'Parent'
                                                       else instance['properties'].get(name)) for name in fields}
        self.actions.append(action)

    def globals(self, payload):
        """Globals/top containers for capability set 0x100000.

        Native 104ca5c4c and 104df2254. No optional simulation-step field is
        negotiated. Parse the full packet before committing any state.
        """
        r = Reader(payload)
        if r.u8() != 129: raise WireError('Not a globals packet')
        flags = [r.u8() for _ in range(7)]
        if any(v > 1 for v in flags): raise WireError('Invalid globals boolean')
        scope = r.varuint()
        if scope == 0: raise WireError('Invalid client scope')
        containers = {}
        for _ in range(r.count(1000)):
            key, ci, first, second = self.guid(r), r.u16(), r.u8(), r.u8()
            if key is None or key in containers or ci >= len(self.schema['classes']) or max(first, second) > 1:
                raise WireError('Invalid top container')
            containers[key] = {'class': ci, 'flags': [first, second]}
        r.finish()
        for key, item in containers.items():
            if key in self.instances and self.instances[key]['class'] != item['class']:
                raise WireError('Top container class mismatch')
        self.client_scope, self.global_flags, self.top_containers = scope, flags, containers
        for key, item in containers.items():
            self.instances.setdefault(key, {'class': item['class'], 'properties': {}, 'parent': None})
            self.touch(key, created=True)

    def guid(self, r):
        scope = r.varuint()
        return (scope, r.u32()) if scope else None

    def remove_tree(self, key):
        self.remove_trees([key])

    def remove_trees(self, keys):
        keys = tuple(key for key in keys if key is not None)
        if not keys: return
        # Keep the index across stream-out packets. Creates and reparenting
        # invalidate it; removals maintain it without rescanning the world.
        if self._removal_children is None or self._removal_instances is not self.instances:
            self._removal_children = collections.defaultdict(set)
            self._removal_parent = {}
            for key, instance in self.instances.items():
                parent = instance.get('parent')
                self._removal_children[parent].add(key)
                self._removal_parent[key] = parent
            self._removal_instances = self.instances
        children = self._removal_children
        visited = set()
        for key in keys:
            pending = collections.deque([key])
            while pending:
                k = pending.popleft()
                if k in visited: continue
                visited.add(k)
                pending.extend(children.pop(k, ()))
                existed = self.instances.pop(k, None)
                self._removal_parent.pop(k, None)
                if existed is not None:
                    siblings = children.get(existed.get('parent'))
                    if siblings is not None: siblings.discard(k)
                self.creation.pop(k, None)
                self.property_versions.pop(k, None)
                if existed is not None: self.touch(k, deleted=True)

    def avatar(self, user_id):
        """Return evidence plus private references; callers publish evidence only."""
        def cls(instance):
            return self.schema['classes'][instance['class']]['name'] if instance else None
        # The three scans below are O(instances) and avatar() runs several times per tick in a world of 100k instances. Each result is
        # cached and re-validated in O(1); a stale entry triggers the original scan. Additions append to the dict, so the first match
        # in dict order (what next() returns) cannot change while the cached instance still qualifies. That relies on the protocol's
        # invariants: an instance never changes class, and the Player UserId / Humanoid parent are set when it is created.
        cache = self._avatar_cache
        cached = self.instances.get(cache.get(('player', user_id)))
        if cached is not None and cls(cached) == 'Player' and cached['properties'].get('UserId') == user_id:
            player_key = cache[('player', user_id)]
        else:
            player_key = next((k for k, v in self.instances.items() if cls(v) == 'Player'
                              and v['properties'].get('UserId') == user_id), None)
            cache[('player', user_id)] = player_key
        player = self.instances.get(player_key)
        character_key = player['properties'].get('Character') if player else None
        character = self.instances.get(character_key)
        root_key = character['properties'].get('PrimaryPart') if character else None
        root = self.instances.get(root_key)
        humanoid = None
        if character:
            cached = self.instances.get(cache.get(('humanoid', character_key)))
            if cached is not None and cached.get('parent') == character_key and cls(cached) == 'Humanoid':
                humanoid = cached
            else:
                found = next(((k, v) for k, v in self.instances.items() if v.get('parent') == character_key
                              and cls(v) == 'Humanoid'), None)
                if found is not None:
                    cache[('humanoid', character_key)] = found[0]
                    humanoid = found[1]
        position = None
        if root:
            for name in ('ReplicationPV', 'CFrame'):
                value = root['properties'].get(name)
                if isinstance(value, dict) and 'position' in value:
                    position = value['position']
                    break
        evidence = {
            'game_account_accepted': player is not None,
            'own_player_parented_to_players': bool(player and cls(self.instances.get(player.get('parent'))) == 'Players'),
            'character_reference_received': character_key is not None,
            'character_model_resolved': cls(character) == 'Model',
            'character_in_workspace': bool(character and cls(self.instances.get(character.get('parent'))) == 'Workspace'),
            'humanoid_present': humanoid is not None,
            'root_part_resolved': bool(root and cls(root) in ('Part', 'MeshPart')
                                      and root.get('parent') == character_key
                                      and root['properties'].get('Name') == b'HumanoidRootPart'),
            'root_position_finite': bool(isinstance(position, list) and len(position) == 3
                                         and all(isinstance(v, (int, float)) and math.isfinite(v) for v in position)),
            'health_explicitly_replicated': bool(humanoid and 'Health' in humanoid['properties']),
        }
        evidence['player_spawned'] = all(evidence[k] for k in (
            'game_account_accepted', 'character_model_resolved', 'character_in_workspace',
            'humanoid_present', 'root_part_resolved', 'root_position_finite'))
        if humanoid and (not math.isfinite(humanoid['properties'].get('Health', 1))
                         or humanoid['properties'].get('Health', 1) <= 0):
            evidence['player_spawned'] = False
        covered = False
        if evidence['root_position_finite']:
            coordinate = tuple(math.floor(v / 64) for v in position)
            covered = coordinate in self.received_regions and any(
                'radius' in region and region['radius'] >= 1
                and max(abs(x-y) for x, y in zip(coordinate, region['coordinate'])) < region['radius']
                for region in self.regions)
        evidence['spawn_region_received'] = covered
        if character:
            workspace = self.instances.get(character.get('parent'))
        else:
            cached = self.instances.get(cache.get('workspace'))
            if cached is not None and cls(cached) == 'Workspace':
                workspace = cached
            else:
                found = next(((k, v) for k, v in self.instances.items() if cls(v) == 'Workspace'), None)
                workspace = found[1] if found else None
                cache['workspace'] = found[0] if found else None
        streaming = workspace['properties'].get('StreamingEnabled') if cls(workspace) == 'Workspace' else None
        evidence['workspace_streaming_enabled'] = streaming
        evidence['initial_world_received'] = 13 in self.tags
        evidence['spawn_world_received'] = covered or (streaming is False and evidence['initial_world_received'])
        evidence['root_unanchored_by_server'] = bool(root and root['properties'].get('Anchored') is False)
        evidence['server_gameplay_paused'] = player['properties'].get('GameplayPaused') if player else None
        evidence['movement_ready'] = (evidence['player_spawned'] and evidence['spawn_world_received']
                                      and evidence['root_unanchored_by_server'])
        return {'evidence': evidence, 'root_key': root_key, 'root': root,
                'character_key': character_key, 'humanoid': humanoid, 'position': position,
                'player_key': player_key, 'player': player}

    @staticmethod
    def compact_position(r):
        def signed32(value):
            value &= 0xffffffff
            return value - (1 << 32) if value & 0x80000000 else value
        b = r.u8()
        sx, sy, sz = bool(b & 4), bool(b & 2), bool(b & 1)
        if b <= 0x27:
            n = r.u32()
            xyz = [signed32((2*n) | (sx<<31)) >> 21,
                   signed32(((n<<11)&0x7fe00000) | (sy<<31)) >> 21,
                   signed32((sz<<31) | ((n&1023)<<21)) >> 21]
            divisor = 1023.0
        elif b <= 0x57:
            xyz = [signed32((s<<31) | (r.u16()<<15)) >> 15 for s in (sx, sy, sz)]
            divisor = 65535.0
        else:
            n, m = r.u32(), r.u32()
            xyz = [signed32((((b>>2)<<32)|n)>>1) >> 10,
                   signed32((sy<<31) | ((((n&2047)<<10)|(m>>21))<<10)) >> 10,
                   signed32((sz<<31) | ((m&0x1fffff)<<10)) >> 10]
            divisor = 2097151.0
        return [math.ldexp(v/divisor, b>>3) for v in xyz]

    def shared_entry(self, r):
        key, marker = r.take(16), r.u8()
        if marker == 0:
            value = r.take(r.count(16 * 1024 * 1024))
            # Native labels retain MD5 terminology, but the current wire hash
            # is BLAKE2b-128 (also verified against every captured entry).
            if hashlib.blake2b(value, digest_size=16).digest() != key:
                raise WireError('Shared string digest mismatch')
            self.shared[key] = value
        elif marker != 1 or key not in self.shared:
            raise WireError('Unknown shared string marker/reference')
        return key

    def content_id(self, r, compressed):
        if not compressed: return r.take(r.count(16 * 1024 * 1024))
        marker = r.u8()
        index = marker >> 1
        if index >= len(self.schema['strings']): raise WireError('Invalid content prefix index')
        prefix = self.schema['strings'][index].encode()
        suffix = str(r.signed(64)).encode() if marker & 1 else r.take(r.count(16 * 1024 * 1024))
        return prefix + suffix

    def value(self, r, p, deferred, depth=0, compressed=False, preserve_variants=False):
        if depth > 16: raise WireError('Value nesting exceeds limit')
        t = p['type']
        self.context = {'property': p.get('name'), 'type': t, 'offset': r.pos}
        if t in (2, 8): return r.take(r.count(16 * 1024 * 1024))
        if t == 33: return self.content_id(r, compressed)
        if t in (0, 3): return None
        if t in (29, 30):
            return [self.variant(r, deferred, depth+1, compressed, preserve_variants) for _ in range(r.count(10000))]
        if t in (31, 32):
            return [(r.take(r.count()), self.variant(r, deferred, depth+1, compressed, preserve_variants)) for _ in range(r.count(10000))]
        if t == 7: return r.varuint()
        if t == 18: return r.u16()
        if t == 9:
            value = r.u8()
            if value > 1: raise WireError('Invalid boolean')
            return bool(value)
        if t == 10: return r.signed(32)
        if t == 11: return r.f32()
        if t == 12: return r.f64()
        if t == 48:
            # 104f201f0 -> 1015f9ea4 reads signed Unix milliseconds;
            # 102a0f18c constructs DateTime. Retain its type inside variants.
            millis = r.number('q')
            if not -17987443200000 <= millis <= 253402300799999:
                raise WireError('DateTime timestamp outside supported range')
            return {'$datetime': millis}
        if t == 13: return [r.f32(), r.number('i')]
        if t == 14: return [r.f32(), r.number('i'), r.f32(), r.number('i')]
        if t in (21, 37): return [r.f32(), r.f32()]
        if t == 40: return [r.f32() for _ in range(4)]
        if t in (19, 22, 36): return [r.f32(), r.f32(), r.f32()]
        if t == 20: return list(r.take(3))
        if t == 27:
            position = [r.f32(), r.f32(), r.f32()]
            rotation = r.u8()
            return {'position': position, 'rotation_id': rotation,
                    'packed_rotation': r.take(6).hex() if rotation == 0 else None}
        if t == 41:
            flag = r.u8()
            return [r.f32() for _ in range(6 if flag >= 2 else 5)] if flag & 1 else None
        if t == 51:
            flag = r.u8()
            if not flag & 128: return None
            rotation = r.take(6).hex() if flag == 128 else flag & 127
            return {'rotation': rotation, 'position': [r.f32(), r.f32(), r.f32()]}
        if t == 54:
            return [r.u16(), r.u8(), r.take(r.u32()), r.take(r.u32())]
        if t == 56:
            # Native 104da8d24 reads compressed and expanded varuint32 sizes.
            # Its zero-compressed-size branch copies expanded bytes verbatim.
            compressed_size, expanded_size = r.varuint(), r.varuint()
            if max(compressed_size, expanded_size) > 1024*1024:
                raise WireError('Replicated buffer exceeds runtime limit')
            if compressed_size:
                import zstandard
                encoded = r.take(compressed_size)
                try:
                    data = decompress_bytes(encoded, expanded_size, 1024*1024)
                except zstandard.ZstdError as error:
                    raise WireError('Invalid compressed replicated buffer') from error
            else:
                data = r.take(expanded_size)
            return {'$buffer_hex': data.hex()}
        if t == 60:
            # Legacy LR reference: 104d886b0 -> 1044a805c reads a uint64
            # identity plus a varuint32 index, then a uint64 type word. Keep
            # the reference opaque; decoding it does not construct mesh data.
            return {'lr_reference': {'identity': r.u64(), 'index': r.varuint(),
                                     'type_word': r.u64()}}
        if t == 61:
            marker = r.varuint()
            if marker == 0: return None
            if marker == 1: return self.content_id(r, compressed)
            raise WireError('Unsupported content marker %d' % marker)
        if t in (28, 69): return self.guid(r)
        if t == 34: return r.varuint()
        if t in (35, 38):
            count = r.u32()
            if count > 20: raise WireError('Sequence too long')
            return [[r.f32() for _ in range(3 if t == 35 else 5)] for _ in range(count)]
        if t == 57:
            flags = r.u8()
            pos = [0., 0., 0.] if flags & 128 else self.compact_position(r)
            rot = flags & 31
            rotation = [r.f32() for _ in range(7)] if rot == 31 else r.take(6).hex() if rot == 0 else rot
            velocities = []
            for mask in (64, 32):
                if flags & mask: velocities.append(None)
                else:
                    b = r.u8()
                    velocities.append([b, r.u32() if b else 0])
            return {'position': pos, 'rotation': rotation, 'packed_velocities': velocities,
                    'position_present': not bool(flags & 128)}
        if t == 44: return r.signed(64)
        if t in (65, 66, 67):
            from animation_wire_codec import (decode_anim_track_play_state,
                decode_anim_track_metadata, decode_anim_track_weight)
            decoder, size, label = {
                65: (decode_anim_track_play_state, 13, 'anim_track_play_state'),
                66: (decode_anim_track_metadata, 3, 'anim_track_metadata'),
                67: (decode_anim_track_weight, 16, 'anim_track_weight'),
            }[t]
            try:
                fields, _ = decoder(r.take(size))
            except ValueError as error:
                raise WireError('Invalid animation track property value') from error
            return {label: fields}
        if t == 68: return [r.signed(64), r.varuint(), r.signed(64), r.signed(64)]
        if t in (52, 55): return r.u64()
        if t in (46, 47):
            key = r.take(16)
            if key not in self.shared: deferred.add(key)
            return {'shared': key.hex()}
        if t == 49:
            marker = r.u8()
            if marker & 128:
                index = marker & 127
                if index == 127: index += r.varuint()
                return self.schema['names'][index].encode()
            size = r.count() if marker == 127 else marker
            return r.take(size)
        raise WireError('Unimplemented property type %d' % t)

    def variant(self, r, deferred, depth, compressed=False, preserve_types=False):
        p = {'type': r.u8(), 'name': 'Event variant'}
        if p['type'] == 7: p['enum'] = r.u16()
        value = self.value(r, p, deferred, depth, compressed, preserve_types)
        if preserve_types:
            return {'$remote_variant': {'type': p['type'], 'value': value}}
        return value

    def property_list(self, r, instance, deferred, compressed=False):
        cls = self.schema['classes'][instance['class']]
        native = _native
        if native is not None:
            # One native call decodes the whole list. Anything it does not handle exactly (malformed data, rare property types)
            # raises Fallback and the Python code below decodes the same bytes, producing the original errors.
            try:
                props = self._native_props.get(instance['class'])
                if props is None:
                    props = tuple((p['name'], p['type']) for p in (self.schema['properties'][i] for i in cls['properties']))
                    self._native_props[instance['class']] = props
                names, strings = self.schema.get('names', []), self.schema.get('strings', [])
            except (KeyError, IndexError, TypeError):
                props = None
            if props is not None:
                try:
                    position, values, found = native.property_list(r.data, r.pos, props, names, strings, self.shared, compressed)
                except native.Fallback:
                    pass
                else:
                    r.pos = position
                    instance['properties'].update(values)
                    deferred.update(found)
                    return
        last = -1
        while True:
            index = r.u8()
            if index == 255: return
            if index <= last or index >= len(cls['properties']):
                raise WireError('Invalid property order/index')
            last = index
            p = self.schema['properties'][cls['properties'][index]]
            instance['properties'][p['name']] = self.value(r, p, deferred, compressed=compressed)

    def new_instance(self, r, lists=2, inline_shared=True, batch_deferred=None):
        key, ci = self.guid(r), r.u16()
        if key is None or ci >= len(self.schema['classes']):
            raise WireError('Invalid instance header')
        fresh = key not in self.instances
        self.creation[key] = {'fresh': fresh, 'complete': False,
                              'property_lists': lists, 'ordinary': lists == 2 and inline_shared}
        instance = self.instances.setdefault(key, {'class': ci, 'properties': {}})
        if instance['class'] != ci: raise WireError('Instance changed class')
        deferred = set() if batch_deferred is None else batch_deferred
        for index in range(lists):
            self.property_list(r, instance, deferred, compressed=(lists == 2 and index == 0))
        if inline_shared:
            while deferred:
                deferred.discard(self.shared_entry(r))
        elif deferred and batch_deferred is None:
            raise WireError('Cached instance references unknown shared string')
        instance['parent'] = self.guid(r)
        self.creation[key]['complete'] = True
        self.touch(key, [*instance['properties'], 'Parent'], created=True)
        return instance

    def stats_item(self, r):
        def string(reader):
            size = reader.u32()
            if size > 16 * 1024 * 1024: raise WireError('Stats string exceeds limit')
            return reader.take(size)

        def boolean(reader):
            value = reader.u8()
            if value > 1: raise WireError('Invalid stats boolean')
            return bool(value)

        version = r.u32()
        initial_values = [r.f32(), r.f32()] if version >= 9 else []
        version8_text = None
        if version >= 8 and boolean(r):
            content = decompress_stream(r)
            version8_text = string(content)
            content.finish()
        version7_text = None
        if version >= 7:
            expected = r.u32()
            content = decompress_stream(r)
            version7_text = string(content)
            content.finish()
            if len(version7_text) != expected: raise WireError('Stats text length mismatch')
        memory = None
        if version >= 6:
            memory = {'total': r.f64(), 'categories': []}
            for _ in range(2):
                count = r.u32()
                if count > 100000: raise WireError('Too many memory stats entries')
                memory['categories'].append([
                    {'name': string(r), 'memory': r.f64()} for _ in range(count)
                ])
        datastore = None
        if version >= 3:
            enabled = boolean(r)
            datastore = {'enabled': enabled,
                         'counters': [r.u32() for _ in range(6)] if enabled else []}
        jobs = []
        for _ in range(100000):
            if boolean(r): break
            jobs.append({'name': string(r), 'values': [r.f32(), r.f32(), r.f32()]})
        else: raise WireError('Too many job stats entries')
        scripts = []
        for _ in range(100000):
            if boolean(r): break
            scripts.append({'name': string(r), 'value': r.f32(), 'count': r.u32()})
        else: raise WireError('Too many script stats entries')
        return {'version': version, 'initial_values': initial_values,
                'version8_text': version8_text, 'version7_text': version7_text,
                'memory': memory, 'datastore': datastore, 'jobs': jobs, 'scripts': scripts,
                'final_values': [r.f32() for _ in range(5)]}

    def packet(self, payload):
        r = Reader(payload)
        packet_pings = []
        property_changes = []
        self.received_property_changes = ()
        if r.u8() != 131: raise WireError('Not a replication packet')
        while r.remaining:
            kind = r.u8()
            if kind == 0:
                r.finish()
                self.received_property_changes = tuple(property_changes)
                return packet_pings
            self.items[kind] += 1
            if kind == 1:
                self.remove_tree(self.guid(r))
            elif kind == 2:
                self.new_instance(r)
            elif kind == 3:
                key, pi, reset_version = self.guid(r), r.u16(), r.u8()
                if reset_version > 1 or pi > self.schema['parent_property_id']:
                    raise WireError('Invalid property change header')
                instance = self.instances.get(key)
                deferred = set()
                if pi == self.schema['parent_property_id']:
                    value = self.guid(r)
                    if instance is not None:
                        instance['parent'] = value
                        self.touch(key, ['Parent'])
                else:
                    p = self.schema['properties'][pi]
                    value = self.value(r, p, deferred, compressed=True)
                    if instance is not None:
                        instance['properties'][p['name']] = value
                        self.touch(key, [p['name']])
                while deferred: deferred.discard(self.shared_entry(r))
                if instance is not None:
                    property_changes.append((key, pi, bool(reset_version), instance))
            elif kind == 19:
                key, parent = self.guid(r), self.guid(r)
                if key in self.instances:
                    self.instances[key]['parent'] = parent
                    self.touch(key, ['Parent'])
            elif kind == 20:
                wide = r.u8()
                if wide > 1: raise WireError('Invalid region coordinate width')
                coordinate = [r.number('i' if wide else 'b') for _ in range(3)]
                self.regions.append({'coordinate': coordinate, 'radius': r.number('i'), 'version': r.u32()})
            elif kind == 7:
                key, ei = self.guid(r), r.u16()
                if ei >= len(self.schema['events']): raise WireError('Invalid event ID')
                event = self.schema['events'][ei]
                deferred = set()
                arguments = [self.value(r, dict(arg, name='Event:' + event['name']), deferred, compressed=True,
                                        preserve_variants=(event['name'] in ('RemoteOnInvokeClient','OnClientEvent') or
                                            (event['name']=='RemoteOnInvokeSuccess' and
                                             getattr(self, 'preserve_remote_success_variants', False))))
                             for arg in event['arguments']]
                while deferred: deferred.discard(self.shared_entry(r))
                self.event_sequence += 1
                record = {'key': key, 'event': ei, 'arguments': arguments}
                self.events.append(record)
                self.event_journal.append((self.event_sequence, record))
                self.revision += 1
                self.actions.append({'sequence': self.revision, 'kind': 'event', **record})
            elif kind == 21:
                key = self.guid(r)
                # The version byte is conditional on the property-version
                # capability; our negotiated capability set does not enable it.
                name, value = r.take(r.count(100)), r.take(r.count(1024*1024))
                if key in self.instances:
                    update=attribute_update(name,value)
                    attributes=self.instances[key].setdefault('attributes', {})
                    if name not in attributes and len(attributes)>=1024:
                        raise WireError('Received attribute count exceeds limit')
                    attributes[name] = value
                    self.revision += 1
                    self.changes.append((self.revision,key,False))
                    self.actions.append({'sequence':self.revision,'kind':'attribute','key':key,
                                         'attribute_update':update})
            elif kind in (5, 6):
                ping = read_ping(r, kind)
                self.pings.append(ping)
                packet_pings.append(ping)
                if len(packet_pings) > 64:
                    raise WireError('Too many ping items')
            elif kind == 22:
                subtype = r.u8()
                content = decompress_stream(r)
                if subtype == 1:
                    while content.remaining: self.shared_entry(content)
                elif subtype in (2, 3, 4):
                    count = r.u32()
                    if count > 100000: raise WireError('Too many cached instances')
                    offsets = {r.varuint(): r.varuint() for _ in range(r.count())}
                    for _ in range(count):
                        while content.pos in offsets: content.take(offsets[content.pos])
                        self.new_instance(content, lists=1, inline_shared=False)
                    while content.pos in offsets: content.take(offsets[content.pos])
                    content.finish()
                else:
                    raise WireError('Unsupported cached replication subtype %d' % subtype)
            elif kind in (11, 13):
                count = r.u32()
                if count > 100000: raise WireError('Too many streamed instances')
                if count:
                    content = decompress_stream(r)
                    deferred = set()
                    for _ in range(count):
                        self.new_instance(content, lists=1, inline_shared=False, batch_deferred=deferred)
                    while deferred: deferred.discard(self.shared_entry(content))
                    content.finish()
                if kind == 13:
                    for _ in range(100000):
                        flags = r.u8()
                        region = {'flags': flags}
                        if flags & ~8 == 0:
                            wide = r.u8()
                            if wide > 1: raise WireError('Invalid region coordinate width')
                            region['coordinate'] = [r.number('i' if wide else 'b') for _ in range(3)]
                        elif flags & ~8 in (1, 2, 3):
                            if self.last_region is None: raise WireError('Relative region before absolute region')
                            region['coordinate'] = list(self.last_region)
                            axis = {1: 1, 2: 2, 3: 0}[flags & ~8]
                            region['coordinate'][axis] += 1
                        elif flags & ~8 != 4:
                            raise WireError('Unsupported streamed region flag')
                        if 'coordinate' in region:
                            self.last_region = tuple(region['coordinate'])
                            self.received_regions.add(self.last_region)
                        self.regions.append(region)
                        if not flags & 8: break
                    else: raise WireError('Too many streamed regions')
            elif kind == 16:
                self.tags.append(r.number('i'))
            elif kind == 17:
                self.statistics.append(self.stats_item(r))
            elif kind == 35:
                self.server_step = r.number('i')
            elif kind == 26:
                focus_id = r.u32()
                floating_center = r.u8()
                if floating_center > 1: raise WireError('Invalid replication focus coordinate encoding')
                center = ([r.f32() for _ in range(3)] if floating_center
                          else [r.number('b') for _ in range(3)])
                radius = r.f32()
                optional_float = r.f32()
                flags = [r.u8(), r.u8()]
                if any(value > 1 for value in flags): raise WireError('Invalid replication focus boolean')
                self.replication_foci[focus_id] = {
                    'center': center, 'radius': radius,
                    'optional_float': None if optional_float == -1.0 else optional_float,
                    'flags': [bool(value) for value in flags], 'timeout': r.u32(),
                }
            elif kind == 24:
                floating_center = r.u8()
                if floating_center > 1: raise WireError('Invalid prefetch coordinate encoding')
                center = ([r.f32() for _ in range(3)] if floating_center
                          else [r.number('b') for _ in range(3)])
                self.prefetch_data_info.append({'center': center, 'values': [r.f32(), r.f32()]})
            elif kind == 25:
                self.prefetch_requests.append({
                    'center': [r.f32() for _ in range(3)],
                    'radius': r.f64(), 'timeout': r.f32(),
                })
            elif kind in (29, 30):
                self.persistent_player_changes.append(('add' if kind == 29 else 'remove', self.guid(r)))
            elif kind == 31:
                qos_type, value = r.u8(), r.u8()
                if qos_type not in (0, 3):
                    self.qos_changes.append({'type': qos_type, 'value': value,
                                             'text': r.take(r.u32())})
            elif kind == 32:
                item_id, size = r.u32(), r.u32()
                if size > 16 * 1024 * 1024: raise WireError('Replicator data exceeds limit')
                self.replicator_data.append({'id': item_id, 'data': r.take(size)})
            elif kind == 37:
                count = r.u32()
                if count > 100000: raise WireError('Too many pinned stream instances')
                if count:
                    content = decompress_stream(r)
                    deferred = set()
                    for _ in range(count):
                        self.new_instance(content, lists=1, inline_shared=False, batch_deferred=deferred)
                    while deferred: deferred.discard(self.shared_entry(content))
                    content.finish()
                points = []
                for _ in range(100000):
                    flags = r.u8()
                    if flags & ~8 == 0:
                        floating_center = r.u8()
                        if floating_center > 1: raise WireError('Invalid stream pin coordinate encoding')
                        points.append([r.f32() for _ in range(3)] if floating_center
                                      else [r.number('b') for _ in range(3)])
                    if not flags & 8: break
                else: raise WireError('Too many stream pin points')
                key, value, pinned = self.guid(r), r.f32(), r.u8()
                if pinned > 1: raise WireError('Invalid stream pin boolean')
                self.stream_pin_data.append({'points': points, 'key': key,
                                             'value': value, 'pinned': bool(pinned)})
            elif kind == 39:
                focus_id = r.u32()
                self.replication_frusta[focus_id] = [r.f32() for _ in range(15)]
            elif kind == 36:
                self.replication_foci.pop(r.u32(), None)
            elif kind == 40:
                self.replication_frusta.pop(r.u32(), None)
            elif kind == 41:
                count = r.u32()
                if count > 100000: raise WireError('Too many instance intents')
                for _ in range(count):
                    self.instance_intents.append({'key': self.guid(r), 'intent': r.u8()})
            elif kind == 27:
                count = r.u32()
                if count > 100000: raise WireError('Too many batched instance references')
                keys = [self.guid(r) for _ in range(count)]
                self.guid_batches.append(keys)
                self.remove_trees(keys)
            else:
                raise WireError('Unimplemented replication kind %d' % kind)
        raise WireError('Missing replication terminator')
