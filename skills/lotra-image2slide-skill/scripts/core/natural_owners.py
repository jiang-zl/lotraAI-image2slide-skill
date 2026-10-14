"""Verify declared native anatomy through executable construction owners.

The host classifies source meaning. This bounded vocabulary checks the classes
it declares, including leaves of mixed scenes; it never classifies photographs
or guesses a family from an object name, colour or arbitrary prose.
"""

VEHICLE_SEMANTICS=frozenset(('wireless_vehicle','top_view_vehicle','vehicle_icon',
    'wireless_car','connected_car','car_icon','connected_car_body','car_body',
    'vehicle_body','car_window','vehicle_window','car_mirror'))
GRAPHIC_SEMANTICS=frozenset(('wireless_signal','radio_wave','antenna_wave','signal_band'))
NATURAL_RECIPES=frozenset(('wireless_vehicle','natural_icon'))


def constructed_roots(method,owner,depth=0):
    if depth>8:raise ValueError('Bounded executable natural owner hierarchy required')
    roots={owner} if method.get('recipe') in NATURAL_RECIPES else set()
    for child in method.get('children',[]):
        roots.update(constructed_roots(child['method'],child['id'],depth+1))
    for instance in method.get('recipe_instances',[]):
        roots.update(constructed_roots(instance['method'],instance['id'],depth+1))
    return roots


def validated_alternatives(method,owner,depth=0):
    """The caller has executed each branch's resource/representation validator."""
    if depth>8:raise ValueError('Bounded validated representation hierarchy required')
    roots={owner} if any(method.get(field) for field in ('native_asset','svg_asset','solid_svg','hd_asset')) else set()
    for child in method.get('children',[]):
        roots.update(validated_alternatives(child['method'],child['id'],depth+1))
    return roots


def verify(objects,method,owner):
    """Every recognized vehicle leaf belongs to a real constructed family root.

    Call this on fresh construction and retained-cache paths alike. Raw caller
    metadata is not a construction receipt. Other source-supported families and
    original identity photos retain their separate existing quality contracts.
    """
    allowed=constructed_roots(method,owner);alternatives=validated_alternatives(method,owner)
    nodes={obj['id']:obj for obj in objects};natural={}
    for obj in objects:
        content=obj.get('content',{});marker=content.get('natural_icon')
        if marker is not None:
            if (obj['id'] not in allowed or obj.get('render_type')!='group'
                    or not isinstance(marker,dict) or not marker.get('family')
                    or not isinstance(marker.get('parts'),dict) or not marker['parts']
                    or not isinstance(marker.get('mother'),str) or len(marker['mother'])!=64):
                raise ValueError('Natural owner '+obj['id']+' must be produced by the program recipe, not raw natural metadata; use source-bound natural children or recipe_instances')
            natural[obj['id']]=marker
        if obj.get('semantic_type') in GRAPHIC_SEMANTICS and obj.get('render_type') in ('text','equation'):
            raise ValueError('Declared graphic '+obj['id']+' needs source-supported native/vector geometry; text characters cannot replace its observed signal contour')
    for obj in objects:
        semantic=obj.get('semantic_type');part=obj.get('content',{}).get('natural_part')
        if semantic not in VEHICLE_SEMANTICS and not (isinstance(part,dict) and part.get('role')=='vehicle_body'):
            continue
        current=obj['id'];seen=set();matched=False
        while current in nodes and current not in seen:
            seen.add(current)
            # The executable model retains the source-specific family/view.
            # Catalog compatibility decides whether a top-view default fits;
            # this ownership check must also support explicit side/3D models.
            if current in natural or current in alternatives:matched=True;break
            current=nodes[current].get('parent')
        if not matched:
            raise ValueError('Declared vehicle anatomy '+obj['id']+' requires a source-bound natural owner; create its own child root and use recursive children or recipe_instances with compatible source_traits. Omitting a group cannot bypass observed anatomy.')
    return {'checked_objects':len(objects),'constructed_natural_roots':sorted(natural),
        'validated_component_alternatives':sorted(alternatives),
        'scope':'Declared bounded native semantics and construction ownership; source classification still belongs to the host.'}


def saved_inventory(scene):
    """Recheck actual Scene anatomy before the saved-native inventory gate.

    Native/Scene names and parentage are independently reconciled by the same
    whole-inventory gate. This check preserves approved source imports and
    detects a dropped, duplicated or reparented generated natural part.
    """
    nodes={obj['id']:obj for obj in scene['objects']};items=[]
    for root in scene['objects']:
        marker=root.get('content',{}).get('natural_icon')
        if marker is None:continue
        parts=marker.get('parts') if isinstance(marker,dict) else None
        expected={root['id']+'__'+name:role for name,role in parts.items()} if isinstance(parts,dict) else {}
        actual={obj['id']:obj.get('content',{}).get('natural_part',{}).get('role')
            for obj in scene['objects'] if obj.get('parent')==root['id']}
        valid=bool(expected) and expected==actual and root.get('render_type')=='group'
        items.append({'root':root['id'],'passed':valid,'expected_parts':expected,'actual_parts':actual,
            'family':marker.get('family') if isinstance(marker,dict) else None})
    return {'passed':all(item['passed'] for item in items),'items':items,
        'scope':'Actual native/Scene reconciliation also enforces saved names and semantic parents; this checks every recorded natural anatomy, including retained imports.'}
