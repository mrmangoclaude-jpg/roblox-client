"""Export decoded instances for real Luau source execution, with value provenance."""
import base64
import json
import math
from functools import lru_cache
from pathlib import Path

from world_replication import World
from world_schema import parse_schema
from script_catalog import script_catalog
from received_attributes import attribute_snapshot
from received_tags import tag_snapshot
from physics_rotation import RotationField, rotation_is_identity
from collision_groups import part_group
from no_collision_constraints import constructor_defaults as constraint_defaults


ROOT = Path(__file__).resolve().parents[1]
MAX_NODES = 20000
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


@lru_cache(maxsize=1)
def _archivable_defaults():
    classes=json.loads((ROOT/'runtime/class-constructors-745.json').read_text())['classes']
    return {name: fields['properties']['Archivable']['value'] for name,fields in classes.items()
            if fields.get('properties',{}).get('Archivable',{}).get('type')=='boolean'}


def _class_property_types(world, class_index):
    cache = getattr(world, '_class_property_types_cache', None)
    if cache is None or getattr(world, '_class_property_types_schema_id', None) != id(world.schema):
        props = world.schema['properties']
        cache = [
            {props[pi]['name']: props[pi]['type'] for pi in cls.get('properties', ())}
            for cls in world.schema['classes']
        ]
        try:
            world._class_property_types_cache = cache
            world._class_property_types_schema_id = id(world.schema)
        except AttributeError:
            pass
    return cache[class_index]


def instance_id(key):
    return None if key is None else f'{key[0]}:{key[1]}'


def _encode(value, type_id=None, depth=0):
    if depth > 16:
        raise ValueError('Snapshot property nesting exceeds limit')
    if isinstance(value, dict) and set(value) == {'$remote_variant'}:
        typed = value['$remote_variant']
        kind = typed['type']
        if kind == 30:
            return {'$remote_array': [_encode(item, depth=depth+1) for item in typed['value']]}
        if kind in (31, 32):
            return {'$remote_map': [[_encode(key, depth=depth+1), _encode(item, depth=depth+1)]
                                   for key, item in typed['value']]}
        if kind == 27:
            from remote_datatypes import remote_cframe
            return remote_cframe(typed['value'])
        # Keep unsupported engine variants distinct from primitive values:
        # an EnumItem must not silently become a number, nor a Vector3 a table.
        if kind not in (0, 2, 3, 8, 9, 10, 11, 12, 13, 14, 18, 19, 20, 21, 22,
                        28, 37, 40, 48, 56, 69):
            return {'$unsupported_remote_type': kind}
        return _encode(typed['value'], kind, depth+1)
    if type_id in (28, 69):
        return {'$ref': instance_id(value)} if value is not None else None
    if type_id == 18:
        return {'$brickcolor': value}
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            return {'$bytes_hex': value.hex()}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return {'$number': 'nan' if math.isnan(value) else 'inf' if value > 0 else '-inf'}
        return value
    # Preserve engine datatypes across the data-only world -> Luau boundary.
    # These IDs come from the v3 schema and World.value's matching wire readers.
    # Type 19 is Color3, not Vector3; type 22 is the three-dimensional vector.
    component_counts = {13: 2, 14: 4, 19: 3, 20: 3, 21: 2, 22: 3, 37: 2, 40: 4}
    if type_id in component_counts:
        if (not isinstance(value, (list, tuple)) or len(value) != component_counts[type_id]
                or any(type(v) not in (int, float) for v in value)):
            raise ValueError('Invalid engine datatype components')
        values = [_encode(v, depth=depth+1) for v in value]
        if type_id == 13:
            return {'$udim': values}
        if type_id == 14:
            return {'$udim2': [{'$udim': values[:2]}, {'$udim': values[2:]}]}
        if type_id == 19:
            return {'$color3': values}
        if type_id == 20:
            if any(type(v) is not int or not 0 <= v <= 255 for v in value):
                raise ValueError('Invalid byte color components')
            return {'$color3': [v / 255 for v in value]}
        if type_id == 21:
            return {'$vector2': values}
        if type_id == 37:
            return {'$number_range': values}
        if type_id == 40:
            return {'$rect': [{'$vector2': values[:2]}, {'$vector2': values[2:]}]}
        return {'$vector3': values}
    if type_id in (35, 38):
        if not isinstance(value, (list, tuple)) or len(value) > 20:
            raise ValueError('Invalid engine sequence')
        keyframes = []
        for keyframe in value:
            count = 3 if type_id == 35 else 5
            if (not isinstance(keyframe, (list, tuple)) or len(keyframe) != count
                    or any(type(v) not in (int, float) for v in keyframe)):
                raise ValueError('Invalid engine sequence keypoint')
            values = [_encode(v, depth=depth+1) for v in keyframe]
            if type_id == 35:
                keyframes.append({'$number_keypoint': values})
            else:
                if keyframe[4] != 0:
                    raise ValueError('Unsupported color sequence envelope')
                keyframes.append({'$color_keypoint': [values[0], {'$color3': values[1:4]}]})
        return {'$number_sequence' if type_id == 35 else '$color_sequence': keyframes}
    if type_id in (27, 51, 57) and isinstance(value, dict):
        frame = dict(value)
        selector = frame.get('rotation_id') if type_id == 27 else frame.get('rotation')
        if type(selector) is int:
            if type_id == 27:
                field = RotationField(selector, 'selector', None)
            elif type_id == 51:
                field = RotationField(0x80 | selector, 'selector', selector)
            else:
                field = RotationField(selector, 'selector', selector)
            if rotation_is_identity(field, 'type%d' % type_id) is True:
                frame['rotation_selector'] = selector
                frame['rotation'] = [1., 0., 0., 0., 1., 0., 0., 0., 1.]
                frame['rotation_mapping'] = 'native_745_identity'
        return {'$cframe': _encode(frame, depth=depth+1)}
    if isinstance(value, tuple) and len(value) == 2 and all(type(v) is int for v in value):
        return {'$ref': instance_id(value)}
    if isinstance(value, (list, tuple)):
        return [_encode(item, depth=depth+1) for item in value]
    if isinstance(value, dict):
        return {str(k): _encode(v, depth=depth+1) for k, v in value.items()}
    raise ValueError('Unsupported snapshot property type')


def _received_value(world, value, type_id=None):
    if type_id in (46, 47) and isinstance(value, dict) and set(value) == {'shared'}:
        try:
            key = bytes.fromhex(value['shared'])
            if len(key) == 16 and key in world.shared:
                return _encode(world.shared[key])
        except (ValueError, TypeError):
            pass
        # Retain unresolved provenance. Never replace missing shared bytes with
        # an empty string or a payload captured from a different world.
    return _encode(value, type_id)


def _node_snapshot(world, key, instance, *, creation=None, versions=None):
    cls = world.schema['classes'][instance['class']]
    types = _class_property_types(world, instance['class'])
    properties, origins = {}, {}
    for name, value in instance['properties'].items():
        if name in ('Source', 'Bytecode', 'ScriptBytecode'):
            continue
        properties[name] = _received_value(world, value, types.get(name))
        origins[name] = 'received'
    creation = world.creation.get(key, {}) if creation is None else creation
    if cls['name'] == 'NoCollisionConstraint':
        for name, value in constraint_defaults(creation).items():
            if name not in properties:
                properties[name] = value
                origins[name] = 'class_default'
    if (not {'Archivable','archivable'} & properties.keys()
            and all(creation.get(flag) for flag in ('fresh','complete'))
            and cls['name'] in _archivable_defaults()):
        properties['Archivable']=_archivable_defaults()[cls['name']]
        origins['Archivable']='class_default'
    if (cls['name'] in ('Part', 'MeshPart') and 'Anchored' not in properties
            and all(creation.get(flag) for flag in ('fresh', 'complete', 'ordinary'))):
        properties['Anchored'] = False
        origins['Anchored'] = 'class_default'
    versions = dict(world.property_versions.get(key, {}) if versions is None else versions)
    if 'CollisionGroup' not in properties and 'CollisionGroupReplicate' in properties:
        try:
            properties['CollisionGroup'] = part_group(properties)
        except ValueError:
            # Keep the private bytes intact; consumers must report unavailable
            # state instead of exporting a fabricated Default name.
            pass
        else:
            origins['CollisionGroup'] = 'derived_received'
            versions['CollisionGroup'] = versions.get('CollisionGroupReplicate', 0)
    if 'Size' not in properties and 'size' in properties and types.get('size') == 22:
        properties['Size'] = properties['size']
        origins['Size'] = 'derived_received'
        versions['Size'] = versions.get('size', 0)
    frames = [name for name in ('CFrame', 'ReplicationPV')
              if isinstance(instance['properties'].get(name), dict)
              and 'position' in instance['properties'][name]]
    if frames:
        frame_name = max(frames, key=lambda name: versions.get(name, 0))
        frame = instance['properties'][frame_name]
        if frame_name == 'ReplicationPV':
            properties['CFrame'] = _encode(frame, types.get(frame_name, 57))
            origins['CFrame'] = 'derived_received'
            versions['CFrame'] = versions.get(frame_name, 0)
            velocities = frame.get('decoded_velocities')
            if isinstance(velocities, list) and len(velocities) == 2:
                for name, vector in zip(('AssemblyLinearVelocity', 'AssemblyAngularVelocity'), velocities):
                    if (isinstance(vector, list) and len(vector) == 3
                            and all(type(v) in (int, float) and math.isfinite(v) for v in vector)
                            and versions.get(name, 0) <= versions.get(frame_name, 0)):
                        properties[name] = {'$vector3': list(vector)}
                        origins[name] = 'derived_received'
                        versions[name] = versions.get(frame_name, 0)
        if 'Position' not in properties or versions.get('Position', 0) <= versions.get(frame_name, 0):
            properties['Position'] = {'$vector3': list(frame['position'])}
            origins['Position'] = 'derived_received'
            versions['Position'] = versions.get(frame_name, 0)
    parent = 'game' if key in world.top_containers else instance_id(instance.get('parent'))
    raw_name = instance['properties'].get('Name', cls['name'])
    name = raw_name.decode('utf-8', 'replace') if isinstance(raw_name, bytes) else str(raw_name)
    return {'id': instance_id(key), 'class_name': cls['name'], 'name': name,
            'parent': parent, 'properties': properties, 'origins': origins,
            # A fresh cached/streamed record also creates an instance before
            # applying its property list. Its transport has one list instead
            # of two; that does not remove the class constructor. Keep these
            # defaults separate from received fields, and exclude partial or
            # reused records whose initialization state is unknown.
            'constructor_defaults_known': all(creation.get(flag, False)
                for flag in ('fresh', 'complete')),
            **attribute_snapshot(instance['properties'],instance.get('attributes'),creation),
            **tag_snapshot(instance['properties'],world.shared,creation),
            'property_revisions': versions}


def make_world_snapshot(world, user_id, *, job_id=None, include_script_sources=True):
    if len(world.instances) > MAX_NODES-1:
        raise ValueError('World snapshot node limit exceeded')
    parents = json.loads((ROOT/'runtime/class-parents-745.json').read_text())['parents']
    class_parents = {name: parent for name, parent in parents.items() if isinstance(parent, str)}
    nodes = [{'id': 'game', 'class_name': 'DataModel', 'name': 'Game',
              'parent': None, 'properties': {}, 'origins': {}}]
    if job_id is not None:
        nodes[0]['properties']['JobId'] = job_id
        nodes[0]['origins']['JobId'] = 'issued_session'
    services = {}
    for key, instance in world.instances.items():
        node = _node_snapshot(world, key, instance)
        if key in world.top_containers:
            services[node['class_name']] = node['id']
        nodes.append(node)
    for service_name in ('ContentProvider', 'PathfindingService'):
        if service_name not in services:
            service_id = f'service:{service_name}'
            services[service_name] = service_id
            nodes.append({'id': service_id, 'class_name': service_name,
                          'name': service_name, 'parent': 'game',
                          'properties': {}, 'origins': {}})
    defaults = {
        'Player': {
            'Character': None,
            'CameraMinZoomDistance': 0.5,
            'CameraMaxZoomDistance': 400.0,
        },
        'ImageHandleAdornment': {
            'Size': {'$vector2': [1.0, 1.0]},
        },
        'ParticleEmitter': {
            'EmissionDirection': {'$enum': {'type': 'NormalId', 'name': 'Top', 'value': 1}},
        },
        'ScreenGui': {
            'ZIndexBehavior': {'$enum': {'type': 'ZIndexBehavior', 'name': 'Sibling', 'value': 1}},
        },
        'TextChatService': {
            'ChatVersion': {'$enum': {'type': 'ChatVersion', 'name': 'TextChatService', 'value': 1}},
        },
    }
    default_origins = {
        class_name: {prop: 'class_default' for prop in props}
        for class_name, props in defaults.items()
    }
    player = world.avatar(user_id)['player_key']
    snapshot = {'version': 1, 'local_player': instance_id(player), 'services': services,
                'nodes': nodes, 'class_parents': class_parents, 'defaults': defaults,
                'default_origins': default_origins, 'sequence': world.revision,
                'script_sources': script_catalog(world) if include_script_sources else {},
                'initial_replication_complete': 13 in world.tags,
                'class_events': {cls['name']: [world.schema['events'][i]['name'] for i in cls.get('events', [])]
                                 for cls in world.schema['classes']},
                'class_event_signatures': {cls['name']: {world.schema['events'][i]['name']: [p['type'] for p in world.schema['events'][i]['arguments']]
                                                       for i in cls.get('events', [])} for cls in world.schema['classes']},
                'class_property_types': {cls['name']: {world.schema['properties'][i]['name']: world.schema['properties'][i]['type']
                                                     for i in cls.get('properties', [])} for cls in world.schema['classes']}}
    if len(json.dumps(snapshot, ensure_ascii=True, allow_nan=False).encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError('World snapshot exceeds 8 MiB')
    return snapshot


def make_world_delta(world, since_revision, *, max_actions=None, max_bytes=None):
    if max_actions is not None and (type(max_actions) is not int or max_actions < 1):
        raise ValueError('Delta action budget must be positive')
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 1024):
        raise ValueError('Delta byte budget must be at least 1024')
    retained = getattr(world.actions, 'iter_since', None)
    if retained is None and world.actions and since_revision < world.actions[0]['sequence'] - 1:
        raise ValueError('World action journal was overrun; faithful event replay is unavailable')
    actions = []
    used_bytes = 256  # Envelope and final sequence; leave room for JSON separators.
    sequence = world.revision
    records = retained(since_revision) if retained else world.actions
    if retained is None and records and since_revision >= records[len(records) // 2]['sequence']:
        # A caught-up consumer needs only the recent suffix. Walk it backwards
        # to avoid scanning the retained history, then restore receipt order.
        # Keep the forward path for a backlog so bounded batches stay cheap.
        pending = []
        for record in reversed(records):
            if record['sequence'] <= since_revision:
                break
            pending.append(record)
        records = reversed(pending)
    for record in records:
        if record['sequence'] <= since_revision:
            continue
        if max_actions is not None and len(actions) >= max_actions:
            sequence = actions[-1]['sequence']
            break
        kind = record['kind']
        action = {'sequence': record['sequence'], 'kind': kind, 'id': instance_id(record['key'])}
        if kind == 'create':
            action['node'] = _node_snapshot(world, record['key'], record['instance'],
                                            creation=record['creation'], versions=record['property_revisions'])
        elif kind == 'set':
            if {'Source','Bytecode','ScriptBytecode'} & record['fields'].keys():
                action['script_code_changed'] = True
            types = _class_property_types(world, record['class'])
            action['fields'] = {name: ({'$ref': instance_id(value)} if value else None)
                                if name == 'Parent' else _received_value(world, value, types.get(name))
                                for name, value in record['fields'].items()
                                if name not in ('Source', 'Bytecode', 'ScriptBytecode')}
            if 'AttributesReplicate' in record['fields']:
                action['attribute_snapshot'] = attribute_snapshot(record['fields'])
            if 'Tags' in record['fields']:
                action['tag_snapshot'] = tag_snapshot(record['fields'],world.shared)
        elif kind == 'attribute':
            action['attribute_update'] = record['attribute_update']
        elif kind == 'event':
            descriptor = world.schema['events'][record['event']]
            action['name'] = descriptor['name']
            action['arguments'] = [_encode(value, parameter['type'])
                                   for value, parameter in zip(record['arguments'], descriptor['arguments'])]
            if (descriptor['name'] == 'OnClientEvent' and len(descriptor['arguments']) == 1
                    and descriptor['arguments'][0]['type'] == 29):
                # Native OnClientEvent exposes a Tuple as separate Luau arguments.
                # Keep the VM update protocol flat, including leading/trailing nil.
                if len(action['arguments']) != 1 or not isinstance(action['arguments'][0], list):
                    raise ValueError('Invalid OnClientEvent tuple')
                action['arguments'] = action['arguments'][0]
        size = len(json.dumps(action, ensure_ascii=True, allow_nan=False).encode()) + 2 if max_bytes is not None else 0
        if max_bytes is not None and used_bytes + size > max_bytes:
            if not actions:
                raise ValueError('One world action exceeds the delta byte budget')
            sequence = actions[-1]['sequence']
            break
        actions.append(action)
        used_bytes += size
    return {'version': 1, 'delta': True, 'sequence': sequence, 'actions': actions}


def replay_world(report_path, user_id):
    """Load a local capture without invoking a server or running received code."""
    report = json.loads(Path(report_path).read_text())
    capture = (ROOT/report['private_capture']).resolve()
    if not capture.is_relative_to((ROOT/'secrets').resolve()):
        raise ValueError('Capture must remain inside secrets')
    world = None
    for row in json.loads(capture.read_text()):
        if row.get('direction') != 'received' or row.get('application') != 4 or row.get('channel') != 1:
            continue
        payload = base64.b64decode(row['data_base64'], validate=True)
        if payload[:1] == b'\x97': world = World(parse_schema(payload))
        elif payload[:1] == b'\x81':
            if world is None: raise ValueError('Globals before schema')
            world.globals(payload)
        elif payload[:1] == b'\x83':
            if world is None: raise ValueError('World packet before schema')
            world.packet(payload)
    if world is None or not world.avatar(user_id)['evidence']['player_spawned']:
        raise ValueError('Capture lacks the selected player character')
    return world
