"""Mandatory numeric relations inside classified raw physical icon assemblies.

Semantic classification is supplied by the host. Programs discover every
relevant constituent pair, including parts wrongly moved apart; a prose
decision or coordinate-container declaration cannot close their obligations.
"""
from itertools import combinations
from .natural_owners import constructed_roots

PHYSICAL={'physical_assembly','physical_icon','icon_set','camera','camera_icon',
    'camera_illustration','surveillance_camera','sensor_icon','device_icon',
    'phone_icon','mobile_phone','computer_icon','monitor_icon','robot_icon',
    'instrument_icon','vehicle_icon','wireless_vehicle','top_view_vehicle'}
PAINT={'shape','path','bezier','photo','svg'}


def required(state,scene):
    nodes={o['id']:o for o in scene['objects']};children={}
    for obj in nodes.values():children.setdefault(obj.get('parent'),[]).append(obj['id'])
    controlled=set()
    for owner,entry in state.get('built',{}).items():
        controlled.update(constructed_roots(entry.get('method',{}),owner))
    result={}
    for root,obj in nodes.items():
        if obj.get('render_type')!='group' or root in controlled:continue
        direct=[nodes[n] for n in children.get(root,[])]
        physical=(obj.get('semantic_type') in PHYSICAL or any(o.get('semantic_type')=='icon_part' for o in direct))
        if not physical:continue
        leaves=[o['id'] for o in direct if o.get('render_type') in PAINT]
        if len(leaves)>64:raise ValueError('Bound physical assembly parts to at most 64 direct painted roles; refine independently classified subassemblies')
        for pair in combinations(sorted(leaves),2):result[pair]=root
    return result


def proven(pair,decision,rows,scene):
    """Require a matching numerical contract; original claims alone are pending."""
    if decision.get('decision') in ('unresolved','unrelated','hierarchy'):return False
    selected={r['id']:r for r in rows if r.get('id') in decision.get('contracts',[])}
    a,b=pair['objects'];root=pair['physical_root']
    for row in selected.values():
        if row.get('kind')=='interface':
            sets=row.get('part_sets',[])
            if (row.get('root')==root and row.get('original_spacing') and len(sets)==2 and
                    ((a in sets[0] and b in sets[1]) or (b in sets[0] and a in sets[1]))):return True
        if set(row.get('objects',[]))!={a,b} or not row.get('source_evidence'):continue
        if row.get('kind')=='inside' and row.get('source_view'):
            # _validate freezes the <=2px tolerance; the actual capture uses
            # the independent painted container interior, never its bbox.
            return True
        if row.get('kind')=='join' and row.get('mask') and row.get('mask_origin')=='original_observed':return True
    return False
