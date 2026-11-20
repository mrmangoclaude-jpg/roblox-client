"""Advance own-character gravity from received state, separate from replication."""
from physics_ground import _is_part_descendant, _property_type_map, extract_ground
from collision_groups import context_from_world
from no_collision_constraints import _constructor_fields as no_collision_defaults
from physics_script_bridge import PhysicsScriptBridge
from physics_gravity import ReceivedGravity
from physics_job_statistics import PhysicsJobStatistics
from physics_job_scheduler import PhysicsJobScheduler
from simulation_step_clock import SimulationStepClock
from physics_character_states import extract_environment
from physics_platforms import platform_poses_from_world
from world_snapshot import _node_snapshot, instance_id
from world_replication import _copy  # native deep copy of plain data, falls back to copy.deepcopy
from types import SimpleNamespace
from mesh_asset_decoder import MeshAssetQueue, visual_meshes_from_world
from collections import OrderedDict
import weakref

_ENVIRONMENT_CLASSES = frozenset((
    'TrussPart', 'Seat', 'VehicleSeat', 'Terrain', 'Weld', 'WeldConstraint',
    'ManualWeld', 'Motor6D', 'Snap',
))

# Snapshot calls run on the packet cadence. Keep a small number of live worlds
# and their current character-subtree indexes; never retain a closed World.
_SNAPSHOT_DESCENDANT_CACHE = OrderedDict()
_SNAPSHOT_DESCENDANT_CACHE_MAX_WORLDS = 4
_SNAPSHOT_NODE_CACHE = OrderedDict()
_SNAPSHOT_NODE_CACHE_MAX_WORLDS = 4
_SNAPSHOT_NODE_CACHE_MAX_NODES = 65536


class _FrozenDict(dict):
    def _immutable(self, *args, **kwargs):
        raise TypeError('read-only snapshot node')
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _immutable


class _FrozenList(list):
    def _immutable(self, *args, **kwargs):
        raise TypeError('read-only snapshot node')
    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = _immutable
    __iadd__ = __imul__ = _immutable


def _freeze_snapshot_value(value):
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze_snapshot_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze_snapshot_value(item) for item in value)
    return value


def own_character_snapshot(world, user_id, *, read_only=False):
    """Export only the own Player/Character subtree needed by the controller.

    No script catalog or full-world JSON is built on a network tick. Returned
    Node projections are detached and mutable by default. Internal read-only
    consumers may opt into immutable cached nodes to avoid copying.
    """
    avatar = world.avatar(user_id)
    player = avatar.get('player_key')
    character = avatar.get('character_key')
    keys = {key for key in (player, character) if key is not None}
    if character is not None:
        keys.update(_cached_descendant_keys(world, character))
    return {'local_player': instance_id(player),
            'initial_replication_complete': 13 in world.tags,
            'nodes': _cached_node_snapshots(world, keys, read_only=read_only)}


def own_character_monitor_snapshot(world, user_id, *, avatar=None):
    """Return only the Player, Character, direct Humanoid and root for monitoring."""
    avatar = world.avatar(user_id) if avatar is None else avatar
    player = avatar.get('player_key')
    character = avatar.get('character_key')
    keys = {key for key in (player, character) if key is not None}
    if character is not None:
        for key in _cached_descendant_keys(world, character):
            instance = world.instances.get(key)
            if not isinstance(instance, dict) or instance.get('parent') != character:
                continue
            class_index = instance.get('class')
            classes = world.schema.get('classes', ())
            if type(class_index) is not int or not 0 <= class_index < len(classes):
                continue
            class_name = classes[class_index].get('name')
            properties = instance.get('properties', {})
            raw_name = properties.get('Name', class_name)
            name = raw_name.decode('utf-8', 'replace') if isinstance(raw_name, bytes) else str(raw_name)
            if class_name == 'Humanoid' or (name == 'HumanoidRootPart'
                    and class_name in ('Part', 'MeshPart')):
                keys.add(key)
    return {'local_player': instance_id(player),
            'initial_replication_complete': 13 in world.tags,
            'nodes': _cached_node_snapshots(world, keys, read_only=True)}


def _schema_snapshot_fingerprint(schema):
    """Detect schema replacement/table replacement/size changes in O(1).

    World schemas are fixed after parse; a changed schema arrives with a new
    World. Length checks also catch structural append/remove operations.
    """
    classes = schema.get('classes', ())
    properties = schema.get('properties', ())
    return (id(schema), id(classes), len(classes), id(properties), len(properties))


def _cached_node_snapshots(world, keys, *, read_only=False):
    """Encode changed nodes once and return detached mutable projections."""
    world_id = id(world)
    entry = _SNAPSHOT_NODE_CACHE.get(world_id)
    if entry is None or entry['world_ref']() is not world:
        try:
            def discard_dead_world(ref, key=world_id):
                current = _SNAPSHOT_NODE_CACHE.get(key)
                if current is not None and current['world_ref'] is ref:
                    _SNAPSHOT_NODE_CACHE.pop(key, None)
            world_ref = weakref.ref(world, discard_dead_world)
        except TypeError:
            return [_node_snapshot(world, key, world.instances[key])
                    for key in keys if key in world.instances]
        entry = {'world_ref': world_ref, 'instances': world.instances,
                 'schema_fingerprint': _schema_snapshot_fingerprint(world.schema),
                 'cursor': None, 'nodes': OrderedDict(), 'frozen_nodes': {}}
        _SNAPSHOT_NODE_CACHE[world_id] = entry
    _SNAPSHOT_NODE_CACHE.move_to_end(world_id)
    while len(_SNAPSHOT_NODE_CACHE) > _SNAPSHOT_NODE_CACHE_MAX_WORLDS:
        _SNAPSHOT_NODE_CACHE.popitem(last=False)

    schema_fingerprint = _schema_snapshot_fingerprint(world.schema)
    if (entry['instances'] is not world.instances
            or entry['schema_fingerprint'] != schema_fingerprint):
        entry['nodes'].clear()
        entry['frozen_nodes'].clear()
        entry['instances'] = world.instances
        entry['schema_fingerprint'] = schema_fingerprint
        entry['cursor'] = None

    actions = getattr(world, 'actions', None)
    revision = getattr(world, 'revision', None)
    cursor = entry['cursor']
    invalid_keys = set()
    journal_valid = cursor is not None and isinstance(revision, int)
    if journal_valid and cursor != revision:
        if (not actions or actions[0].get('sequence', 0) > cursor + 1
                or actions[-1].get('sequence') != revision):
            journal_valid = False
        else:
            pending = []
            for action in reversed(actions):
                if action.get('sequence', 0) <= cursor:
                    break
                pending.append(action)
            pending.reverse()
            if (not pending or pending[0].get('sequence') != cursor + 1
                    or pending[-1].get('sequence') != revision):
                journal_valid = False
            else:
                for action in pending:
                    if action.get('kind') in ('create', 'set', 'remove'):
                        invalid_keys.add(action.get('key'))
    elif cursor is None:
        journal_valid = False

    if not journal_valid:
        entry['nodes'].clear()
    else:
        for key in invalid_keys:
            entry['nodes'].pop(key, None)
            entry['frozen_nodes'].pop(key, None)

    result = []
    for key in keys:
        instance = world.instances.get(key)
        if instance is None:
            continue
        snapshot = entry['nodes'].get(key)
        if snapshot is None:
            snapshot = _node_snapshot(world, key, instance)
            entry['nodes'][key] = snapshot
        entry['nodes'].move_to_end(key)
        if read_only:
            frozen = entry['frozen_nodes'].get(key)
            if frozen is None:
                frozen = _freeze_snapshot_value(snapshot)
                entry['frozen_nodes'][key] = frozen
            result.append(frozen)
        else:
            result.append(_copy(snapshot))
    while len(entry['nodes']) > _SNAPSHOT_NODE_CACHE_MAX_NODES:
        removed, _ = entry['nodes'].popitem(last=False)
        entry['frozen_nodes'].pop(removed, None)
    entry['cursor'] = revision
    return result


def _snapshot_for_keys(world, player, character, children, *, allow_network_constructor_defaults=False, read_only=False):
    """Build the local controller view from an already-maintained key set."""
    keys = {key for key in (player, character) if key is not None}
    keys.update(children)
    nodes = _cached_node_snapshots(world, keys, read_only=(read_only and not allow_network_constructor_defaults))
    if allow_network_constructor_defaults:
        ncc_defaults = None
        for node in nodes:
            if node.get('constructor_defaults_known') is not True:
                continue
            class_name = node.get('class_name')
            props = node.get('properties')
            if (class_name in ('Part', 'MeshPart', 'Seat', 'VehicleSeat', 'SpawnLocation')
                    and (props is None or 'Anchored' not in props)):
                node.setdefault('properties', {})['Anchored'] = False
                node.setdefault('origins', {})['Anchored'] = 'class_default'
            elif class_name == 'NoCollisionConstraint':
                if ncc_defaults is None:
                    ncc_defaults = no_collision_defaults()
                node_props = node.setdefault('properties', {})
                node_origins = node.setdefault('origins', {})
                for field, value in ncc_defaults.items():
                    if field not in node_props:
                        node_props[field] = value
                        node_origins[field] = 'class_default'
    return {'local_player': instance_id(player),
            'initial_replication_complete': 13 in world.tags,
            'nodes': nodes}


def _children_map(world):
    children = {}
    for key, node in world.instances.items():
        if isinstance(node, dict):
            parent = node.get('parent')
            if parent is not None:
                bucket = children.get(parent)
                if bucket is None:
                    children[parent] = [key]
                else:
                    bucket.append(key)
    return children


def _descendants_from_children(children, ancestor):
    if ancestor is None:
        return set()
    descendants = set()
    stack = list(children.get(ancestor, ()))
    while stack:
        key = stack.pop()
        if key not in descendants and key != ancestor:
            descendants.add(key)
            sub = children.get(key)
            if sub:
                stack.extend(sub)
    return descendants


def _descendant_keys(world, ancestor):
    """Return cached-world descendants without exporting unrelated nodes."""
    if ancestor is None:
        return set()
    return _descendants_from_children(_children_map(world), ancestor)


def _cached_descendant_keys(world, ancestor):
    """Use structural world receipts to avoid rescanning all instances per packet.

    Parent changes and creates invalidate the affected index, since their old
    topology cannot always be recovered from the current instance table. Tree
    removals are applied incrementally. Journal gaps always trigger a rebuild.
    """
    world_id = id(world)
    entry = _SNAPSHOT_DESCENDANT_CACHE.get(world_id)
    if entry is None or entry[0]() is not world:
        try:
            def discard_dead_world(ref, key=world_id):
                current = _SNAPSHOT_DESCENDANT_CACHE.get(key)
                if current is not None and current[0] is ref:
                    _SNAPSHOT_DESCENDANT_CACHE.pop(key, None)
            world_ref = weakref.ref(world, discard_dead_world)
        except TypeError:
            return _descendant_keys(world, ancestor)
        entry = (world_ref, {})
        _SNAPSHOT_DESCENDANT_CACHE[world_id] = entry
    _SNAPSHOT_DESCENDANT_CACHE.move_to_end(world_id)
    while len(_SNAPSHOT_DESCENDANT_CACHE) > _SNAPSHOT_DESCENDANT_CACHE_MAX_WORLDS:
        _SNAPSHOT_DESCENDANT_CACHE.popitem(last=False)

    indexes = entry[1]
    index = indexes.get(ancestor)
    revision = getattr(world, 'revision', None)
    actions = getattr(world, 'actions', None)
    if index is not None and revision == index[0] and index[1] is world.instances:
        return index[2]

    rebuild = (index is None or index[1] is not world.instances
               or not isinstance(revision, int) or not actions)
    pending = []
    if not rebuild:
        cursor = index[0]
        if actions[0].get('sequence', 0) > cursor + 1 or actions[-1].get('sequence') != revision:
            rebuild = True
        else:
            for action in reversed(actions):
                if action.get('sequence', 0) <= cursor:
                    break
                pending.append(action)
            pending.reverse()
            if not pending or pending[0].get('sequence') != cursor + 1 or pending[-1].get('sequence') != revision:
                rebuild = True

    if rebuild:
        descendants = _descendant_keys(world, ancestor)
    else:
        descendants = set(index[2])
        for action in pending:
            kind = action.get('kind')
            if kind == 'remove':
                descendants.discard(action.get('key'))
            elif kind == 'create':
                # New topology can include previously unresolved descendants;
                # rebuild once here to preserve exact subtree membership.
                rebuild = True
                break
            elif kind == 'set' and 'Parent' in action.get('fields', {}):
                rebuild = True
                break
        if rebuild:
            descendants = _descendant_keys(world, ancestor)

    # Keep only a few ancestor entries per world (character replacement is
    # common); copying prevents callers from mutating the cached index.
    indexes[ancestor] = (revision, world.instances, descendants)
    while len(indexes) > 4:
        indexes.pop(next(iter(indexes)))
    return descendants


def _received_surface_velocities(world, geometry):
    """Read typed received velocity only for colliders used as support surfaces."""
    schema = getattr(world, 'schema', {})
    instances = getattr(world, 'instances', {})
    versions = getattr(world, 'property_versions', {})
    colliders = {getattr(box, 'source', None) for box in getattr(geometry, 'colliders', ())}
    result = {}
    for key in colliders:
        node = instances.get(key)
        if not isinstance(node, dict):
            continue
        class_index = node.get('class')
        if type(class_index) is not int or not 0 <= class_index < len(schema.get('classes', [])):
            continue
        property_types = _property_type_map(schema, class_index)
        properties = node.get('properties', {})
        revision_map = versions.get(key, {}) if isinstance(versions, dict) else {}
        # A missing/default CanCollide value is not evidence that a surface
        # should impart motion. Require its typed explicit receipt.
        if (property_types.get('CanCollide', (None, None))[0] != 9
                or properties.get('CanCollide') is not True
                or 'CanCollide' not in revision_map):
            continue
        candidates = []
        for name in ('AssemblyLinearVelocity', 'Velocity'):
            metadata = property_types.get(name)
            value = properties.get(name)
            if (metadata is None or metadata[0] not in (19, 22, 36)
                    or name not in revision_map):
                continue
            if isinstance(value, dict) and '$vector3' in value:
                value = value['$vector3']
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                continue
            try:
                vector = tuple(float(component) for component in value)
            except (TypeError, ValueError):
                continue
            import math
            if not all(math.isfinite(component) for component in vector):
                continue
            candidates.append((revision_map.get(name, 0), name == 'AssemblyLinearVelocity', vector))
        if candidates:
            result[key] = max(candidates, key=lambda item: (item[0], item[1]))[2]
    return result


def _mesh_content_references(world, geometry_keys):
    """Return only typed MeshContent references from cached MeshPart candidates."""
    schema = getattr(world, 'schema', {})
    instances = getattr(world, 'instances', {})
    references = []
    for key in geometry_keys:
        node = instances.get(key)
        if not isinstance(node, dict):
            continue
        class_index = node.get('class')
        if (type(class_index) is not int or not 0 <= class_index < len(schema.get('classes', []))
                or schema['classes'][class_index].get('name') != 'MeshPart'):
            continue
        if _property_type_map(schema, class_index).get('MeshContent', (None, None))[0] != 61:
            continue
        reference = node.get('properties', {}).get('MeshContent')
        if isinstance(reference, (bytes, str)):
            references.append(reference)
    return references


class RuntimePhysicsPrediction:
    """Controller adapter; neither sends packets nor changes received poses."""

    def __init__(self, *, allow_network_constructor_defaults=False,
                 allow_visual_mesh_approximation=False, mesh_asset_queue=None):
        if type(allow_network_constructor_defaults) is not bool:
            raise ValueError('network constructor default inference must be a boolean')
        if type(allow_visual_mesh_approximation) is not bool:
            raise ValueError('visual mesh approximation opt-in must be a boolean')
        if mesh_asset_queue is not None and not allow_visual_mesh_approximation:
            raise ValueError('mesh asset queue requires visual mesh approximation opt-in')
        self.allow_network_constructor_defaults = allow_network_constructor_defaults
        self.allow_visual_mesh_approximation = allow_visual_mesh_approximation
        self._mesh_asset_queue = (mesh_asset_queue if mesh_asset_queue is not None else
                                  MeshAssetQueue() if allow_visual_mesh_approximation else None)
        self._mesh_assets = {}
        self._mesh_asset_signature = ()
        self.bridge = PhysicsScriptBridge()
        self._world = None
        self._revision = None
        self._last_step = None
        self._geometry_revision = None
        self._geometry_at = None
        self._geometry = None
        self._player_key = None
        self._character_key = None
        self._character_children = set()
        self._environment_keys = set()
        self._geometry_keys = set()
        self._no_collision_keys = set()
        self._class_by_key = {}
        self._geometry_dirty = False
        self._env_dirty = False
        self._collision_dirty = True
        self._platform_poses = {}
        self._platform_pose_at = None
        self._workspace_key = None
        self._workspace_keys = None
        self._physics_service_keys = ()
        self._gravity = ReceivedGravity()
        self._job_statistics = PhysicsJobStatistics()
        self._job_scheduler = PhysicsJobScheduler()
        self._simulation_step_clock = SimulationStepClock(units_per_second=240)
        self._clock_world = None

    @property
    def simulation_step(self):
        """Current completed local simulation clock, without advancing it."""
        return self._simulation_step_clock.step

    def prepare(self, world, user_id, now):
        """Warm initial caches; retain a controller that is already advancing."""
        if self._last_step is not None and self.bridge.controller is not None:
            return self.report()
        result = self.advance(world, user_id, now)
        self._last_step = None
        return result

    def advance(self, world, user_id, now, intents=(), *, mutations=(), observed_revision=None):
        if world is not self._world:
            if self._world is not None and self._mesh_asset_queue is not None:
                self._mesh_asset_queue.reset()
            self._mesh_assets = {}
            self._mesh_asset_signature = ()
            self.bridge.clear()
            self._world = world
            self._revision = None
            self._geometry_revision = None
            self._geometry_at = None
            self._geometry = None
            self._player_key = None
            self._character_key = None
            self._character_children = set()
            self._environment_keys = set()
            self._geometry_keys = set()
            self._no_collision_keys = set()
            self._class_by_key = {}
            self._geometry_dirty = False
            self._env_dirty = False
            self._collision_dirty = True
            self._platform_poses = {}
            self._platform_pose_at = None
            self._last_step = None
            self._workspace_key = None
            self._workspace_keys = None
            self._physics_service_keys = ()
            self._gravity = ReceivedGravity()
            self._job_statistics = PhysicsJobStatistics()
            self._job_scheduler = PhysicsJobScheduler()
            if world is not self._clock_world:
                self._simulation_step_clock = SimulationStepClock(units_per_second=240)
                self._clock_world = world
        if world is None:
            self.clear()
            return self.report()
        own_dirty, full_refresh, geometry_dirty = self._changes_since(world)
        if full_refresh:
            self._refresh_keys(world, user_id)
            self._collision_dirty = True
            own_dirty = True
            geometry_dirty = True
            self._env_dirty = True
        if own_dirty:
            self._env_dirty = True
        if geometry_dirty:
            self._geometry_dirty = True
        if self._mesh_asset_queue is not None:
            if own_dirty or geometry_dirty:
                self._mesh_asset_queue.submit(_mesh_content_references(world, self._geometry_keys))
            completed = self._mesh_asset_queue.drain()
            signature = tuple(sorted((key, asset.sha256)
                                     for key, asset in completed.items()))
            if signature != self._mesh_asset_signature:
                self._mesh_assets = completed
                self._mesh_asset_signature = signature
                self._geometry_dirty = True
        if own_dirty:
            snapshot = _snapshot_for_keys(
                world, self._player_key, self._character_key,
                self._character_children | self._no_collision_keys,
                allow_network_constructor_defaults=self.allow_network_constructor_defaults)
            self.bridge.update(snapshot)
        if self._env_dirty and self.bridge.controller is not None:
            environment_snapshot = _snapshot_for_keys(
                world, self._player_key, self._character_key,
                self._character_children | self._environment_keys,
                read_only=True)
            decoded_terrain = getattr(world, 'decoded_terrain_materials', None)
            if isinstance(decoded_terrain, dict):
                environment_snapshot['decoded_terrain_materials'] = decoded_terrain
            try:
                environment = extract_environment(environment_snapshot)
                self.bridge.controller.update_environment(**{
                    name: environment.get(name, ()) for name in
                    ('water_regions', 'ladder_regions', 'seat')}, timestamp=now)
            except (AttributeError, TypeError, ValueError):
                # Old injected test controllers may not implement environment
                # hooks. The built-in controller always does.
                pass
            self._env_dirty = False
        self._revision = world.revision
        controller = self.bridge.controller
        if (controller is not None and self._geometry_dirty
                and (self._geometry_at is None or now-self._geometry_at >= .25)):
            geometry_world = SimpleNamespace(
                schema=world.schema,
                instances={key: world.instances[key] for key in self._geometry_keys
                           if key in world.instances
                           and key not in self._character_children
                           and key != self._character_key},
                creation=getattr(world, 'creation', {}),
                property_versions=getattr(world, 'property_versions', {}))
            visual_meshes = (visual_meshes_from_world(geometry_world, self._mesh_assets)
                             if self.allow_visual_mesh_approximation else None)
            self._geometry = (extract_ground(geometry_world, allow_network_constructor_defaults=True,
                                              visual_meshes=visual_meshes,
                                              allow_visual_mesh_approximation=self.allow_visual_mesh_approximation,
                                              include_unanchored=True)
                              if self.allow_network_constructor_defaults else
                              extract_ground(geometry_world, visual_meshes=visual_meshes,
                                             allow_visual_mesh_approximation=self.allow_visual_mesh_approximation,
                                             include_unanchored=True))
            self._geometry_revision = world.revision
            self._collision_dirty = True
            self._geometry_at = now
            self._geometry_dirty = False
            previous_poses = self._platform_poses
            current_poses = platform_poses_from_world(geometry_world)
            interval = (max(0., now-self._platform_pose_at)
                        if self._platform_pose_at is not None else 0.)
            self._platform_poses = current_poses
            self._platform_pose_at = now
            controller.update_platform_poses(previous_poses or current_poses,
                                             current_poses, interval)
            controller.update_surface_velocities(
                _received_surface_velocities(world, self._geometry))
        if controller is not None and self._geometry is not None:
            if self._collision_dirty:
                update_context=getattr(controller,'update_collision_context',None)
                if callable(update_context):
                    root_key=next((key for key in self._character_children
                                   if instance_id(key)==controller.root_id),None)
                    if len(self._physics_service_keys) == 1:
                        ps_node = world.instances.get(self._physics_service_keys[0])
                        ps_props = ps_node.get('properties', {}) if isinstance(ps_node, dict) else {}
                    else:
                        ps_props = {}
                    update_context(context_from_world(
                        world, self._geometry, self._character_key, root_key,
                        constraint_keys=self._no_collision_keys,
                        physics_service_properties=ps_props,
                        allow_network_constructor_defaults=self.allow_network_constructor_defaults))
                self._collision_dirty=False
            controller.update_geometry(self._geometry)
        admitted = self._job_scheduler.admit(now)
        self._gravity.apply(world.instances.get(self._workspace_key), controller, observe=admitted)
        if admitted:
            dt = min(.25, max(0., now-self._last_step)) if self._last_step is not None else 0.
            # An admitted job samples the current intention. Updates between
            # jobs are retained for the next scheduled simulation step.
            self.bridge.step(dt, timestamp=now)
            self._simulation_step_clock.advance(dt)
            self._job_statistics.completed()
            self._last_step = now
        # Native cursors preserve script order between topology/property
        # writes and movement, after the elapsed simulation step above.
        def refresh_authored_environment():
            # Local Sit writes may activate or release an already received
            # SeatPart link. Refresh that evidence from the detached overlay.
            if self.bridge.controller is not None:
                try:
                    effective = self.bridge._effective_snapshot()
                    by_id = {node.get('id'): node for node in effective['nodes']}
                    environment_snapshot = _snapshot_for_keys(
                        world, self._player_key, self._character_key,
                        self._character_children | self._environment_keys)
                    decoded_terrain = getattr(world, 'decoded_terrain_materials', None)
                    if isinstance(decoded_terrain, dict):
                        environment_snapshot['decoded_terrain_materials'] = decoded_terrain
                    for node in environment_snapshot['nodes']:
                        authored = by_id.get(node.get('id'))
                        if authored:
                            node['properties'] = authored.get('properties', {})
                            node['origins'] = authored.get('origins', node.get('origins', {}))
                    environment = extract_environment(environment_snapshot)
                    self.bridge.controller.update_environment(**{
                        name: environment.get(name, ()) for name in
                        ('water_regions', 'ladder_regions', 'seat')}, timestamp=now)
                except (AttributeError, TypeError, ValueError):
                    pass
        if mutations or intents:
            self.bridge.consume_batch(mutations,list(intents),observed_revision=observed_revision,
                                      after_mutations=refresh_authored_environment)
        return self.report()

    def _refresh_keys(self, world, user_id):
        """Rescan only for startup, relevant identity changes, or journal loss."""
        avatar = world.avatar(user_id)
        self._player_key = avatar.get('player_key')
        self._character_key = avatar.get('character_key')
        class_names = [cls['name'] for cls in world.schema['classes']]
        class_count = len(class_names)
        class_by_key = {}
        children = {}
        workspaces = []
        physics_services = []
        no_collision_keys = set()
        for key, node in world.instances.items():
            if not isinstance(node, dict):
                continue
            parent = node.get('parent')
            if parent is not None:
                bucket = children.get(parent)
                if bucket is None:
                    children[parent] = [key]
                else:
                    bucket.append(key)
            class_index = node.get('class')
            if type(class_index) is int and 0 <= class_index < class_count:
                name = class_names[class_index]
                class_by_key[key] = name
                if name == 'Workspace':
                    workspaces.append(key)
                elif name == 'NoCollisionConstraint':
                    no_collision_keys.add(key)
                elif name == 'PhysicsService':
                    physics_services.append(key)
        self._class_by_key = class_by_key
        self._no_collision_keys = no_collision_keys
        self._physics_service_keys = tuple(physics_services)
        self._workspace_key = workspaces[0] if len(workspaces) == 1 else None

        self._character_children = (
            _descendants_from_children(children, self._character_key)
            if self._character_key is not None else set()
        )
        if self._workspace_key is not None:
            workspace_keys = _descendants_from_children(children, self._workspace_key)
            workspace_keys.add(self._workspace_key)
            self._workspace_keys = workspace_keys
            phys_items = ((key, class_by_key[key]) for key in workspace_keys if key in class_by_key)
        else:
            self._workspace_keys = None
            phys_items = class_by_key.items()

        environment_keys = set()
        geometry_keys = set()
        for key, name in phys_items:
            if name in _ENVIRONMENT_CLASSES:
                environment_keys.add(key)
            if name in ('Terrain', 'MeshPart') or _is_part_descendant(name):
                geometry_keys.add(key)
        self._environment_keys = environment_keys
        self._geometry_keys = geometry_keys

    def _changes_since(self, world):
        """Apply the bounded replication journal and classify what needs refresh.

        Returns (own_subtree_dirty, full_identity_rescan, world_geometry_dirty).
        An overrun or an uninitialized cache falls back to one complete scan.
        """
        cursor = self._revision
        if cursor is None:
            return False, True, False
        if cursor == world.revision:
            return False, False, False
        actions = getattr(world, 'actions', None)
        if not actions:
            return False, True, False
        if actions[0].get('sequence', 0) > cursor + 1:
            return False, True, False
        if actions[-1].get('sequence') != world.revision:
            return False, True, False
        pending_reversed = []
        for action in reversed(actions):
            sequence = action.get('sequence', 0)
            if sequence <= cursor:
                break
            pending_reversed.append(action)
        if (not pending_reversed
                or pending_reversed[-1].get('sequence') != cursor + 1):
            return False, True, False
        pending = reversed(pending_reversed)

        own_dirty = False
        full_refresh = False
        geometry_dirty = False
        classes = world.schema['classes']
        workspace = self._workspace_keys
        # Keep this aligned with extract_ground's inputs. ReplicationPV can be
        # the freshest pose in place of CFrame, and shape aliases decide
        # whether a Part is a supported Block collider.
        always_geometry_fields = {
            'Anchored', 'CanCollide', 'Parent', 'Shape', 'shape', 'NetworkShape',
            'PartType', 'PrimitiveType', 'MeshContent', 'PhysicsData',
            'SolidMeshHolder', 'AeroMeshData', 'PhysicalConfigData',
            'MeshSize', 'InitialSize', 'CollisionFidelity',
            'CollisionPrecision', 'Materials', 'SmoothVoxelsUpgraded',
            'MaterialColors', 'WaterColor',
        }
        pose_size_fields = {'CFrame', 'ReplicationPV', 'Size', 'size'}
        velocity_fields = {'AssemblyLinearVelocity', 'Velocity'}
        geometry_payload_fields = {'CollisionGeometry', 'MeshId', 'MeshContent',
                                   'CollisionFidelity', 'Material', 'PhysicsData',
                                   'SolidMeshHolder', 'PhysicalConfigData', 'AeroMeshData',
                                   'VoxelData', 'TerrainMaterial', 'TerrainMaterials'}
        environment_fields = {'Parent', 'Part0', 'Part1', 'Enabled', 'Occupant',
                              'CFrame', 'Position', 'Size', 'VoxelData',
                              'TerrainMaterial', 'TerrainMaterials',
                              'SmoothVoxelsUpgraded', 'Materials', 'MaterialColors', 'WaterColor'}
        global_collision_fields = {'CollisionGroupData', 'CollisionGroups',
                                   'UseWorkspaceCollisionGroups'}
        part_collision_fields = {'CollisionGroupData', 'CollisionGroups', 'CollisionGroup',
                                 'CollisionGroupReplicate', 'UseWorkspaceCollisionGroups',
                                 'CanCollide', 'Parent'}

        for action in pending:
            key = action.get('key')
            kind = action.get('kind')
            class_name = self._class_by_key.get(key)
            if kind == 'create':
                node = action.get('instance', {})
                class_id = node.get('class')
                if isinstance(class_id, int) and 0 <= class_id < len(classes):
                    class_name = classes[class_id]['name']
                    self._class_by_key[key] = class_name
                if class_name == 'NoCollisionConstraint':
                    self._no_collision_keys.add(key); own_dirty = True; self._collision_dirty = True
                parent = node.get('parent')
                if workspace is None:
                    in_ws = True
                elif parent in workspace:
                    workspace.add(key)
                    in_ws = True
                elif parent is not None and parent not in self._class_by_key:
                    full_refresh = True
                    in_ws = True
                else:
                    in_ws = False
                if in_ws:
                    self._collision_dirty = True
                    if class_name in _ENVIRONMENT_CLASSES:
                        self._environment_keys.add(key)
                        self._env_dirty = True
                        geometry_dirty = True
                    if class_name in ('Terrain', 'MeshPart') or _is_part_descendant(class_name):
                        self._geometry_keys.add(key)
                        geometry_dirty = True
                if (self._player_key is None and class_name == 'Player'):
                    full_refresh = True
                if class_name in ('Workspace', 'PhysicsService'):
                    full_refresh = True
                if (self._character_key is not None and
                        (parent == self._character_key or parent in self._character_children)):
                    self._character_children.add(key)
                    own_dirty = True
            elif kind == 'remove':
                if key in self._no_collision_keys:
                    self._no_collision_keys.discard(key); own_dirty = True; self._collision_dirty = True
                if key in self._physics_service_keys:
                    full_refresh = True
                if key in (self._player_key, self._character_key, self._workspace_key):
                    full_refresh = True
                if key in self._character_children:
                    self._character_children.discard(key)
                    own_dirty = True
                    full_refresh = True
                self._class_by_key.pop(key, None)
                in_ws = workspace is None or key in workspace
                if workspace is not None:
                    workspace.discard(key)
                if in_ws:
                    self._collision_dirty = True
                    if key in self._geometry_keys:
                        self._geometry_keys.discard(key)
                        geometry_dirty = True
                    elif class_name == 'Terrain' or class_name == 'MeshPart' or _is_part_descendant(class_name):
                        geometry_dirty = True
                    if key in self._environment_keys:
                        self._environment_keys.discard(key)
                        self._env_dirty = True
                        geometry_dirty = True
                else:
                    self._geometry_keys.discard(key)
                    self._environment_keys.discard(key)
            elif kind == 'set':
                fields = action.get('fields', {})
                changed_fields = fields.keys()
                in_ws = workspace is None or key in workspace
                if 'Parent' in fields and workspace is not None:
                    new_parent = fields['Parent']
                    was_ws = key in workspace
                    now_ws = new_parent in workspace
                    if was_ws != now_ws or (new_parent is not None and new_parent not in self._class_by_key):
                        full_refresh = True
                        in_ws = True
                if (in_ws and (part_collision_fields & changed_fields)) or (global_collision_fields & changed_fields):
                    self._collision_dirty = True
                if class_name == 'NoCollisionConstraint' and {'Enabled', 'Part0', 'Part1', 'Parent'} & changed_fields:
                    own_dirty = True; self._collision_dirty = True
                if key == self._player_key:
                    if {'Character', 'UserId'} & changed_fields:
                        full_refresh = True
                elif key == self._character_key:
                    if 'Parent' in fields:
                        full_refresh = True
                    elif fields:
                        own_dirty = True
                elif key in self._character_children:
                    if 'Parent' in fields:
                        if fields['Parent'] == self._character_key:
                            self._character_children.add(key)
                            full_refresh = True
                        elif fields['Parent'] in self._character_children:
                            self._character_children.add(key)
                            full_refresh = True
                        else:
                            self._character_children.discard(key)
                            full_refresh = True
                    own_dirty = True
                elif ('Parent' in fields and self._character_key is not None
                      and (fields['Parent'] == self._character_key
                           or fields['Parent'] in self._character_children)):
                    self._character_children.add(key)
                    own_dirty = True
                    full_refresh = True
                elif self._player_key is None and class_name == 'Player' and 'UserId' in fields:
                    full_refresh = True
                if in_ws:
                    if class_name in _ENVIRONMENT_CLASSES and (environment_fields & changed_fields):
                        self._env_dirty = True
                        geometry_dirty = True
                    if (class_name == 'Terrain' or class_name == 'MeshPart'
                            or _is_part_descendant(class_name)):
                        if always_geometry_fields & changed_fields:
                            geometry_dirty = True
                        elif geometry_payload_fields & changed_fields:
                            geometry_dirty = True
                        elif velocity_fields & changed_fields:
                            instance = world.instances.get(key)
                            properties = instance.get('properties', {}) if isinstance(instance, dict) else {}
                            if properties.get('CanCollide') is True:
                                geometry_dirty = True
                        elif pose_size_fields & changed_fields:
                            instance = world.instances.get(key)
                            properties = instance.get('properties', {}) if isinstance(instance, dict) else {}
                            # extract_ground creates colliders only from explicitly
                            # anchored parts. Unanchored body-part motion cannot
                            # change the cached floor map.
                            if (properties.get('Anchored') is True
                                    or (properties.get('Anchored') is False
                                        and properties.get('CanCollide') is True)):
                                geometry_dirty = True

        if full_refresh:
            return own_dirty, True, geometry_dirty
        return own_dirty, False, geometry_dirty

    def clear_binding(self):
        """Drop avatar state without resetting the current world's step clock.

        Only completed intervals contribute. Rebinding does not simulate the
        missing-avatar gap, and changing worlds still creates a fresh clock.
        """
        clock, world = self._simulation_step_clock, self._clock_world
        self.clear()
        self._simulation_step_clock, self._clock_world = clock, world

    def clear(self):
        if self._mesh_asset_queue is not None:
            self._mesh_asset_queue.reset()
        self._mesh_assets = {}
        self._mesh_asset_signature = ()
        self.bridge.clear()
        self._world = None
        self._revision = None
        self._last_step = None
        self._geometry = None
        self._geometry_revision = None
        self._geometry_at = None
        self._player_key = None
        self._character_key = None
        self._character_children = set()
        self._environment_keys = set()
        self._geometry_keys = set()
        self._no_collision_keys = set()
        self._class_by_key = {}
        self._geometry_dirty = False
        self._env_dirty = False
        self._collision_dirty = True
        self._platform_poses = {}
        self._platform_pose_at = None
        self._workspace_key = None
        self._workspace_keys = None
        self._physics_service_keys = ()
        self._gravity = ReceivedGravity()
        self._job_statistics = PhysicsJobStatistics()
        self._job_scheduler = PhysicsJobScheduler()
        self._simulation_step_clock = SimulationStepClock(units_per_second=240)
        self._clock_world = None

    def close(self):
        if self._mesh_asset_queue is not None:
            self._mesh_asset_queue.close()
        self.clear()

    def report(self):
        result = self.bridge.report()
        controller = result.get('controller') or {}
        state = controller.get('predicted_state') or {}
        mesh_status = {'enabled': self.allow_visual_mesh_approximation,
                       'submitted_reference_count': 0, 'pending_count': 0,
                       'decoded_asset_count': 0, 'error_count': 0, 'error_codes': []}
        if self._mesh_asset_queue is not None:
            errors = self._mesh_asset_queue.errors()
            mesh_status.update({
                'submitted_reference_count': len(self._mesh_asset_queue.submitted),
                'pending_count': len(self._mesh_asset_queue.pending),
                'decoded_asset_count': len(self._mesh_asset_queue.cache),
                'error_count': len(errors),
                'error_codes': sorted(set(errors.values())),
            })
        return {**result,
                'gravity': self._gravity.report(),
                'job_statistics': self._job_statistics.report(),
                'job_scheduler': self._job_scheduler.report(),
                'simulation_step_clock': self._simulation_step_clock.report(),
                'accepted_intents': result['accepted_intents'],
                'predicted_position': state.get('position'),
                'simulated_seconds': controller.get('simulated_seconds', 0.),
                'last_reason': controller.get('last_reason'),
                'ground_collider_count': len(self._geometry.colliders) if self._geometry else 0,
                'geometry_assumptions': sorted({item for box in self._geometry.colliders
                                                for item in box.assumptions}) if self._geometry else [],
                'unsupported_geometry_count': len(self._geometry.unsupported) if self._geometry else 0,
                'visual_mesh_approximation': mesh_status}
