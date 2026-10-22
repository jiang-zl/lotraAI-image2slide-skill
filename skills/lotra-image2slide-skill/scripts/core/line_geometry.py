"""Independent saved-line decoding and bounded source geometry predicates.

No writer or native_route_spec is imported. Approximation error is carried into
acceptance bounds; an unresolved bound requests refinement instead of a PASS.
"""
import math
import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from .mathml import NS
from .line_contracts import segment_ends


def result(passed, **values):
    return {'passed':bool(passed), 'valid':True, 'status':'PASS' if passed else 'FAIL', **values}


def invalid(reason, **values):
    return {'passed':False, 'valid':False, 'status':'INVALID', 'reason':str(reason), **values}


def bounded(value, error, tolerance, **values):
    lower, upper = max(0., value-error), value+error
    if upper <= tolerance + 1e-9:
        return result(True, value=value, lower=lower, upper=upper, tolerance=tolerance, **values)
    if lower > tolerance + 1e-9:
        return result(False, value=value, lower=lower, upper=upper, tolerance=tolerance, **values)
    return invalid('BOUND_REFINEMENT_REQUIRED', value=value, lower=lower, upper=upper, tolerance=tolerance, **values)


def _flatten_controls(controls, epsilon, output, depth=0):
    points = np.asarray(controls, float)
    if len(points) == 2:
        output.append(points[-1].tolist()); return
    chord = LineString([points[0], points[-1]]) if np.linalg.norm(points[0]-points[-1]) > 1e-12 else Point(points[0])
    deviation = max(Point(p).distance(chord) for p in points[1:-1])
    if deviation <= epsilon:
        output.append(points[-1].tolist()); return
    if depth >= 24 or len(output) >= 32768:
        raise ValueError('CURVE_PRECISION_REQUIRED: finite subdivision exhausted')
    level = points; left = [level[0]]; right = [level[-1]]
    while len(level) > 1:
        level = (level[:-1]+level[1:])/2
        left.append(level[0]); right.append(level[-1])
    _flatten_controls(left, epsilon, output, depth+1)
    _flatten_controls(list(reversed(right)), epsilon, output, depth+1)


def flatten(segments, epsilon):
    points = []; offsets = []
    for segment in segments:
        first, last = segment_ends(segment)
        if not points: points.append(first)
        offsets.append(len(points)-1)
        if segment['kind'] == 'arc':
            matrix=np.asarray(segment.get('transform',np.eye(3)),float)
            radius = max(segment['radii'])*float(np.linalg.norm(matrix[:2,:2],2)); sweep = abs(math.radians(segment['sweep_degrees']))
            angle = 2*math.acos(max(-1., min(1., 1-epsilon/radius))) if epsilon < 2*radius else math.pi
            count = max(2, math.ceil(sweep/max(angle, 1e-7)))
            if count > 32768: raise ValueError('CURVE_PRECISION_REQUIRED: bounded source arc sampling')
            for a in np.linspace(segment['start_degrees'], segment['start_degrees']+segment['sweep_degrees'], count+1)[1:]:
                a = math.radians(a); c=segment['center']; rx,ry=segment['radii']
                p=matrix@np.array([c[0]+rx*math.cos(a),c[1]+ry*math.sin(a),1.])
                points.append(p[:2].tolist())
        else:
            _flatten_controls(segment['points'], epsilon, points)
    return np.asarray(points, float), offsets


def _world(entry, controls):
    return (np.c_[np.asarray(controls, float), np.ones(len(controls))] @ entry['matrix'].T)[:, :2].tolist()


def _effective_line(entry, parts):
    """Resolve actual explicit/theme line properties; unknown colours stay invalid."""
    props = entry['node'].find('p:spPr', NS)
    explicit = props.find('a:ln', NS)
    reference = entry['node'].find('p:style/a:lnRef', NS)
    layers=[]; theme_colour=None
    if reference is not None:
        if not parts: raise ValueError('STYLE_MEASUREMENT_REQUIRED: theme reference needs package bytes')
        from lxml import etree as E
        import posixpath
        rel_ns={'r':'http://schemas.openxmlformats.org/package/2006/relationships'}
        slide_rels=E.fromstring(parts['ppt/slides/_rels/slide1.xml.rels'])
        def target(rels, suffix, base):
            row=next((r for r in rels if r.get('Type','').endswith('/'+suffix)),None)
            if row is None: raise ValueError('STYLE_MEASUREMENT_REQUIRED: missing '+suffix)
            if row.get('TargetMode')=='External': raise ValueError('External style dependency')
            return posixpath.normpath(posixpath.join(base,row.get('Target')))
        layout=target(slide_rels,'slideLayout','ppt/slides')
        def relationships(name):
            return E.fromstring(parts[posixpath.dirname(name)+'/_rels/'+posixpath.basename(name)+'.rels'])
        master=target(relationships(layout),'slideMaster',posixpath.dirname(layout))
        theme=target(relationships(master),'theme',posixpath.dirname(master)); tree=E.fromstring(parts[theme])
        styles=tree.find('a:themeElements/a:fmtScheme/a:lnStyleLst',NS)
        index=int(reference.get('idx','0'))
        if not 1 <= index <= len(styles): raise ValueError('STYLE_MEASUREMENT_REQUIRED: unresolved theme line index')
        layers.append(styles[index-1])
        colours=tree.find('a:themeElements/a:clrScheme',NS)
        def colour(node):
            if node is None: return None
            rgb=node.find('a:srgbClr',NS)
            if rgb is not None: return rgb.get('val')
            scheme=node.find('a:schemeClr',NS)
            if scheme is not None:
                name=scheme.get('val')
                if name=='phClr': return theme_colour
                element=colours.find('a:'+name,NS)
                if element is None: raise ValueError('STYLE_MEASUREMENT_REQUIRED: unresolved colour map')
                child=next(iter(element),None)
                if child is None:return None
                if len(child):raise ValueError('STYLE_MEASUREMENT_REQUIRED: transformed theme colour')
                return child.get('val') if child.tag.endswith('srgbClr') else child.get('lastClr')
            return None
        theme_colour=colour(reference)
    else:
        def colour(node):
            if node is None:return None
            rgb=node.find('a:srgbClr',NS)
            return rgb.get('val') if rgb is not None else None
    if explicit is not None:layers.append(explicit)
    if not layers:raise ValueError('STYLE_MEASUREMENT_REQUIRED: no resolved native line properties')
    attrs={}; children={}
    for layer in layers:
        attrs.update(layer.attrib)
        for child in layer:
            key=child.tag.rsplit('}',1)[-1]
            for alternatives in (('noFill','solidFill','gradFill','pattFill'),('prstDash','custDash'),('round','bevel','miter')):
                if key in alternatives:
                    for old in alternatives:children.pop(old,None)
            children[key]=child
    if 'noFill' in children: raise ValueError('Actual native line is unpainted')
    if any(k in children for k in ('gradFill','pattFill')):
        raise ValueError('STYLE_MEASUREMENT_REQUIRED: gradient/pattern stroke needs its source appearance profile')
    fill=children.get('solidFill'); rgb=colour(fill)
    if rgb is None:raise ValueError('STYLE_MEASUREMENT_REQUIRED: unresolved line colour')
    alpha=1.
    node=next(iter(fill),None) if fill is not None else None
    if node is not None:
        for transform in node:
            tag=transform.tag.rsplit('}',1)[-1]
            if tag=='alpha':alpha=int(transform.get('val'))/100000
            else:raise ValueError('STYLE_MEASUREMENT_REQUIRED: unsupported native colour transform '+tag)
    dash=children.get('prstDash'); custom=children.get('custDash')
    markers=[]
    for name in ('headEnd','tailEnd'):
        marker=children.get(name)
        markers.append({'type':marker.get('type','none') if marker is not None else 'none',
                        'width':marker.get('w','med') if marker is not None else 'med',
                        'length':marker.get('len','med') if marker is not None else 'med'})
    return {'width_emu':int(attrs.get('w','0')), 'colour':rgb.upper(), 'opacity':alpha,
            'cap':{'flat':'flat','rnd':'round','sq':'square'}.get(attrs.get('cap','flat')),
            'join':next((k for k in ('round','bevel','miter') if k in children),'round'),
            'compound':{'sng':'single','dbl':'double','thickThin':'thickThin','thinThick':'thinThick','tri':'triple'}.get(attrs.get('cmpd','sng')),
            'dash':'custom' if custom is not None else dash.get('val') if dash is not None else 'solid',
            'custom_dash':[[int(ds.get('d')),int(ds.get('sp'))] for ds in custom] if custom is not None else [],
            'markers':markers}


def decode(entry, parts=None, terminal_sites=None):
    if entry.get('error') or entry.get('matrix') is None:raise ValueError(entry.get('error') or 'Missing saved transform')
    from .boundary_geometry import require_projected
    require_projected(entry)
    if entry['tag'] not in ('sp','cxnSp'):raise ValueError('Actual line is not an editable native leaf')
    prop=entry['node'].find('.//p:cNvPr',NS)
    if prop is not None and prop.get('hidden','0') in ('1','true'):raise ValueError('Actual line is hidden')
    props=entry['node'].find('p:spPr',NS); preset=props.find('a:prstGeom',NS)
    effects=props.find('a:effectLst',NS)
    if props.find('a:effectDag',NS) is not None or effects is not None and len(effects):
        raise ValueError('STYLE_MEASUREMENT_REQUIRED: effects need a qualified paint producer')
    closed=False; filled=False; segments=[]
    if preset is not None:
        name=preset.get('prst')
        if name in ('line','straightConnector1','lineInv'):
            uv=[[0,1],[1,0]] if name=='lineInv' else [[0,0],[1,1]]
            segments=[{'kind':'line','points':_world(entry,uv)}]
        elif name in ('bentConnector2','bentConnector3','bentConnector4','bentConnector5'):
            # Independent DrawingML definitions, not construction decisions.
            adj={n:.5 for n in ('adj1','adj2','adj3')}
            for guide in preset.findall('a:avLst/a:gd',NS):
                formula=(guide.get('fmla') or '').split()
                if len(formula)!=2 or formula[0]!='val' or guide.get('name') not in adj:
                    raise ValueError('ROUTE_MEASUREMENT_REQUIRED: unsupported saved guide')
                adj[guide.get('name')]=float(formula[1])/100000
            x,y,z=[adj[n] for n in ('adj1','adj2','adj3')]
            uv={'bentConnector2':[[0,0],[1,0],[1,1]],
                'bentConnector3':[[0,0],[x,0],[x,1],[1,1]],
                'bentConnector4':[[0,0],[x,0],[x,y],[1,y],[1,1]],
                'bentConnector5':[[0,0],[x,0],[x,y],[z,y],[z,1],[1,1]]}[name]
            world=_world(entry,uv)
            segments=[{'kind':'line','points':[a,b]} for a,b in zip(world,world[1:]) if math.dist(a,b)>1e-9]
        elif name in ('rect','ellipse'):
            closed=True
            if name=='rect':
                uv=[[0,0],[1,0],[1,1],[0,1],[0,0]]; world=_world(entry,uv)
                segments=[{'kind':'line','points':[a,b]} for a,b in zip(world,world[1:])]
            else:
                segments=[{'kind':'arc','center':[.5,.5],'radii':[.5,.5],
                           'start_degrees':0,'sweep_degrees':360,'transform':entry['matrix'].tolist()}]
        elif name in ('rightArrow','leftArrow','upArrow','downArrow'):
            if not terminal_sites:raise ValueError('ROUTE_MEASUREMENT_REQUIRED: filled arrow requires explicit qualified terminal sites and contour')
            from .neighbor_geometry import _paths
            contours=_paths(entry,props)
            if len(contours)!=1 or not contours[0][1]:raise ValueError('Unsupported filled arrow contour')
            vertices=np.asarray(contours[0][0],float)
            sites=[]
            for end in ('start','end'):
                site=terminal_sites[end]
                if type(site.get('vertex')) is not int or not 0<=site['vertex']<len(vertices):raise ValueError('Actual filled-arrow terminal vertex required')
                sites.append(vertices[site['vertex']].tolist())
            segments=[{'kind':'line','points':sites}];filled=True
        else:raise ValueError('ROUTE_MEASUREMENT_REQUIRED: unsupported native preset '+str(name))
    else:
        geom=props.find('a:custGeom',NS)
        paths=geom.findall('a:pathLst/a:path',NS) if geom is not None else []
        if len(paths)!=1:raise ValueError('ROUTE_MEASUREMENT_REQUIRED: disjoint subpaths need distinct native parts')
        p=paths[0];w,h=float(p.get('w',0)),float(p.get('h',0))
        if min(w,h)<=0:raise ValueError('Unresolved native path dimensions')
        current=start=None
        for command in p:
            tag=command.tag.rsplit('}',1)[-1]
            pts=[[float(q.get('x'))/w,float(q.get('y'))/h] for q in command.findall('a:pt',NS)]
            if tag=='moveTo' and current is None:current=start=pts[0]
            elif tag in ('lnTo','quadBezTo','cubicBezTo') and current is not None:
                count={'lnTo':1,'quadBezTo':2,'cubicBezTo':3}[tag]
                if len(pts)!=count:raise ValueError('Malformed saved path controls')
                segments.append({'kind':{1:'line',2:'quadratic',3:'cubic'}[count],'points':_world(entry,[current]+pts)})
                current=pts[-1]
            elif tag=='close' and start is not None:
                if math.dist(current,start)>1e-10:segments.append({'kind':'line','points':_world(entry,[current,start])})
                closed=True;current=start
            else:raise ValueError('ROUTE_MEASUREMENT_REQUIRED: unsupported path operation '+tag)
    if not segments:raise ValueError('No measurable saved line segments')
    if closed and terminal_sites:
        # A source-declared filled freeform arrow retains its complete saved
        # outline. Axis terminals must be actual outline vertices or edge sites.
        vertices=np.asarray([segment_ends(s)[0] for s in segments],float)
        if any(s['kind']!='line' for s in segments):raise ValueError('Filled curved outline needs a qualified contour/terminal extractor')
        sites=[]
        for end in ('start','end'):
            site=terminal_sites[end];index=site.get('vertex',site.get('edge'))
            if type(index) is not int or not 0<=index<len(vertices):raise ValueError('Actual filled-arrow terminal site required')
            p=vertices[index]
            if 'edge' in site:
                ratio=site.get('fraction')
                if type(ratio) not in (int,float) or not 0<=ratio<=1:raise ValueError('Actual edge fraction required')
                p=p+(vertices[(index+1)%len(vertices)]-p)*ratio
            sites.append(p.tolist())
        segments=[{'kind':'line','points':sites}];closed=False;filled=True
    if filled:
        colour=props.find('a:solidFill/a:srgbClr',NS)
        if colour is None:raise ValueError('STYLE_MEASUREMENT_REQUIRED: filled arrow needs an explicit measurable body colour')
        if any(v.tag.rsplit('}',1)[-1]!='alpha' for v in colour):raise ValueError('Unsupported filled arrow colour transform')
        alpha=colour.find('a:alpha',NS)
        style={'width_emu':0,'colour':colour.get('val').upper(),'opacity':int(alpha.get('val'))/100000 if alpha is not None else 1.,
               'cap':'flat','join':'round','compound':'single','dash':'solid','custom_dash':[],
               'markers':[{'type':'none','width':'med','length':'med'} for _ in range(2)],'paint_mode':'filled_body'}
    else:style=_effective_line(entry,parts)
    parent=np.asarray(entry.get('parent_matrix',np.eye(3)),float)[:2,:2]
    singular=np.linalg.svd(parent,compute_uv=False)
    style['width_source_bounds']=[float(style['width_emu']*min(singular)),float(style['width_emu']*max(singular))]
    if filled:
        contour=[list(p) for p in vertices]
    else:contour=None
    return {'segments':segments,'style':style,'closed':closed,'filled':filled,'contour':contour,
            'start':segment_ends(segments[0])[0],'end':segment_ends(segments[-1])[-1]}


def _reduced(points):
    result=[]
    for p in points:
        if not result or math.dist(result[-1],p)>1e-8:result.append(list(p))
        while len(result)>=3:
            a,b,c=np.asarray(result[-3:]);u=b-a;v=c-b
            # Only remove redundant forward-collinear vertices. Preserve U-turns.
            if abs(float(u[0]*v[1]-u[1]*v[0]))<=1e-8*max(1.,np.linalg.norm(u)*np.linalg.norm(v)) and float(u@v)>=0:
                result.pop(-2)
            else:break
    return result


def separate_marker_paint_extent(entry, vertices, anchor):
    """Exact polygon paint envelope only for independently qualified saved paint.

    A shaft's ending multiplier cannot bound an unrelated marker owner. Unknown
    inherited/stroked/effect paint keeps the conservative producer instead.
    """
    props=entry['node'].find('p:spPr',NS)
    preset=props.find('a:prstGeom',NS);line=props.find('a:ln',NS)
    if (preset is None or preset.get('prst') not in ('triangle','diamond','rect') or
        preset.find('a:avLst',NS) is not None and len(preset.find('a:avLst',NS))):return None
    if line is None or line.find('a:noFill',NS) is None:return None
    if any(line.find('a:'+name,NS) is not None for name in ('solidFill','gradFill','pattFill')):return None
    if any(n.get('type','none')!='none' for n in line if n.tag.rsplit('}',1)[-1] in ('headEnd','tailEnd')):return None
    effects=props.find('a:effectLst',NS)
    if props.find('a:effectDag',NS) is not None or effects is not None and len(effects):return None
    effect_ref=entry['node'].find('p:style/a:effectRef',NS)
    if effect_ref is not None and effect_ref.get('idx','0')!='0':return None
    paints=[n for n in props if n.tag.rsplit('}',1)[-1] in ('solidFill','gradFill','pattFill','blipFill','noFill','grpFill')]
    if len(paints)!=1 or paints[0].tag.rsplit('}',1)[-1]!='solidFill':return None
    rgb=paints[0].find('a:srgbClr',NS)
    if rgb is None or len(paints[0])!=1 or any(n.tag.rsplit('}',1)[-1]!='alpha' or n.get('val')!='100000' for n in rgb):return None
    colour=rgb.get('val','')
    if len(colour)!=6 or any(c not in '0123456789ABCDEFabcdef' for c in colour):return None
    vertices=np.asarray(vertices,float);anchor=np.asarray(anchor,float)
    if vertices.ndim!=2 or vertices.shape[1]!=2 or not len(vertices) or not np.isfinite(vertices).all() or not np.isfinite(anchor).all():return None
    lo=vertices.min(axis=0);hi=vertices.max(axis=0)
    return {'method':'independent_saved_polygon_marker_paint','bounds':[float(lo[0]),float(lo[1]),float(hi[0]),float(hi[1])],
            'radius_from_source_anchor':float(np.abs(vertices-anchor).max()),'stroke_painted':False,
            'fill':rgb.get('val'),'effects':'none','source_anchor':anchor.tolist()}


def native_checks(row, decoded, nodes, bindings, epsilon):
    source=row['source'];limits=source['limits'];closed=source['path']['kind']=='closed'
    expected, _=flatten(source['path']['segments'],epsilon)
    shafts=[(part['owner'],decoded[part['owner']]) for part in row['parts'] if part['role']=='shaft']
    paths=[];oriented=[];current=expected[0];remaining=list(shafts)
    while remaining:
        distances=[(min(math.dist(q['start'],current),math.dist(q['end'],current)),i) for i,(_,q) in enumerate(remaining)]
        _,i=min(distances);owner,q=remaining.pop(i);points,_=flatten(q['segments'],epsilon)
        reverse=math.dist(points[-1],current)<math.dist(points[0],current)
        if reverse:points=points[::-1]
        oriented.append({'owner':owner,'reverse':reverse,'points':points,'native':q})
        paths.append(LineString(points));current=points[-1]
    actual=unary_union(paths);expected_path=LineString(expected)
    # No output-derived mask or best-fit alignment is permitted.
    hidden=[]
    for item in source['visibility']['hidden']:
        points,_=flatten([source['path']['segments'][item['segment']]],epsilon)
        curve=LineString(points);lo,hi=item['range']
        from shapely.ops import substring
        hidden.append(substring(curve,lo*curve.length,hi*curve.length).buffer(limits['route']))
    domain=unary_union(hidden) if hidden else None
    exp_visible=expected_path.difference(domain) if domain is not None else expected_path
    act_visible=actual.difference(domain) if domain is not None else actual
    if exp_visible.is_empty or act_visible.is_empty:route=invalid('No independently measurable visible route')
    else:route=bounded(float(exp_visible.hausdorff_distance(act_visible)),2*epsilon,limits['route'],method='saved_path_bidirectional_bound',unit='source_px')
    if source['path']['kind']=='filled_arrow':
        if len(shafts)!=1 or not shafts[0][1].get('contour'):
            route['body_outline']=invalid('Filled-arrow body/head needs an actual qualified contour extractor')
        else:
            original_outline=source['path']['outline'];saved_outline=shafts[0][1]['contour']
            a=LineString(original_outline+[original_outline[0]]);b=LineString(saved_outline+[saved_outline[0]])
            route['body_outline']=bounded(float(a.hausdorff_distance(b)),epsilon,limits['route'])
        route['passed']=route['passed'] and route['body_outline']['passed']
        route['valid']=route['valid'] and route['body_outline']['valid']
    # Union distance cannot detect duplicate/retraced strokes or reordered bends.
    length_error=abs(sum(p.difference(domain).length if domain is not None else p.length for p in paths)-exp_visible.length)
    length_bound=limits['route']*max(2,len(source['path']['segments']))
    length_check=bounded(length_error,epsilon*(len(expected)+sum(len(v['points']) for v in oriented)),length_bound,unit='source_px')
    route['length']=length_check;route['passed']=route['passed'] and length_check['passed']
    route['valid']=route['valid'] and length_check['valid']
    if len(oriented)==1 and all(s['kind']=='line' for s in source['path']['segments']) and all(s['kind']=='line' for s in oriented[0]['native']['segments']):
        a=_reduced(expected);b=_reduced(oriented[0]['points'])
        if closed and len(a)==len(b) and len(a)>2:
            aa=a[:-1];bb=b[:-1];variants=[]
            for sequence in (bb,list(reversed(bb))):
                for i in range(len(sequence)):
                    variant=sequence[i:]+sequence[:i]
                    variants.append(variant+[variant[0]])
            b=min(variants,key=lambda v:max(math.dist(x,y) for x,y in zip(a,v)))
        signed={'passed':len(a)==len(b),'source_corners':a,'actual_corners':b}
        if len(a)==len(b):
            errors=[math.dist(x,y) for x,y in zip(a,b)]
            directions=[]
            for p,q,x,y in zip(a,a[1:],b,b[1:]):
                u=np.asarray(q)-p;v=np.asarray(y)-x;den=np.linalg.norm(u)*np.linalg.norm(v)
                directions.append(float(u@v/den) if den>1e-12 else -1.)
            signed.update(corner_error=max(errors,default=0.),signed_direction_cosines=directions)
            signed['passed']=max(errors,default=0.)<=limits['route'] and all(v>=math.cos(math.radians(limits['angle_degrees']))-1e-10 for v in directions)
        route['ordered_corners']=signed;route['passed']=route['passed'] and signed['passed']
    elif len(oriented)==1 and not closed:
        # Corresponding source segment ends must occur in source order.
        curve=paths[0];landmarks=[segment_ends(s)[-1] for s in source['path']['segments'][:-1]]
        if oriented[0]['reverse']:curve=LineString(oriented[0]['points'])
        positions=[curve.project(Point(p)) for p in landmarks]
        route['ordered_landmarks']={'passed':all(b>=a-1e-7 for a,b in zip(positions,positions[1:])),'positions':positions}
        route['passed']=route['passed'] and route['ordered_landmarks']['passed']
    curved=any(s['kind']!='line' for s in source['path']['segments']) or any(
        s['kind']!='line' for part in oriented for s in part['native']['segments'])
    if curved and (not expected_path.is_simple or not LineString(np.concatenate([p['points'] for p in oriented])).is_simple):
        # Equal occupied sets and length do not establish loop traversal order.
        # Keep established failures as leaves; do not downgrade them to a waivable
        # uncertainty while exposing this additional unsupported measurement.
        route['geometric_bound']=dict(route)
        route['traversal_order']=invalid('MEASUREMENT_REQUIRED: self-intersecting curved traversal needs ordered measurement or source-declared simple parts')
        route['passed']=False;route['valid']=False
    terminals=[];markers=[];stroke=[];marker_paint_extents={}
    for i,part in enumerate(oriented):
        for native_index,ending in enumerate(part['native']['style']['markers']):
            index=1-native_index if part['reverse'] else native_index
            outside=not closed and ((i==0 and index==0) or (i==len(oriented)-1 and index==1))
            if not outside:markers.append(result(ending['type']=='none',owner=part['owner'],end=native_index,scope='no hidden intermediate/closed-path terminal marker'))
    if not closed:
        actual_ends=[oriented[0]['points'][0],oriented[-1]['points'][-1]]
        for index,(end,p) in enumerate(zip(source['ends'],actual_ends)):
            check=bounded(math.dist(end['point'],p),epsilon,limits['endpoint'],unit='source_px')
            q=oriented[0 if index==0 else -1];native_index=index if len(oriented)==1 else (0 if index==0 else 1)
            native_index=1-native_index if q['reverse'] else native_index
            def tangent(segments,last):
                segment=segments[-1 if last else 0]
                if segment['kind']=='arc':
                    angle=math.radians(segment['start_degrees']+(segment['sweep_degrees'] if last else 0))
                    v=np.array([-segment['radii'][0]*math.sin(angle),segment['radii'][1]*math.cos(angle)])*math.copysign(1,segment['sweep_degrees'])
                    return np.asarray(segment.get('transform',np.eye(3)))[:2,:2]@v
                values=np.asarray(segment['points'],float)
                pairs=list(zip(values,values[1:]))
                for a,b in reversed(pairs) if last else pairs:
                    if np.linalg.norm(b-a)>1e-10:return b-a
                raise ValueError('Terminal tangent is not independently measurable')
            original_tangent=tangent(source['path']['segments'],index==1)
            saved_tangent=tangent(q['native']['segments'],bool(native_index))*(-1 if q['reverse'] else 1)
            cosine=float(original_tangent@saved_tangent/(np.linalg.norm(original_tangent)*np.linalg.norm(saved_tangent)))
            check['signed_tangent']={'passed':cosine>=math.cos(math.radians(limits['angle_degrees']))-1e-10,'cosine':cosine,'angle_limit_degrees':limits['angle_degrees']}
            check['passed']=check['passed'] and check['signed_tangent']['passed']
            marker=q['native']['style']['markers'][native_index]
            custom=[part for part in row['parts'] if part['role']==('start_marker' if index==0 else 'end_marker')]
            if custom:
                if len(custom)!=1:raise ValueError('One located marker owner per terminal required')
                else:
                    entry=nodes[custom[0]['owner']];props=entry['node'].find('p:spPr',NS);preset=props.find('a:prstGeom',NS)
                    from .boundary_geometry import require_projected
                    require_projected(entry)
                    prop=entry['node'].find('.//p:cNvPr',NS)
                    if prop is not None and prop.get('hidden','0') in ('1','true'):raise ValueError('Separate native marker is hidden')
                    native_type={'ellipse':'oval','triangle':'triangle','diamond':'diamond','line':'bar'}.get(preset.get('prst') if preset is not None else None,'custom')
                    filled=props.find('a:solidFill',NS) is not None
                    marker_check=result(marker['type']=='none' and native_type==end['marker']['type'] and filled==end['marker']['filled'],expected=end['marker']['type'],actual=native_type,method='separate_native_marker')
                    from .neighbor_geometry import _paths
                    outlines=_paths(entry,props)
                    vertices=np.asarray([p for path,_,_ in outlines for p in path],float)
                    if not len(vertices):raise ValueError('Empty separate native marker geometry')
                    axis=original_tangent/np.linalg.norm(original_tangent);normal=np.array([-axis[1],axis[0]])
                    length=float(np.ptp(vertices@axis));width=float(np.ptp(vertices@normal))
                    dimension_good=all(lo-limits['marker']<=value<=hi+limits['marker'] for value,(lo,hi) in ((width,end['marker']['width']),(length,end['marker']['length'])))
                    anchor=vertices.mean(axis=0) if end['marker']['anchor_role']=='center' else vertices[np.argmin(np.linalg.norm(vertices-np.asarray(end['marker']['anchor']),axis=1))]
                    anchor_good=math.dist(anchor,end['marker']['anchor'])<=limits['marker']
                    marker_check.update(dimensions={'passed':dimension_good,'width':width,'length':length},anchor={'passed':anchor_good,'actual':anchor.tolist()})
                    extent=separate_marker_paint_extent(entry,vertices,end['marker']['anchor'])
                    if extent is not None:
                        extent['owner']=custom[0]['owner'];marker_paint_extents[str(index)]=extent
                        marker_check['paint_extent']=extent
                    marker_check['passed']=marker_check['passed'] and dimension_good and anchor_good
                    if end['marker'].get('contour'):
                        expected_contour=LineString(end['marker']['contour']);saved_contour=LineString(vertices)
                        marker_check['contour']=bounded(float(expected_contour.hausdorff_distance(saved_contour)),.05,limits['marker'])
                        marker_check['passed']=marker_check['passed'] and marker_check['contour']['passed']
                    markers.append(marker_check)
            else:
                filled=marker['type'] not in ('none','arrow')
                markers.append(result(marker['type']==end['marker']['type'] and filled==end['marker']['filled'],expected=end['marker']['type'],actual=marker['type'],method='native_line_ending'))
                if end['marker']['type']!='none' and math.dist(end['marker']['anchor'],p)>limits['endpoint']:
                    markers[-1]=invalid('Noncoincident marker anchor requires a separately measured native marker owner')
            contact=end['attachment']
            if contact['kind']!='free':
                target_binding=bindings[contact['feature']];targets=target_binding['owners']
                actual_contact=anchor if custom and contact['kind'] in ('marker_center_on_boundary','circle_half_embedded') else p
                pt=Point(actual_contact)
                if contact['kind']=='line_junction':
                    peers=[decoded[name] for name in targets if name in decoded and not decoded[name]['closed']]
                    if not peers:raise ValueError('Line junction needs a measured open peer shaft')
                    domains=[LineString(flatten(peer['segments'],epsilon)[0]) for peer in peers]
                    distance=float(pt.distance(unary_union(domains)))
                else:
                    from .connection_geometry import _boundary
                    body=unary_union([_boundary(nodes[name]) for name in targets])
                    distance=float(pt.distance(body.boundary))
                lo,hi=contact['distance'];kind=contact['kind']
                good=lo-limits['endpoint']<=distance<=hi+limits['endpoint']
                if kind=='line_junction':good=max(0,distance-epsilon)>=max(0,lo-limits['endpoint']) and distance+epsilon<=hi+limits['endpoint']
                if kind=='intentional_gap':good=good and not body.contains(pt)
                elif kind=='inside_port':good=good and body.contains(pt)
                check['contact']={'passed':bool(good),'kind':kind,'distance':distance,'targets':targets}
                if kind=='line_junction':check['contact']['approximation_error']=epsilon
                check['passed']=check['passed'] and good
                entry=nodes[q['owner']]
                if kind=='line_junction':
                    check['native_binding_scope']='source-declared shaft junction; independent geometry and reciprocal topology required; automatic rerouting is not claimed'
                elif entry['tag']=='cxnSp':
                    connection=entry['node'].find('p:nvCxnSpPr/p:cNvCxnSpPr/a:'+('stCxn' if native_index==0 else 'endCxn'),NS)
                    ids={nodes[name]['node'].find('.//p:cNvPr',NS).get('id') for name in targets}
                    connected=connection is not None and connection.get('id') in ids
                    check['native_binding']={'passed':connected,'expected_ids':sorted(ids),'actual_id':connection.get('id') if connection is not None else None}
                    check['passed']=check['passed'] and connected
                else:check['native_binding_scope']='editable geometry association; automatic rerouting is not claimed'
            terminals.append(check)
    for owner,q in shafts:
        style=q['style'];expected_style=source['stroke']
        rgb=lambda s:np.asarray([int(s[i:i+2],16)/255 for i in (0,2,4)])
        colour=float(np.linalg.norm(rgb(style['colour'])-rgb(expected_style['colour']))/math.sqrt(3))
        width_bounds=style['width_source_bounds'];source_width=expected_style['width']
        good=(colour<=limits['colour'] and expected_style['opacity'][0]<=style['opacity']<=expected_style['opacity'][1] and
              all(style[key]==expected_style[key] for key in ('cap','join','compound')) and style['dash']==expected_style['dash']['kind'])
        if style.get('paint_mode')!='filled_body':
            good=good and style['width_emu']>0 and source_width[0]-limits['width']<=width_bounds[0] and width_bounds[1]<=source_width[1]+limits['width']
        stroke.append(result(good,owner=owner,actual=style,colour_error=colour,method='effective_saved_native_style'))
    route['status']='PASS' if route['passed'] else 'FAIL' if route['valid'] else 'INVALID'
    def aggregate(values):
        return {'passed':all(v['passed'] for v in values),'valid':all(v.get('valid') is True for v in values),'items':values,
                'applicable':bool(values),'scope':'checked items' if values else 'source-proved closed route has no terminals'}
    occlusions=[];order={name:i for i,name in enumerate(nodes)}
    for item in source['visibility']['hidden']:
        points,_=flatten([source['path']['segments'][item['segment']]],epsilon)
        from shapely.ops import substring
        path=LineString(points);piece=substring(path,item['range'][0]*path.length,item['range'][1]*path.length)
        from .connection_geometry import _boundary
        bodies=[]
        for name in bindings[item['occluder']]['owners']:
            entry=nodes[name];props=entry['node'].find('p:spPr',NS)
            fill=props.find('a:solidFill/a:srgbClr',NS) if props is not None else None
            if fill is None:raise ValueError('MEASUREMENT_REQUIRED: hidden line needs a qualified opaque occluder')
            alpha=fill.find('a:alpha',NS)
            if alpha is not None and int(alpha.get('val'))!=100000:raise ValueError('MEASUREMENT_REQUIRED: translucent occlusion is not fully hidden')
            if any(order[name]<=order[owner] for owner,_ in shafts):continue
            bodies.append(_boundary(entry))
        good=bool(bodies) and piece.difference(unary_union(bodies).buffer(limits['route'])).is_empty
        occlusions.append(result(good,occluder=item['occluder'],segment=item['segment'],scope='opaque actual owner covers original hidden interval and paints after shafts'))
    return {'route':route,'terminals':aggregate(terminals),'markers':aggregate(markers),'stroke':aggregate(stroke),'visibility_native':aggregate(occlusions),
            'paths':paths,'expected':expected,'oriented':oriented,'marker_paint_extents':marker_paint_extents}
