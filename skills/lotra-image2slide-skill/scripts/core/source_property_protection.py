"""Protect actually satisfactory native geometry independently of paint debt.

No inferred satisfaction, extra render or intentional failure experiment.
Only exact source observations and own fixed metric intervals create locks.
"""
import copy
from .common import identity

NATIVE_VISUAL={'shape','path','bezier','connector','group'}

def _spec(unit):
    return identity({k:v for k,v in unit.items() if k not in
        ('status','built_fingerprint','missing_output_bindings')})

def _nodes(state,unit,updates=None):
    built=(updates or {}).get(unit['owner']) or state.get('built',{}).get(unit['owner'],{})
    objects=built.get('objects',[]);mapping={o['id']:o for o in objects}
    own=set(unit.get('objects',[]));queue=list(own)
    if not own or not own<=mapping.keys():return None
    while queue:
        root=queue.pop()
        for o in objects:
            if o.get('parent')==root and o['id'] not in own:
                own.add(o['id']);queue.append(o['id'])
    nodes=[o for o in objects if o['id'] in own]
    if any(o['render_type'] not in NATIVE_VISUAL for o in nodes):return None
    return nodes

def _geometry(nodes):
    result=[]
    for obj in nodes:
        content=copy.deepcopy(obj.get('content',{}))
        if content.get('geometry_ref'):
            content['geometry_ref']={'sha256':content['geometry_ref']['sha256']}
        result.append({'id':obj['id'],'parent':obj.get('parent'),
            'render_type':obj['render_type'],'semantic_type':obj.get('semantic_type'),
            'bbox':obj['bbox'],'content':content})
    return identity(result)

def _source_matched(record,category):
    observations=record.get('observations',[])
    items=[o for o in observations if o.get('property')==category]
    return bool(items) and all(o.get('outcome')=='matched' for o in items)

def _geometry_minima(record):
    from .source_quality import METRIC_DIMENSIONS
    names=METRIC_DIMENSIONS['geometry']|METRIC_DIMENSIONS['presence']
    rules=[r for r in record.get('diagnostic',{}).get('constraints',[]) if r['id'] in names]
    return bool(rules) and all(r['status'] in ('minimum_met','stretch_met') for r in rules)

def capture(state):
    """Reuse actual per-part observations; unobserved units never acquire locks."""
    selected=state.get('selected') or {};candidate=selected.get('pptx',{}).get('sha256')
    quality=state.get('quality',{});ledger=quality.setdefault('satisfactory_native_properties',{})
    units=quality.get('units',{});records=quality.get('observations',{})
    for uid in list(ledger):
        unit=units.get(uid);nodes=_nodes(state,unit) if unit else None
        if not unit or _spec(unit)!=ledger[uid]['source_unit_hash'] or not nodes or _geometry(nodes)!=ledger[uid]['geometry_hash']:
            quality.setdefault('property_protection_history',[]).append({**ledger.pop(uid),'unit':uid,'event':'source_or_actual_native_geometry_changed'})
    for uid,unit in units.items():
        record=records.get(uid)
        if not record or record.get('candidate')!=candidate:continue
        # A newly located own geometry/content issue explicitly releases that
        # unit. Paint-only issues cannot silently release satisfactory pose.
        geometry_category='geometry' if any(o.get('property')=='geometry' for o in record.get('observations',[])) else 'placement'
        matched=_source_matched(record,geometry_category) and _source_matched(record,'content')
        if not matched or not _geometry_minima(record):
            if uid in ledger:
                quality.setdefault('property_protection_history',[]).append({**ledger.pop(uid),'unit':uid,'event':'independent_source_geometry_or_content_reopened'})
            continue
        nodes=_nodes(state,unit)
        if not nodes:continue
        ledger[uid]={'category':'native_geometry_and_semantic_structure',
            'source_unit_hash':_spec(unit),'geometry_hash':_geometry(nodes),
            'candidate':candidate,'source_views':record['views'],
            'native_ids':[o['id'] for o in nodes],
            'basis':'Own fixed geometry/presence minima plus actual matched original content/geometry; material may remain below its own floor',
            'limits':'Native paths/shapes/groups only. Text/math/SVG/image units retain their existing protected writer routes; no new source observation or acceptance inferred.'}
    return len(ledger)

def guard(state,updates):
    """Reject planned geometry/structure changes before native construction."""
    quality=state.get('quality',{});units=quality.get('units',{})
    for uid,entry in quality.get('satisfactory_native_properties',{}).items():
        unit=units.get(uid)
        if not unit or unit['owner'] not in updates:continue
        if _spec(unit)!=entry['source_unit_hash']:
            raise ValueError('Refresh changed source-property evidence before repair: '+uid)
        current=_nodes(state,unit)
        if not current or _geometry(current)!=entry['geometry_hash']:
            raise ValueError('Reconcile the changed actual native baseline before repair: '+uid)
        proposed=_nodes(state,unit,updates)
        if not proposed or _geometry(proposed)!=entry['geometry_hash']:
            raise ValueError('Satisfactory native geometry/structure is protected: '+uid+
                '; keep bbox/contours/parents/order or independently revisit this exact source geometry defect first')
    return {'source_property_locks':len(quality.get('satisfactory_native_properties',{})),
        'scope':'Own actual satisfactory native geometry remains exact during other attribute/part repair'}


def snapshot_satisfaction(state):
    """Keep original critical observations before overlapping ROI invalidation."""
    quality=state.get('quality',{});result={}
    for uid,unit in quality.get('units',{}).items():
        record=quality.get('observations',{}).get(uid)
        if (unit['status']=='minimum_met' and record and record['status']=='minimum_met'
                and unit['profile']!='relation' and not unit.get('missing_output_bindings')
                and all(o.get('outcome')=='matched' for o in record['observations'])
                and all(f.get('category') not in ('relation','relations','relationships') for f in unit['features'])):
            result[uid]={'source_unit_hash':_spec(unit),'record':copy.deepcopy(record)}
    return {'source_hash':state['source']['sha256'],'units':result}


def _owned_scene_signature(scene,unit):
    mapping={o['id']:o for o in scene['objects']};own=set(unit['objects']);queue=list(own)
    if not own or not own<=mapping.keys():return None
    while queue:
        root=queue.pop()
        for obj in scene['objects']:
            if obj.get('parent')==root and obj['id'] not in own:
                own.add(obj['id']);queue.append(obj['id'])
    ancestors=set()
    for name in own:
        cursor=mapping[name].get('parent');seen=set()
        while cursor:
            if cursor in seen or cursor not in mapping:return None
            seen.add(cursor);ancestors.add(cursor);cursor=mapping[cursor].get('parent')
    values=[{k:v for k,v in o.items() if k!='versions'} for o in scene['objects'] if o['id'] in own|ancestors]
    return identity(values)


def _native_owned_signature(archive,nodes,names):
    """Reuse native_commit's real shape map; include referenced media bytes."""
    import hashlib,posixpath
    from lxml import etree as E
    from .native_commit import _sp
    from .mathml import NS
    if not set(names)<=nodes.keys():return None
    relpath='ppt/slides/_rels/slide1.xml.rels'
    relations={}
    if relpath in archive.namelist():
        relations={r.get('Id'):r for r in E.fromstring(archive.read(relpath))}
    pieces=[];resources={}
    for name in sorted(names):
        node=nodes[name];pieces.append(E.tostring(node,method='c14n'))
        parent=node.getparent()
        while parent is not None:
            if E.QName(parent).localname=='grpSp':
                transform=_sp(parent)
                if transform is None:return None
                pieces.append(E.tostring(transform,method='c14n'))
            parent=parent.getparent()
        for child in node.iter():
            for attr,rid in child.attrib.items():
                if not attr.startswith('{'+NS['r']+'}'):continue
                relation=relations.get(rid)
                if relation is None:return None
                target=relation.get('Target');external=relation.get('TargetMode')=='External'
                if not target:return None
                target=target if external else posixpath.normpath(posixpath.join('ppt/slides',target))
                if not external and target not in archive.namelist():return None
                resources[target]=('external' if external else hashlib.sha256(archive.read(target)).hexdigest())
    return identity({'native_subtrees':[hashlib.sha256(p).hexdigest() for p in pieces],'resources':resources})


def preserve_satisfaction(task,state,before,after,snapshot):
    """Prune fresh observation only for an exactly unchanged owned result.

    No metric is re-run and no new host observation is fabricated. Source,
    native subtrees/resources/transforms, scene and actual fixed-domain RGB
    must remain exact. Relationships and any changed/unknown unit stay open.
    """
    import hashlib,numpy as np
    from pathlib import Path
    from zipfile import ZipFile
    from lxml import etree as E
    from .common import read_json,digest,safe_path,write_json
    from .native_commit import _nodes
    from . import source_quality as q
    if snapshot['source_hash']!=state['source']['sha256'] or not snapshot['units']:return []
    for candidate in (before,after):
        for key in ('pptx','preview','render','scene'):
            if digest(safe_path(task,candidate[key]['path']))!=candidate[key]['sha256']:
                raise ValueError('Preservation needs immutable saved drawing and actual rendering')
        receipt=read_json(safe_path(task,candidate['render']['path']))
        if receipt.get('pptx_hash')!=candidate['pptx']['sha256'] or receipt.get('preview_hash')!=candidate['preview']['sha256']:
            raise ValueError('Preservation needs bound actual rendering')
    left=read_json(safe_path(task,before['scene']['path']));right=read_json(safe_path(task,after['scene']['path']))
    if identity(left['canvas'])!=identity(right['canvas']):return []
    kept=[];quality=state['quality']
    with ZipFile(safe_path(task,before['pptx']['path'])) as old,ZipFile(safe_path(task,after['pptx']['path'])) as new:
        oldmap=_nodes(E.fromstring(old.read('ppt/slides/slide1.xml')));newmap=_nodes(E.fromstring(new.read('ppt/slides/slide1.xml')))
        for uid,entry in snapshot['units'].items():
            unit=quality['units'].get(uid)
            if not unit or _spec(unit)!=entry['source_unit_hash']:continue
            if any(i.get('quality_unit')==uid and i['status']=='open' and i.get('evidence',{}).get('candidate')==after['pptx']['sha256'] for i in state['issues']):continue
            scene_a=_owned_scene_signature(left,unit);scene_b=_owned_scene_signature(right,unit)
            if scene_a is None or scene_a!=scene_b:continue
            native_a=_native_owned_signature(old,oldmap,unit['objects']);native_b=_native_owned_signature(new,newmap,unit['objects'])
            if native_a is None or native_a!=native_b:continue
            _,a=q._crop_images(task,state,before,unit['roi']);_,b=q._crop_images(task,state,after,unit['roi'])
            a=np.asarray(a);b=np.asarray(b);domain=q._mask(task,unit.get('evaluation_mask'))
            if domain is None:domain=np.ones(a.shape[:2],bool)
            if domain.shape!=a.shape[:2] or a.shape!=b.shape or not domain.any() or not np.array_equal(a[domain],b[domain]):continue
            proof={'status':'EXACT_OWNED_RESULT_INHERITED_NOT_NEW_OBSERVATION','unit':uid,
                'source_hash':state['source']['sha256'],'source_unit_hash':entry['source_unit_hash'],
                'before':before['pptx'],'after':after['pptx'],'prior_observation_candidate':entry['record']['candidate'],
                'scene_hash':scene_a,'native_subtree_resource_transform_hash':native_a,
                'evaluation_mask':unit.get('evaluation_mask'),'owned_rgb_hash':hashlib.sha256(a[domain].tobytes()).hexdigest(),
                'prior_source_views':entry['record']['views'],
                'limits':'Prior critical source/actual observation and numeric minima are inherited only for exact unchanged owned result. No new scores or visual observations; no source/relationship change or changed native/text/math/media property accepted.'}
            folder=Path(task)/'scratch/source-satisfaction-invariance';folder.mkdir(parents=True,exist_ok=True)
            file=folder/(identity(proof)[:24]+'.json');write_json(file,proof)
            record=copy.deepcopy(entry['record']);record.update(candidate=after['pptx']['sha256'],
                built_fingerprint=unit.get('built_fingerprint'),observation_mode='inherited_exact_owned_result',
                invariance_proof={'path':file.relative_to(task).as_posix(),'sha256':digest(file)},
                inherited_diagnostic_candidate=entry['record'].get('inherited_diagnostic_candidate',entry['record']['candidate']))
            quality['observations'][uid]=record;unit['status']='minimum_met';kept.append(uid)
    return kept


def retained_material_effects(task,state,before,after):
    """Protect the untouched original part of an actually repaired RGB mother.

    This is a local saved-output comparison, not a new satisfaction claim.
    The old mother, original source ownership and native frame are bound;
    changed material pixels outside the named natural excision block adoption.
    """
    import numpy as np
    from .common import read_json,digest,safe_path
    from . import source_quality as q
    left=read_json(safe_path(task,before['scene']['path']));right=read_json(safe_path(task,after['scene']['path']))
    originals={o['id']:o for o in left['objects']};rows=[]
    for node in right['objects']:
        metadata=node.get('content',{}).get('source_natural_excision')
        if not metadata:continue
        old=originals.get(node['id'])
        if old and identity(old)==identity(node):continue
        natural=metadata.get('evidence',{}).get('natural_unit');unit=state.get('quality',{}).get('units',{}).get(natural)
        if (not old or not unit or metadata['evidence'].get('source_hash')!=state['source']['sha256']
                or old['render_type']!='svg' or old['bbox']!=node['bbox'] or old.get('parent')!=node.get('parent')):
            raise ValueError('Retained natural material requires its exact old source/frame/owner')
        mother=node['content'].get('retained_mother')
        if mother!={'path':old['content']['path'],'sha256':old['content']['sha256']}:
            raise ValueError('Retained natural material must name the actual baseline mother')
        if digest(safe_path(task,mother['path']))!=mother['sha256']:
            raise ValueError('Retained baseline mother changed')
        mask=metadata['remaining_original_masks']['complete'];domain=q._mask(task,mask)
        _,first=q._crop_images(task,state,before,node['bbox']);_,second=q._crop_images(task,state,after,node['bbox'])
        aa,bb=np.asarray(first),np.asarray(second)
        if domain.shape!=aa.shape[:2] or aa.shape!=bb.shape or not domain.any():
            raise ValueError('Retained material protection needs a nonempty fixed original domain')
        delta=np.abs(aa.astype(int)-bb.astype(int));changed=np.any(delta>0,axis=2)&domain
        rows.append({'unit':natural,'object':node['id'],'source_hash':state['source']['sha256'],
            'source_roi':node['bbox'],'protected_original_mask':mask,'baseline_mother':mother,
            'before':before['pptx'],'after':after['pptx'],'protected_samples':int(domain.sum()),
            'changed_samples':int(changed.sum()),'maximum_rgb_delta':int(delta[domain].max()),
            'eligible':not bool(changed.any()),'scope':'Only unchanged original material outside the independently declared natural excision; exact actual saved-output RGB required. No new source satisfaction or whole-page review.'})
    return rows
