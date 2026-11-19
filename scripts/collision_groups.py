"""Bounded collision definitions shared by offline character prediction.

Matches the native query adapter's v1 saved-place format and explicit fallback
rules. No definitions or received instances are mutated here.
"""
from dataclasses import dataclass
import re
from no_collision_constraints import capture_nodes, excluded_parts, identifier


def data_bytes(value, limit=4096):
    if isinstance(value, str):
        try: value=value.encode('utf-8')
        except UnicodeError as exc: raise ValueError('invalid collision group UTF-8') from exc
    elif isinstance(value, dict) and set(value)=={'$bytes_hex'}:
        text=value['$bytes_hex']
        if not isinstance(text,str) or len(text)>limit*2 or len(text)%2 or re.fullmatch('[0-9a-fA-F]*',text) is None:
            raise ValueError('invalid collision group hex')
        value=bytes.fromhex(text)
    if not isinstance(value,bytes) or len(value)>limit:
        raise ValueError('invalid or oversized collision group bytes')
    return value


def valid_name(name):
    if not isinstance(name,str): raise ValueError('collision group name must be text')
    try: raw=name.encode('utf-8')
    except UnicodeError as exc: raise ValueError('invalid collision group UTF-8') from exc
    if not 1<=len(raw)<=100 or '\0' in name: raise ValueError('invalid collision group name')
    return name


def part_group(properties):
    if 'CollisionGroup' in properties:
        name=properties['CollisionGroup']
        if isinstance(name,bytes):
            try: name=name.decode('utf-8')
            except UnicodeError as exc: raise ValueError('invalid collision group UTF-8') from exc
        return valid_name(name)
    if 'CollisionGroupReplicate' not in properties: return 'Default'
    raw=data_bytes(properties['CollisionGroupReplicate'],limit=1024*1024)
    if not raw: raise ValueError('CollisionGroupReplicate lacks group ID')
    if len(raw)==1: return 'Default'
    try: return valid_name(raw[1:].decode('utf-8'))
    except UnicodeError as exc: raise ValueError('invalid collision group UTF-8') from exc


@dataclass(frozen=True)
class CollisionTable:
    # ID, name, unsigned mask; tuples keep the decoded table detached.
    groups: tuple = ((0,'Default',0xffffffff),)
    complete: bool = False

    def collidable(self, first, second):
        if not self.complete and (first!='Default' or second!='Default'):
            raise ValueError('collision group matrix is unavailable')
        by_name={name:(id,mask) for id,name,mask in self.groups}
        a=by_name.get(first,by_name['Default']);b=by_name.get(second,by_name['Default'])
        return bool(a[1] & (1<<b[0]) and b[1] & (1<<a[0]))


def validated(rows):
    if not 1<=len(rows)<=32: raise ValueError('invalid collision group count')
    ids=set();names=set()
    for id,name,mask in rows:
        valid_name(name)
        if id not in range(32) or id in ids or name in names:
            raise ValueError('duplicate or out-of-range collision group ID/name')
        if (id==0)!=(name=='Default'): raise ValueError('Default group must have ID zero')
        if not 0<=mask<=0xffffffff: raise ValueError('invalid collision mask')
        ids.add(id);names.add(name)
    if 0 not in ids: raise ValueError('collision groups lack Default')
    return CollisionTable(tuple(sorted(rows)),True)


def decode_binary(value):
    raw=data_bytes(value)
    if not raw: return CollisionTable(complete=True)
    if len(raw)<2 or raw[0]!=1: raise ValueError('invalid CollisionGroupData version/header')
    count=raw[1]
    if not 1<=count<=32: raise ValueError('invalid collision group count')
    cursor=2;rows=[]
    for _ in range(count):
        if len(raw)-cursor<7: raise ValueError('truncated CollisionGroupData')
        id,width=raw[cursor:cursor+2]
        if width!=4: raise ValueError('unsupported collision mask width')
        mask=int.from_bytes(raw[cursor+2:cursor+6],'little');length=raw[cursor+6];cursor+=7
        if len(raw)-cursor<length: raise ValueError('truncated collision group name')
        try: name=raw[cursor:cursor+length].decode('utf-8')
        except UnicodeError as exc: raise ValueError('invalid collision group UTF-8') from exc
        rows.append((id,name,mask));cursor+=length
    if cursor!=len(raw): raise ValueError('trailing CollisionGroupData bytes')
    return validated(rows)


def decode_legacy(value):
    if isinstance(value,bytes):
        try: value=value.decode('utf-8')
        except UnicodeError as exc: raise ValueError('invalid legacy collision groups') from exc
    if not isinstance(value,str) or len(value.encode('utf-8'))>4096:
        raise ValueError('invalid legacy collision groups')
    if not value: return CollisionTable(complete=True)
    rows=[]
    for record in value.split('\\'):
        fields=record.split('^')
        if len(fields)!=3: raise ValueError('invalid legacy collision group record')
        name,id,mask=fields
        if any(len(v)>11 or re.fullmatch('-?[0-9]+',v) is None for v in (id,mask)):
            raise ValueError('invalid legacy collision group integer')
        id,mask=int(id),int(mask)
        if not -(1<<31)<=mask<1<<32: raise ValueError('legacy collision mask out of range')
        rows.append((id,name,mask & 0xffffffff))
    return validated(rows)


def read_table(properties, legacy_service=None):
    if 'CollisionGroupData' in properties: return decode_binary(properties['CollisionGroupData'])
    if 'CollisionGroups' in properties: return decode_legacy(properties['CollisionGroups'])
    if legacy_service is not None and 'CollisionGroups' in legacy_service:
        return decode_legacy(legacy_service['CollisionGroups'])
    return CollisionTable()


@dataclass(frozen=True)
class CollisionContext:
    table: CollisionTable = CollisionTable()
    # Source IDs belonging to the character's physics world and their names.
    groups: tuple = ()
    error: str | None = None
    root_id: str | None = None
    constraint_nodes: tuple = ()

    def allowed_sources(self, character_group, overlay_nodes=(), removed=()):
        if self.error: raise ValueError(self.error)
        excluded=excluded_parts(self.root_id,self.constraint_nodes,overlay_nodes,removed) if self.root_id is not None else ()
        return frozenset(key for key,group in self.groups
                         if identifier(key) not in excluded and self.table.collidable(character_group,group))


def context_from_world(world, geometry, character_key, root_key=None, *,
                       constraint_keys=None, physics_service_properties=None,
                       allow_network_constructor_defaults=False):
    """Capture one character's rules, including nearest-WorldRoot isolation."""
    try:
        instances=world.instances;classes=world.schema['classes']
        def kind(key):
            node=instances.get(key)
            return classes[node['class']]['name'] if node is not None else None
        cache={}
        def root_of(key):
            path=[];seen=set()
            while key is not None and key not in cache:
                if key in seen: raise ValueError('collision hierarchy contains a cycle')
                seen.add(key);path.append(key)
                if kind(key) in ('Workspace','WorldModel'): break
                key=instances.get(key,{}).get('parent')
            root=cache.get(key,key)
            for item in path: cache[item]=root
            return root
        root=root_of(character_key)
        if root is None: raise ValueError('character collision WorldRoot is unavailable')
        table_root=root
        props=instances[root].get('properties',{})
        if kind(root)=='WorldModel' and type(props.get('UseWorkspaceCollisionGroups',False)) is not bool:
            raise ValueError('invalid UseWorkspaceCollisionGroups')
        if kind(root)=='WorldModel' and props.get('UseWorkspaceCollisionGroups') is True:
            ws_cids={i for i, cls in enumerate(classes) if cls['name']=='Workspace'}
            workspaces=[k for k, node in instances.items() if isinstance(node, dict) and node.get('class') in ws_cids]
            if len(workspaces)!=1: raise ValueError('Workspace collision state is unavailable')
            table_root=workspaces[0];props=instances[table_root].get('properties',{})
        legacy=physics_service_properties
        if kind(table_root)=='Workspace' and legacy is None and 'CollisionGroupData' not in props and 'CollisionGroups' not in props:
            ps_cids={i for i, cls in enumerate(classes) if cls['name']=='PhysicsService'}
            if ps_cids:
                services=[node.get('properties',{}) for node in instances.values() if isinstance(node, dict) and node.get('class') in ps_cids]
                if len(services)==1: legacy=services[0]
        table=read_table(props,legacy)
        groups=[]
        for collider in geometry.colliders:
            key=collider.source
            if key not in instances or root_of(key)!=root: continue
            props=instances[key].get('properties',{})
            # A CanCollide update can arrive before the geometry rebuild interval.
            if props.get('CanCollide') is False: continue
            groups.append((key,part_group(props)))
        constraints=(capture_nodes(world,(c.source for c in geometry.colliders),root_key,
                                   constraint_keys=constraint_keys,
                                   allow_network_constructor_defaults=allow_network_constructor_defaults)
                     if root_key is not None else ())
        return CollisionContext(table,tuple(groups),root_id=identifier(root_key),constraint_nodes=constraints)
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        return CollisionContext(error=str(exc))
