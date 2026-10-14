"""Source-bound multi-scale icon quality; geometry and pixels are independent.

No super-resolution inference or restoration of unknown scientific facts.
Edge-spread limits are engineering defaults validated by synthetic controls,
not a claim of ISO optical measurement or universal perceptual aesthetics.
"""
import math, hashlib, copy
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union, polygonize
from .common import read_json, write_json, digest, identity, ROOT
from .mathml import NS

VERSION = 'icon-hd-3'

def profile():
    return read_json(ROOT/'config/icon-hd-profiles.json')

def source_survey(task, state):
    """Fixed full-canvas windows, independent of names and semantic proposals."""
    from .execution_contract import resource
    from .icon_clarity import statistics
    from .resource_facts import image_view
    rows=[];step=128
    with image_view(resource(task,state['source']),state['source']['sha256']) as im:
        if list(im.size)!=state['source_size']: raise ValueError('Original canvas changed')
        for y in range(0,im.height,step):
            for x in range(0,im.width,step):
                roi=[x,y,min(step,im.width-x),min(step,im.height-y)]
                with im.crop((x,y,x+roi[2],y+roi[3])) as crop:
                    stats=statistics(crop)
                    rows.append({'id':f'window:{x}:{y}','roi':roi,'pixel_hash':hashlib.sha256(np.asarray(crop).tobytes()).hexdigest(),
                                 'edge_support':stats['edge_support_fraction']})
    return rows

def closure(nodes, owners):
    names=set(owners)
    if not names or not names<=set(nodes): raise ValueError('Missing actual icon owners')
    while True:
        added={n for n,v in nodes.items() if v.get('parent_name') in names}-names
        if not added: return names
        names|=added

def validate_target(row, unit):
    from .source_contract import finite
    finite(row,'icon_hd_target')
    t=row.get('target',{})
    if t.get('representation')!='editable_vector': raise ValueError('HD icons require editable native vectors')
    p=profile()
    if t.get('profile') not in p['styles']: raise ValueError('Freeze observed flat/outlined/shaded style')
    probes=t.get('edge_probes',[])
    if len(probes)<p['minimum_edge_probes'] or len({r['id'] for r in probes})!=len(probes):
        raise ValueError('HD quality needs distinct source-located edge probes')
    x,y,w,h=unit['roi']
    for probe in probes:
        points=probe.get('points',[])
        if len(points)!=2 or any(len(q)!=2 for q in points) or math.dist(*points)<4 or not probe.get('source_evidence'):
            raise ValueError('Original silhouette/material transition probe required')
        if any(not x-8<=q[0]<=x+w+8 or not y-8<=q[1]<=y+h+8 for q in points):
            raise ValueError('Edge probe escaped the unchanged source context')
    patches=t.get('smooth_patches',[])
    if t['profile']=='shaded' and not patches: raise ValueError('Shaded materials require source-supported smooth interior patches')
    for patch in patches:
        a,b,c,d=patch['roi']
        if min(c,d)<3 or a<x or b<y or a+c>x+w or b+d>y+h or not patch.get('source_evidence'):
            raise ValueError('Material patch must remain inside the original object window')
    relations=row.get('relations')
    if not isinstance(relations,list) or len({r.get('id') for r in relations})!=len(relations):
        raise ValueError('Unique executable relations; explicit empty only for an isolated leaf')
    for rel in relations:
        if rel.get('kind') not in ('distance','overlap','contains','aligned','source_contact') or len(rel.get('parts',[]))!=2 or len(set(rel['parts']))!=2 or not rel.get('source_evidence'):
            raise ValueError('Source-supported typed icon relation required')
        if not any(k in rel for k in ('min','max')) or any(type(rel[k]) not in (int,float) for k in ('min','max') if k in rel):
            raise ValueError('Freeze finite numeric relation bounds before constructing')
        if any(rel[k]<0 for k in ('min','max') if k in rel) or ('min' in rel and 'max' in rel and rel['min']>rel['max']):
            raise ValueError('Nonnegative ordered relation bounds required')
        if rel['kind'] in ('contains','overlap') and any(rel[k]>1 for k in ('min','max') if k in rel):
            raise ValueError('Area fraction bounds must stay in [0,1]')
        if rel.get('kind')=='aligned' and rel.get('axis') not in ('x','y'): raise ValueError('Alignment axis required')
        if rel['kind']=='source_contact':
            point=rel.get('point',[])
            if not isinstance(point,(list,tuple)) or len(point)!=2 or any(type(v) not in (int,float) for v in point):
                raise ValueError('Original contact needs one finite canvas point')
            if 'max' not in rel or not 0<=rel['max']<=.05 or rel.get('min',0)!=0:
                raise ValueError('Contact tolerance only permits native serialization rounding, up to .05 source pixels')
            if not x-8<=point[0]<=x+w+8 or not y-8<=point[1]<=y+h+8:
                raise ValueError('Original contact escaped the unchanged source context')
    if not row.get('relation_inventory_evidence'): raise ValueError('Explain the complete original relation inventory, including intentional separations')

def pdf_evidence(task,state,candidate):
    from .execution_contract import resource
    resource(task,candidate['pptx']);resource(task,candidate['preview'])
    render=read_json(resource(task,candidate['render']))
    if render.get('pptx_hash')!=candidate['pptx']['sha256'] or render.get('preview_hash')!=candidate['preview']['sha256']:
        raise ValueError('HD measurement requires the actual current saved/rendered candidate')
    pdf=Path(task)/candidate['render']['path'];pdf=pdf.parent/'Final.pdf'
    expected=render.get('pdf_hash') or render.get('pdf_sha256')
    reexport=None
    if not pdf.is_file() and (pdf.parent/'Pdf-lifecycle.json').is_file():
        from .transient_export import live_pdf
        pdf,reexport=live_pdf(pdf.parent,resource(task,candidate['pptx']),state.get('capabilities'))
        expected=reexport['pdf_sha256']
    if not pdf.is_file() or not expected or digest(pdf)!=expected:
        raise ValueError('Actual vector PDF hash required; enlarged PNG interpolation is not HD evidence')
    return pdf, {'pptx_hash':candidate['pptx']['sha256'],'render_hash':candidate['render']['sha256'],
                 'pdf_hash':expected,'backend':render.get('backend'),'scales':profile()['scales'],'reexport':reexport}

def pdf_window(pdf, canvas, roi, scale):
    from .resource_facts import pdf_clip
    return pdf_clip(pdf,canvas,roi,scale)

def edge_profile(image, mapping, points):
    """RGB projected edge spread, absolute width in original display pixels."""
    def invalid(reason,code,**values):
        return {'valid':False,'status':'MEASUREMENT_INVALID','reason':reason,'reason_code':code,**values}
    points=np.asarray(points,float);scale=float(mapping['scale'])
    if points.shape!=(2,2) or not np.isfinite(points).all() or not math.isfinite(scale) or scale<=0:
        return invalid('Finite probe endpoints and a positive actual scale required','INVALID_PROBE_DOMAIN')
    length=float(np.linalg.norm(points[1]-points[0]))
    if not math.isfinite(length) or length<=0:
        return invalid('Nonzero finite probe length required','DEGENERATE_PROBE')
    samples=max(64,math.ceil(length*scale*4))
    f=np.linspace(0,1,samples);xy=points[0]+f[:,None]*(points[1]-points[0])
    pixel=(xy-np.asarray(mapping['origin']))*mapping['scale']-.5
    if np.any(pixel<-.5) or np.any(pixel[:,0]>image.shape[1]-.5) or np.any(pixel[:,1]>image.shape[0]-.5):
        return invalid('Edge sampling escaped actual context','PROBE_OUTSIDE_CONTEXT')
    rgb=np.array([map_coordinates(image[:,:,c],[pixel[:,1],pixel[:,0]],order=1,mode='nearest') for c in range(3)]).T
    n=max(4,samples//6);low=rgb[:n].mean(0);high=rgb[-n:].mean(0);delta=high-low;contrast=float(np.linalg.norm(delta))
    if not np.isfinite(rgb).all() or not math.isfinite(contrast):
        return invalid('Nonfinite sampled edge values','NONFINITE_SAMPLES')
    if contrast<profile()['minimum_probe_contrast']: return invalid('insufficient actual boundary contrast','INSUFFICIENT_CONTRAST',contrast=contrast)
    values=(rgb-low)@delta/max(delta@delta,1e-12)
    # Measure the monotone envelope but independently reject oscillation/ringing.
    monotone=np.maximum.accumulate(np.clip(values,0,1))
    def crossing(level):
        i=int(np.searchsorted(monotone,level))
        if not 1<=i<len(f) or not monotone[i-1]<level<=monotone[i]:return None
        interval=float(monotone[i]-monotone[i-1])
        if interval<=1e-12:return None
        position=float((f[i-1]+(f[i]-f[i-1])*(level-monotone[i-1])/interval)*length)
        return position if math.isfinite(position) and 0<=position<=length else None
    positions=[crossing(v) for v in (.1,.5,.9)]
    peak=float(max(0,-values.min(),values.max()-1))
    reversal=float(np.maximum(0,-np.diff(values)).sum())
    if any(v is None for v in positions) or not positions[0]<positions[1]<positions[2]:
        return invalid('The 10/50/90 percent crossings are not bracketed and ordered inside this probe',
                       'UNBRACKETED_EDGE_CROSSING',contrast=contrast,overshoot=peak,reversal=reversal)
    width=positions[2]-positions[0]
    return {'valid':True,'status':'MEASURED','edge_width_px':width,'overshoot':peak,'reversal':reversal,'contrast':contrast,
            'edge_position_px':positions[1],'crossings_px':positions,'probe_length_px':length,
            'direction':'width/overshoot/reversal lower is better'}

def material_residual(image):
    """Remove a smooth quadratic field; residual detects grain/mosaic, not style."""
    h,w=image.shape[:2];y,x=np.mgrid[-1:1:complex(h),-1:1:complex(w)]
    basis=np.stack([np.ones_like(x),x,y,x*x,x*y,y*y],axis=-1).reshape(-1,6)
    target=image.reshape(-1,3);coef=np.linalg.lstsq(basis,target,rcond=None)[0]
    return float(np.sqrt(np.mean((target-basis@coef)**2)))

def _winding_geometry(contours):
    """Actual nonzero-fill faces, including holes and legal self-touching paths."""
    contours=[points for points in contours if len(points)>=3]
    if not contours:return Polygon()
    lines=unary_union([LineString(points+[points[0]]) for points in contours])
    def winding(points,q):
        n=0;x,y=q
        for (ax,ay),(bx,by) in zip(points,points[1:]+points[:1]):
            cross=(bx-ax)*(y-ay)-(x-ax)*(by-ay)
            if ay<=y<by and cross>0:n+=1
            elif by<=y<ay and cross<0:n-=1
        return n
    faces=[]
    for face in polygonize(lines):
        q=list(face.representative_point().coords)[0]
        if sum(winding(points,q) for points in contours)!=0:faces.append(face)
    return unary_union(faces) if faces else Polygon()


def native_geometry(nodes, name, content_geometry=None):
    from .neighbor_geometry import _paths,_stroke
    out=[]
    for n in closure(nodes,[name]):
        row=nodes[n]
        if row['tag']=='grpSp': continue
        if row['tag'] not in ('sp','cxnSp'): raise ValueError('A picture/SVG/table is not an internally editable native icon: '+n)
        if row['node'].findall('.//a:t',NS) or row['node'].findall('.//m:oMath',NS):
            geometry=(content_geometry or {}).get(n)
            if geometry is None or geometry.is_empty or not geometry.is_valid:
                raise ValueError('Icon text/math needs its own typed source unit and actual current glyph capture: '+n)
            out.append(geometry);continue
        props=row['node'].find('p:spPr',NS)
        if props is None: raise ValueError('Missing native paint properties')
        if any(len(e) for e in props.findall('a:effectLst',NS)+props.findall('a:effectDag',NS)):
            raise ValueError('HD icon cannot silently use blur/soft-edge effects')
        width=_stroke(row,props);fill=any(props.find('a:'+k,NS) is not None for k in ('solidFill','gradFill','pattFill'))
        if fill:
            from .native_paint import opaque_fill
            opaque_fill(props,gradient=True)
        paths=_paths(row,props)
        if fill:
            custom=props.find('a:custGeom/a:pathLst',NS)
            groups=[]
            if custom is None:groups=[paths]
            else:
                # Separate DrawingML paths paint independently; their subpaths
                # share nonzero winding. Unioning contour polygons fills holes.
                for i in range(len(custom)):
                    isolated=copy.deepcopy(props);lst=isolated.find('a:custGeom/a:pathLst',NS)
                    for j in reversed(range(len(lst))):
                        if j!=i:lst.remove(lst[j])
                    groups.append(_paths(row,isolated))
            for group in groups:
                region=_winding_geometry([points for points,closed,paintfill in group if closed and paintfill])
                if not region.is_empty:out.append(region)
        for points,closed,paintfill in paths:
            if width and len(points)>1: out.append(LineString(points+[points[0]] if closed else points).buffer(width/2))
    if not out: raise ValueError('Empty native icon paint')
    return unary_union(out)

def measure_relations(nodes,relations,content_geometry=None):
    rows=[];cache={}
    for rel in relations:
        for name in rel['parts']:
            if name not in cache:cache[name]=native_geometry(nodes,name,content_geometry)
        a,b=(cache[n] for n in rel['parts']);kind=rel['kind']
        if kind=='distance': value=float(a.distance(b))
        elif kind=='overlap': value=float(a.intersection(b).area/max(min(a.area,b.area),1e-12))
        elif kind=='contains': value=float(a.difference(b).area/max(a.area,1e-12))
        elif kind=='source_contact':
            point=Point(rel['point']);value=float(max(point.distance(a),point.distance(b)))
        else:
            i=0 if rel['axis']=='x' else 1;value=abs((a.bounds[i]+a.bounds[i+2]-b.bounds[i]-b.bounds[i+2])/2)
        passed=('min' not in rel or value>=rel['min']) and ('max' not in rel or value<=rel['max'])
        rows.append({'id':rel['id'],'kind':kind,'parts':rel['parts'],'value':value,'min':rel.get('min'),'max':rel.get('max'),'passed':bool(passed),
                     **({'point':rel['point']} if kind=='source_contact' else {})})
    return rows

def measure(task,state,candidate,unit,row,nodes=None):
    from .boundary_geometry import saved_nodes
    from .execution_contract import resource
    validate_target(row,unit);pdf,evidence=pdf_evidence(task,state,candidate)
    nodes=nodes or saved_nodes(resource(task,candidate['pptx']),state['source_size'])
    names=closure(nodes,unit['objects']);leaves=sorted(n for n in names if nodes[n]['tag']!='grpSp')
    typed_content={};delegated=[]
    text_names=[n for n in leaves if nodes[n]['node'].findall('.//a:t',NS) or nodes[n]['node'].findall('.//m:oMath',NS)]
    if text_names:
        from .neighbor_geometry import read as painted_owners
        paint,errors=painted_owners(task,state,candidate,state.get('neighbor_mattes'))
        for name in text_names:
            math_object=bool(nodes[name]['node'].findall('.//m:oMath',NS));kind='formula' if math_object else 'text'
            own=[u for u in state.get('quality',{}).get('units',{}).values() if u.get('profile')==kind and name in u.get('objects',[])]
            if not own or name not in paint or paint[name].get('method')!='ACTUAL_HOST_OWNER_MATTE':
                raise ValueError('Mixed icon content requires independent '+kind+' source registration and current actual glyph paint: '+name)
            typed_content[name]=paint[name]['geometry'];delegated.append({'object':name,'profile':kind,'units':[u['id'] for u in own],
                'geometry':'current actual owner glyph matte','content_checks':'Independent whole-result text/Office Math gates remain mandatory'})
    native_geometry(nodes,unit['objects'][0],typed_content)
    # Every bound owner and descendant, not merely the first semantic root.
    for name in unit['objects'][1:]: native_geometry(nodes,name,typed_content)
    target=row['target'];p=profile();scales=[];x,y,w,h=unit['roi']
    context=[max(0,x-8),max(0,y-8),min(state['source_size'][0],x+w+8)-max(0,x-8),min(state['source_size'][1],y+h+8)-max(0,y-8)]
    for scale,limit in zip(p['scales'],p['edge_width_limits_px']):
        image,mapping=pdf_window(pdf,state['source_size'],context,scale)
        probes=[]
        for probe in target['edge_probes']:
            value=edge_profile(image,mapping,probe['points']);passed=value.get('valid') is True and value['edge_width_px']<=limit and value['overshoot']<=p['maximum_overshoot'] and value['reversal']<=p['maximum_reversal']
            probes.append({'id':probe['id'],**value,'limit_px':limit,'passed':bool(passed)})
        scales.append({'scale':scale,'probes':probes,'passed':all(v['passed'] for v in probes)})
    # A noisy field can raise whole-window Laplacian energy while a cleaner
    # icon lowers it. Compare the very same supported boundaries instead.
    box=[math.floor(context[0]),math.floor(context[1]),math.ceil(context[0]+context[2]),math.ceil(context[1]+context[3])]
    from .resource_facts import image_region
    with image_region(resource(task,state['source']),[('crop',box)],state['source']['sha256']) as crop:
        source_pixels=np.asarray(crop,float)/255.
    paired=[]
    for probe,actual in zip(target['edge_probes'],scales[-1]['probes']):
        source=edge_profile(source_pixels,{'origin':box[:2],'scale':1},probe['points'])
        gain=source.get('edge_width_px',0)/max(actual.get('edge_width_px',0),1e-12) if source.get('valid') and actual.get('valid') else None
        applicable=row.get('category')=='blurred_icon'
        paired.append({'id':probe['id'],'source':source,'actual':actual,'gain':gain,'applicable':applicable,
                       'passed':not applicable or bool(gain is not None and gain>=target.get('min_sharpness_gain',1.))})
    paired_pass=all(r['passed'] for r in paired) if row.get('category')=='blurred_icon' else True
    invalid_probes=[{'domain':'actual','scale':s['scale'],'id':v['id'],'reason_code':v.get('reason_code'),'reason':v.get('reason')}
                    for s in scales for v in s['probes'] if v.get('valid') is not True]
    invalid_probes += [{'domain':'source','scale':1,'id':v['id'],'reason_code':v['source'].get('reason_code'),'reason':v['source'].get('reason')}
                      for v in paired if v['source'].get('valid') is not True]
    measurement_valid=not invalid_probes
    patches=[]
    for patch in target.get('smooth_patches',[]):
        # Same actual 4x vector rendering; no repeated full-page PDF evaluation
        # for each small surface and no enlargement of a lower-scale bitmap.
        if scale!=max(p['scales']):raise ValueError('HD scales must end at their largest actual sample')
        a,b,c,d=patch['roi'];sx,sy=mapping['origin'];z=mapping['scale']
        window=[math.floor((a-sx)*z),math.floor((b-sy)*z),math.ceil((a+c-sx)*z),math.ceil((b+d-sy)*z)]
        if min(window[:2])<0 or window[2]>image.shape[1] or window[3]>image.shape[0]:raise ValueError('Material patch escaped actual HD context')
        material=image[window[1]:window[3],window[0]:window[2]]
        residual=material_residual(material);patches.append({'id':patch['id'],'residual':residual,'max':p['styles'][target['profile']]['material_residual_max'],
            'actual_pixel_window':window,'passed':residual<=p['styles'][target['profile']]['material_residual_max']})
    relations=measure_relations(nodes,row['relations'],typed_content)
    # Prevent omitting assembly checks while registering several native parts.
    if len(leaves)>1 and not relations: raise ValueError('Multi-part icon needs executable relationship closure')
    covered={n for r in row['relations'] for owner in r['parts'] if owner not in unit['objects'] or nodes[owner]['tag']!='grpSp' for n in closure(nodes,[owner])}
    if len(leaves)>1 and not set(leaves)<=covered:
        raise ValueError('Every HD native part must participate in an executable assembly/containment relation: '+str(sorted(set(leaves)-covered)[:8]))
    return {'schema':VERSION,'passed':measurement_valid and all(v['passed'] for v in scales+patches+relations) and paired_pass,
            'measurement_valid':measurement_valid,'measurement_failures':invalid_probes,
            'status':'MEASUREMENT_INVALID' if not measurement_valid else 'MEASURED',
            'paired_clarity':{'passed':paired_pass,'required_gain':target.get('min_sharpness_gain'),
                              'source_scale':1,'actual_scale':p['scales'][-1],'probes':paired,
                              'basis':'Same original-world RGB boundary, width in source pixels; whole-window gradient/curvature energy remains diagnostic, not a monotonic clarity oracle'},
            'scales':scales,'materials':patches,'relations':relations,'native_parts':leaves,
            'native_editable_vector':True,'delegated_typed_content':delegated,'configuration_hash':identity(p),'evidence':evidence,
            'scope':'Current native descendants, current vector PDF; no interpolated preview or sharpness-only waiver'}
