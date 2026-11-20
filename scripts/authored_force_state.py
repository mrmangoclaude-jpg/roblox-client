"""Detached native-mutation overlay for own-character force prediction.

No writes are made to received nodes or to the network. Authoritative property
revisions supersede older local edits, while unrelated receipts preserve them.
"""
import copy

from world_replication import _copy  # native deep copy of plain data, falls back to copy.deepcopy

_FIELDS = {
    'NoCollisionConstraint': frozenset(('Enabled','Part0','Part1','Parent','Name')),
    'BodyForce': frozenset(('Force','force','Parent','Name')),
    'BodyVelocity': frozenset(('Velocity','velocity','MaxForce','maxForce','P','Parent','Name')),
    'BodyPosition': frozenset(('Position','position','MaxForce','maxForce','P','D','Parent','Name')),
    'LinearVelocity': frozenset(('Parent','Name','Enabled','Attachment0','Attachment1','RelativeTo',
        'VelocityConstraintMode','ForceLimitMode','ForceLimitsEnabled','ReactionForceEnabled',
        'VectorVelocity','LineDirection','LineVelocity','PlaneVelocity','PrimaryTangentAxis',
        'SecondaryTangentAxis','MaxForce','MaxAxesForce','MaxPlanarAxesForce')),
    'VectorForce': frozenset(('Force','Enabled','RelativeTo','Attachment0','Attachment1',
                              'ApplyAtCenterOfMass','Parent','Name')),
    'Attachment': frozenset(('CFrame','Parent','Name')),
    'Folder': frozenset(('Parent','Name')),
    'Model': frozenset(('Parent','Name','Scale')),
    'Animator': frozenset(('Parent','Name')),
    'AnimationController': frozenset(('Parent','Name')),
    'AnimationConstraint': frozenset(('Parent','Name','Enabled','Attachment0','Attachment1')),
}
for _joint in ('Motor6D','Motor','Weld','Snap','ManualWeld','WeldConstraint'):
    _FIELDS[_joint]=frozenset(('Parent','Name','Part0','Part1','Enabled'))
    if _joint != 'WeldConstraint':
        _FIELDS[_joint] |= frozenset(('C0','C1','Transform'))

_MASS_PARTS=frozenset(('Part','MeshPart','UnionOperation','WedgePart','CornerWedgePart',
    'TrussPart','Seat','VehicleSeat','SpawnLocation','PartOperation','Platform','SkateboardPlatform','FlagStand'))
_MASS_FIELDS=frozenset(('Size','Shape','Material','MaterialVariant','CustomPhysicalProperties','Massless','RootPriority','Anchored','CFrame','Position','CollisionGroup','Parent','Name'))
for _part in _MASS_PARTS:
    _FIELDS[_part]=_MASS_FIELDS
_POSE_FIELDS=('CFrame','Position')
_POSE_RECEIPTS=('CFrame','Position','ReplicationPV','Orientation','Rotation')


def _writable_fields(node):
    kind=node.get('class_name')
    return _MASS_FIELDS if kind in _MASS_PARTS else _FIELDS.get(kind,())


class AuthoredForceState:
    def __init__(self):
        self.local_nodes = {}
        self.overrides = {}
        self.removed = set()
        self.stale_writes = 0
        self.applied_writes = 0
        self.target_generations = {}
        self.pose_generations = {}
        self.pose_baselines = {}
        self._write_sequence = 0

    def clear(self):
        self.local_nodes.clear();self.overrides.clear();self.removed.clear();self.target_generations.clear()
        self.pose_generations.clear();self.pose_baselines.clear()

    @staticmethod
    def _nodes(snapshot):
        return {n['id']:n for n in snapshot.get('nodes',[])
                if isinstance(n,dict) and isinstance(n.get('id'),str)}

    @staticmethod
    def _value(node,key):
        if key=='Parent':return node.get('parent')
        if key=='Name':return node.get('name')
        return node.get('properties',{}).get(key)

    @staticmethod
    def _present(node,key):
        if key in ('Parent','Name'):return key.lower() in node
        return key in node.get('properties',{})

    @staticmethod
    def _put(node,key,value):
        if node.get('class_name') in _MASS_PARTS:
            props=node.setdefault('properties',{});origins=node.setdefault('origins',{})
            if key=='CFrame':
                frame=value.get('$cframe') if isinstance(value,dict) else None
                if isinstance(frame,dict) and 'position' in frame:
                    props['Position']={'$vector3':copy.deepcopy(frame['position'])};origins['Position']='local'
                else:props.pop('Position',None);origins.pop('Position',None)
            elif key=='Position':
                frame=props.get('CFrame')
                if isinstance(frame,dict) and isinstance(frame.get('$cframe'),dict):
                    frame['$cframe']['position']=copy.deepcopy(value.get('$vector3') if isinstance(value,dict) else None)
                    origins['CFrame']='local'
        if node.get('class_name') in ('Motor6D','Motor','Weld','Snap','ManualWeld','WeldConstraint') and key in ('Parent','Part0','Part1','Enabled'):
            node.setdefault('properties',{}).pop('Active',None)
            node.setdefault('origins',{}).pop('Active',None)
        if node.get('class_name')=='BodyForce' and key=='force':key='Force'
        if node.get('class_name')=='BodyVelocity':key={'velocity':'Velocity','maxForce':'MaxForce'}.get(key,key)
        if node.get('class_name')=='BodyPosition':key={'position':'Position','maxForce':'MaxForce'}.get(key,key)
        if node.get('class_name')=='Attachment' and key in ('CFrame','Parent'):
            node.setdefault('properties',{}).pop('WorldCFrame',None)
            node.setdefault('origins',{}).pop('WorldCFrame',None)
        if key=='Parent':
            node['parent'] = value.get('$ref') if isinstance(value,dict) else None
        elif key=='Name':node['name']=value
        else:node.setdefault('properties',{})[key]=copy.deepcopy(value)
        node.setdefault('origins',{})[key]='local'

    def _pose_receipt(self,node):
        return {key:{'revision':node.get('property_revisions',{}).get(key),
                     'present':self._present(node,key),'value':copy.deepcopy(self._value(node,key))}
                for key in _POSE_RECEIPTS}

    def invalidate(self,snapshot):
        nodes=self._nodes(snapshot)
        for identifier,baseline in list(self.pose_baselines.items()):
            node=nodes.get(identifier)
            if node is None or self._pose_receipt(node)!=baseline:
                for field in _POSE_FIELDS:self.overrides.pop((identifier,field),None)
                del self.pose_baselines[identifier]
                if node is None:self.pose_generations.pop(identifier,None)
        for key,entry in list(self.overrides.items()):
            node=nodes.get(key[0])
            if (node is None or node.get('property_revisions',{}).get(key[1])!=entry['revision']
                    or self._present(node,key[1])!=entry['present']
                    or self._value(node,key[1])!=entry['received_value']):
                del self.overrides[key]
        # An absent received ID cannot continue hiding a subsequently created
        # instance with that ID. Local destroyed nodes have already been erased.
        self.removed.intersection_update(nodes)

    def apply(self,mutations,snapshot,observed_revision=None):
        received=self._nodes(snapshot);applied=0
        for item in mutations:
            if not isinstance(item,dict):continue
            kind=item.get('kind')
            if kind=='create':
                raw=item.get('node')
                if not isinstance(raw,dict):continue
                identifier=raw.get('id');cls=raw.get('class_name')
                if (not isinstance(identifier,str) or not identifier.startswith('local:')
                        or cls not in _FIELDS or identifier in received or identifier in self.local_nodes):continue
                if len(self.local_nodes)>=1000:raise ValueError('local force node budget exceeded')
                fields=raw.get('properties',{})
                if not isinstance(fields,dict):continue
                node={'id':identifier,'class_name':cls,'name':raw.get('name',cls),
                      'parent':raw.get('parent'),'properties':{},'origins':{'Parent':'local'}}
                for key,value in fields.items():
                    if cls=='BodyForce' and key=='force' and 'Force' in fields:continue
                    if cls=='BodyVelocity' and key in ('velocity','maxForce') and {'velocity':'Velocity','maxForce':'MaxForce'}[key] in fields:continue
                    if cls=='BodyPosition' and key in ('position','maxForce') and {'position':'Position','maxForce':'MaxForce'}[key] in fields:continue
                    if key in _FIELDS[cls]:self._put(node,key,value)
                self.local_nodes[identifier]=node;applied+=1
            elif kind=='set':
                identifier=item.get('id');key=item.get('property')
                if not isinstance(identifier,str) or not isinstance(key,str) or 'value' not in item:continue
                node=self.local_nodes.get(identifier) or received.get(identifier)
                if not node or identifier in self.removed or key not in _writable_fields(node):continue
                if node.get('class_name')=='BodyForce' and key=='force':key='Force'
                if node.get('class_name')=='BodyVelocity':
                    key={'velocity':'Velocity','maxForce':'MaxForce'}.get(key,key)
                if node.get('class_name')=='BodyPosition':
                    key={'position':'Position','maxForce':'MaxForce'}.get(key,key)
                pose_write=node.get('class_name') in _MASS_PARTS and key in _POSE_FIELDS
                if pose_write and observed_revision is not None and any(
                        type(revision) in (int,float) and revision>observed_revision
                        for field,revision in node.get('property_revisions',{}).items() if field in _POSE_RECEIPTS):
                    self.stale_writes+=1;continue
                self._write_sequence+=1
                if identifier in self.local_nodes:self._put(node,key,item['value'])
                else:
                    revision=node.get('property_revisions',{}).get(key)
                    if observed_revision is not None and revision is not None and revision>observed_revision:
                        self.stale_writes+=1;continue
                    self.overrides[identifier,key]={'value':copy.deepcopy(item['value']),
                        'revision':revision,'present':self._present(node,key),
                        'received_value':copy.deepcopy(self._value(node,key)),
                        'write_sequence':self._write_sequence}
                if pose_write:
                    self.pose_generations[identifier]=self.pose_generations.get(identifier,0)+1
                    self.pose_baselines[identifier]=self._pose_receipt(node)
                if node.get('class_name')=='BodyPosition' and key=='Position':
                    self.target_generations[identifier]=self.target_generations.get(identifier,0)+1
                applied+=1
            elif kind=='destroy':
                identifiers=item.get('ids',[])
                if not isinstance(identifiers,list):continue
                for identifier in identifiers:
                    if not isinstance(identifier,str):continue
                    node=self.local_nodes.get(identifier) or received.get(identifier)
                    if not node or node.get('class_name') not in _FIELDS:continue
                    if identifier not in self.local_nodes and observed_revision is not None:
                        revisions=node.get('property_revisions',{}).values()
                        if any(type(v) in (int,float) and v>observed_revision for v in revisions):
                            self.stale_writes+=1;continue
                    self.local_nodes.pop(identifier,None)
                    self.target_generations.pop(identifier,None)
                    if identifier in received:self.removed.add(identifier)
                    for key in [k for k in self.overrides if k[0]==identifier]:del self.overrides[key]
                    applied+=1
        self.applied_writes+=applied
        return applied

    def snapshot(self,received,*,node_ids=None,properties=None):
        if node_ids is None:
            result=_copy(received)
        else:
            # Animation needs only the own rig, not environment mesh payloads,
            # script data, or the controller's full collision projection.
            result={'nodes':[_copy({**n,'properties':{
                k:v for k,v in n.get('properties',{}).items()
                if properties is None or k in properties}})
                for n in received.get('nodes',[]) if n.get('id') in node_ids]}
        nodes=self._nodes(result)
        for (identifier,key),entry in sorted(self.overrides.items(),key=lambda item:item[1].get('write_sequence',0)):
            if identifier in nodes and (properties is None or key in properties or key in ('Parent','Name')):
                self._put(nodes[identifier],key,entry['value'])
        result['nodes']=[n for n in result['nodes'] if n.get('id') not in self.removed]
        result['nodes'].extend(_copy([n for n in self.local_nodes.values()
            if node_ids is None or n['id'] in node_ids]))
        for node in result['nodes']:
            if node.get('class_name') in _MASS_PARTS and any((node['id'],key) in self.overrides for key in _POSE_FIELDS):
                node['authored_pose_generation']=self.pose_generations.get(node['id'],0)
                node['authored_rotation_generation']=self.overrides.get((node['id'],'CFrame'),{}).get('write_sequence')
            if node.get('class_name')=='BodyPosition':
                node['mover_target_generation']=self.target_generations.get(node['id'],0)
        return result

    def animation_snapshot(self,received,character_id):
        from collections import defaultdict
        children=defaultdict(list)
        for node in (*received.get('nodes',()),*self.local_nodes.values()):
            identifier=node['id']
            if identifier in self.removed:continue
            edit=self.overrides.get((identifier,'Parent'))
            parent=(edit['value'].get('$ref') if isinstance(edit['value'],dict) else None) if edit else node.get('parent')
            children[parent].append(identifier)
        selected=set();pending=[character_id]
        while pending:
            identifier=pending.pop()
            if identifier in selected:continue
            selected.add(identifier);pending.extend(children.get(identifier,()))
        return self.snapshot(received,node_ids=selected,properties=frozenset((
            'Scale','Enabled','C0','C1','CFrame','Part0','Part1','Attachment0','Attachment1')))
