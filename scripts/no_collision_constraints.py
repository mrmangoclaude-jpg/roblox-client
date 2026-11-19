"""Detached NoCollisionConstraint registration for the character body proxy."""
from functools import lru_cache
import json
from pathlib import Path


def identifier(key):
    if key is None:return None
    if isinstance(key,tuple) and len(key)==2:return f'{key[0]}:{key[1]}'
    return str(key)


@lru_cache(maxsize=1)
def _parents():
    return json.loads((Path(__file__).resolve().parents[1]/'runtime/class-parents-745.json').read_text())['parents']


def is_part(kind):
    seen=set()
    while isinstance(kind,str) and kind not in seen:
        if kind=='BasePart':return True
        seen.add(kind);kind=_parents().get(kind)
    return False


@lru_cache(maxsize=1)
def _constructor_fields():
    path=Path(__file__).resolve().parents[1]/'runtime/class-constructors-745.json'
    fields=json.loads(path.read_text())['classes']['NoCollisionConstraint']['properties']
    return {name:fields[name]['value'] for name in ('Enabled','Part0','Part1')}


def constructor_defaults(creation, *, allow_network_constructor_defaults=False):
    """Omitted fields retain their constructor values on complete new instances."""
    required = ('fresh', 'complete') if allow_network_constructor_defaults else ('fresh', 'complete', 'ordinary')
    if all(creation.get(flag) for flag in required):
        return _constructor_fields()
    return {}


def topology_records(nodes):
    """Copy only registration fields, excluding pose and other changing values."""
    result=[]
    for node in nodes:
        record={key:node.get(key) for key in ('id','class_name','parent')}
        if node.get('destroyed'):record['destroyed']=True
        if record['class_name']=='NoCollisionConstraint':
            props=node.get('properties',{})
            record['properties']={key:props[key] for key in ('Enabled','Part0','Part1') if key in props}
        result.append(record)
    return tuple(result)


def capture_nodes(world, sources, root_key, *, constraint_keys=None, allow_network_constructor_defaults=False):
    """Capture constraints, endpoints, and ancestor chains without world mutation."""
    instances=world.instances;classes=world.schema['classes']
    def kind(key):return classes[instances[key]['class']]['name']
    if constraint_keys is None:
        constraint_cids = {i for i, cls in enumerate(classes) if cls['name'] == 'NoCollisionConstraint'}
        if not constraint_cids:
            constraints = set()
        else:
            constraints = {key for key, node in instances.items()
                           if isinstance(node, dict) and node.get('class') in constraint_cids}
    else:
        constraints = {key for key in constraint_keys if key in instances}
    wanted=set(sources)|constraints
    if root_key is not None:wanted.add(root_key)
    for key in constraints:
        props=instances[key].get('properties',{})
        for endpoint in ('Part0','Part1'):
            target=props.get(endpoint)
            if isinstance(target,tuple):wanted.add(target)
    # Include parent containers once, even with many shared ancestor chains.
    pending=list(wanted);seen=set()
    while pending:
        key=pending.pop()
        if key in seen or key not in instances:continue
        seen.add(key)
        parent=instances[key].get('parent')
        if parent is not None:pending.append(parent)
    result=[]
    for key in seen:
        node=instances[key];record={'id':identifier(key),'class_name':kind(key),
                                   'parent':identifier(node.get('parent'))}
        if key in constraints:
            props={**constructor_defaults(world.creation.get(key,{}),
                                          allow_network_constructor_defaults=allow_network_constructor_defaults),
                   **node.get('properties',{})};fields={}
            for field in ('Enabled','Part0','Part1'):
                if field not in props:continue
                value=props[field]
                if field!='Enabled' and isinstance(value,tuple):value={'$ref':identifier(value)}
                fields[field]=value
            record['properties']=fields
        result.append(record)
    return tuple(result)


def excluded_parts(root_id, base_nodes, overlay_nodes=(), removed=()):
    """Return only the parts explicitly paired with this root in its WorldRoot."""
    nodes={node['id']:node for node in base_nodes}
    nodes.update((node['id'],node) for node in overlay_nodes)
    for key in removed:nodes.pop(key,None)
    cache={}
    def container(key):
        path=[];seen=set()
        while key is not None and key not in cache:
            if key in seen:raise ValueError('NoCollisionConstraint ancestry contains a cycle')
            seen.add(key);path.append(key)
            node=nodes.get(key)
            if node is None or node.get('destroyed'):key=None;break
            if node.get('class_name') in ('Workspace','WorldModel'):break
            key=node.get('parent')
        root=cache.get(key,key)
        for item in path:cache[item]=root
        return root
    root=container(root_id)
    if root is None:return frozenset()
    result=set()
    for node in nodes.values():
        if node.get('class_name')!='NoCollisionConstraint' or node.get('destroyed'):continue
        props=node.get('properties',{})
        if props.get('Enabled') is False:continue
        def ref(key):
            value=props.get(key)
            return value.get('$ref') if isinstance(value,dict) else None
        a,b=ref('Part0'),ref('Part1')
        if root_id not in (a,b) or container(node['id'])!=root:continue
        if props.get('Enabled') is not True:raise ValueError('NoCollisionConstraint.Enabled is unavailable')
        for key in ('Part0','Part1'):
            if key not in props:raise ValueError('NoCollisionConstraint endpoint is unavailable')
            value=props[key]
            if value is not None and (not isinstance(value,dict) or not isinstance(value.get('$ref'),str)):
                raise ValueError('invalid NoCollisionConstraint endpoint')
        if a is None or b is None or a==b:continue
        if a not in nodes or b not in nodes:raise ValueError('NoCollisionConstraint endpoint is unresolved')
        if nodes[a].get('destroyed') or nodes[b].get('destroyed'):continue
        if not is_part(nodes[a].get('class_name')) or not is_part(nodes[b].get('class_name')):
            raise ValueError('NoCollisionConstraint endpoint must be a BasePart')
        if container(a)==root and container(b)==root:result.add(b if a==root_id else a)
    return frozenset(result)
