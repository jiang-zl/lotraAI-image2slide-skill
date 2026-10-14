"""Original-only feature ledger, independent of the constructed object list."""
import copy
from .common import identity, read_json, safe_path, write_json, digest


def required(state):
    return state.get('objectives', {}).get('source_feature_ledger', False)


def bind(task, state, value):
    if value.get('source_hash') != state['source']['sha256']:
        raise ValueError('Feature inventory must bind the unchanged original')
    rows = value.get('features', [])
    if not rows or len(rows) > 4096 or len({r.get('id') for r in rows}) != len(rows):
        raise ValueError('Use a bounded nonempty original inventory with unique feature IDs')
    from .agent_runtime import _roi
    owners = {c['id'] for c in state['analysis']['components']}
    prior = state.get('source_features')
    if prior:
        original = read_json(safe_path(task, prior['path']))
        if identity(original)==identity(value):raise ValueError('Unchanged source inventory is not progress; resolve a specific debt or retain uncertainty')
        if not {r['id'] for r in original['features']} <= {r['id'] for r in rows}:
            raise ValueError('Unexplained original features cannot disappear on inventory revision')
        if any({k:r.get(k) for k in ('roi','kind','evidence','importance')} !=
               {k:next(v for v in rows if v['id']==r['id']).get(k) for k in ('roi','kind','evidence','importance')}
               for r in original['features']):
            correction=value.get('original_correction',{})
            if not correction.get('reason'): raise ValueError('Source feature corrections need preserved original evidence')
            from .semantic_composition import _original_view
            _original_view(task,state,correction['source_view'])
    for row in rows:
        _roi(row.get('roi'), state['source_size'])
        if (not row.get('id') or not row.get('evidence') or row.get('kind') not in
                ('text','formula','icon','shape','line','relation','texture','uncertain')
                or row.get('status') not in ('observed','inferred','uncertain','excluded')):
            raise ValueError('Record located source features and actual uncertainty, not candidate objects')
        if row.get('owner') and row['owner'] not in owners:
            raise ValueError('Unknown feature owner; keep the feature unassigned until the source plan is extended')
        if row['status']=='inferred' and (not row.get('constraints') or row['kind'] in ('text','formula','relation')):
            raise ValueError('Bound inferred illustration parts; never invent scientific text/math/relations')
        if row['status']=='excluded' and (row.get('importance')=='critical' or not row.get('exclusion_reason')):
            raise ValueError('Critical source content cannot be excluded; explain non-figure context')
        importance=row.get('importance','major')
        if importance not in ('critical','major','minor','polish'):
            raise ValueError('Use an explicit source feature importance')
        if row['status'] in ('observed','inferred') and importance in ('critical','major') and not row.get('quality_property'):
            raise ValueError('Important original features need their own named source-quality property')
        if row.get('owner') and row.get('source_part') and row['status'] in ('observed','inferred'):
            comp=next(c for c in state['analysis']['components'] if c['id']==row['owner'])
            parts={p if isinstance(p,str) else p['id'] for p in comp['parts']}
            if row['source_part'] not in parts:
                comp['parts'].append(row['source_part'])
                quality=state.get('quality')
                if quality and comp['id'] not in quality.get('source_queue',[]):quality['source_queue'].append(comp['id'])
        if state.get('selected') and not row.get('owner') and row['status'] in ('observed','inferred'):
            iid='source-feature-'+identity(row['id'])[:14]
            if not any(i['id']==iid for i in state['issues']):
                state['issues'].append({'id':iid,'owner':None,'source_feature':row['id'],'roi':row['roi'],
                    'property':'original_feature_coverage','expected':row['evidence'],
                    'actual':'Original feature has no independent semantic source-plan owner',
                    'severity':'critical' if row.get('importance')=='critical' else 'major',
                    'status':'open','attempt_count':0,'evidence':{'source':state['source']['sha256']}})
    file = task/'source/features'/('inventory-'+identity(value)+'.json'); write_json(file,value)
    previous = state.get('source_features')
    state.setdefault('source_feature_history', []).append({'previous': previous, 'current':identity(value),
        'event':'original_inventory_bound', 'drawing_gain':False})
    state['source_features'] = {'path':file.relative_to(task).as_posix(),'sha256':digest(file)}


def pending(task, state):
    if not required(state): return []
    ref = state.get('source_features')
    if not ref: return [{'id':'original_inventory','roi':[0,0,*state['source_size']], 'status':'missing_inventory'}]
    path=safe_path(task,ref['path'])
    if digest(path)!=ref['sha256']: raise ValueError('Immutable original feature ledger changed')
    debt=[]; quality=state.get('quality',{})
    for feature in read_json(path)['features']:
        if feature['status']=='excluded': continue
        owner=feature.get('owner'); part=feature.get('source_part')
        spec=quality.get('specifications',{}).get(owner,{})
        bindings=[b for b in spec.get('coverage_bindings',[]) if b['source_part']==part and b.get('status')!='unresolved']
        units={uid for b in bindings for uid in b.get('quality_units',[])}
        available=[quality.get('units',{}).get(uid) for uid in units]
        expected=feature['kind']
        x,y,w,h=feature['roi']
        important=feature.get('importance','major') in ('critical','major')
        property_id=feature.get('quality_property')
        typed=any(u and u['owner']==owner and u['roi'][0]<=x+w/2<=u['roi'][0]+u['roi'][2]
                  and u['roi'][1]<=y+h/2<=u['roi'][1]+u['roi'][3]
                  and (u['profile']==expected if expected in ('text','formula','relation') else
                       u['profile'] not in ('text','formula','relation'))
                  and (not important or property_id in {f['id'] for f in u['features']})
                  and (not important or expected in ('text','formula','relation') or
                       u['roi'][2]*u['roi'][3]<=4*w*h) for u in available)
        if feature['status']=='uncertain' or not owner or not part or not typed:
            debt.append(copy.deepcopy(feature))
    return debt


def packet(task,state):
    debt=pending(task,state)
    return {'inventory':state.get('source_features'), 'features':debt[:8], 'remaining':max(0,len(debt)-8),
            'return':'source_inventory{source_hash,features[{id,roi,kind,status,evidence,owner,source_part,importance,quality_property,constraints?,exclusion_reason?}]} or immutable source_inventory_ref{path,sha256}. Preserve previous features; resolve uncertainty from raw original views. Important features need a named property; visual measurement area is at most 4x the feature ROI, not a panel mean. Bounded inferred illustration content needs constraints and disclosure; never infer scientific content.'}
