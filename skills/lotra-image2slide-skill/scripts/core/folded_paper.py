"""Editable folded-paper geometry with shared vertices and unique edge owners.

The host chooses the source-supported subtype/corner. Parameters and source
fits are numerical. Acceptance reads saved DrawingML rather than recipe data.
"""
import math,copy
import numpy as np
from .common import identity
from .mathml import NS

VERSION='coherent-folded-paper-1'
ROLES=('paper','fold','outer','crease')

def geometry(parameters):
    x,y,w,h=map(float,parameters['bbox']);u,v=map(float,parameters['fold_size'])
    if min(w,h,u,v)<=0 or u>=w or v>=h or not np.isfinite([x,y,w,h,u,v]).all():raise ValueError('Finite source paper and fold dimensions required')
    corner=parameters.get('corner','top_right')
    if corner not in ('top_right','top_left','bottom_right','bottom_left'):raise ValueError('Observe the supported fold corner')
    def p(a,b):
        return [x+(w-a if 'left' in corner else a),y+(h-b if 'bottom' in corner else b)]
    tl,a,b,br,bl,c=[p(*z) for z in [(0,0),(w-u,0),(w,v),(w,h),(0,h),(w-u,v)]]
    return {'A':a,'B':b,'C':c,'paper':[tl,a,c,b,br,bl],'fold':[a,c,b],'outer':[tl,a,b,br,bl],'crease':[a,c,b]}

def feature_spec(parameters,source_hash,evidence,retained=None):
    if not evidence:raise ValueError('Original fold anatomy evidence required')
    g=geometry(parameters);style=parameters['style'];parts=[]
    for role in ROLES:
        stroke=style['stroke'] if role in ('outer','crease') else None
        fill=style.get('paper_fill','FFFFFF') if role=='paper' else style.get('fold_fill','FFFFFF') if role=='fold' else None
        width=style['crease_width'] if role=='crease' else style['outer_width'] if role=='outer' else 0
        parts.append({'id':role,'kind':'polyline' if role=='crease' else 'polygon','points':g[role],'role':'folded_paper_'+role,
                      'style':{'fill':fill,'stroke':stroke,**({'line_width':width/parameters.get('source_pixels_per_point',1.)} if stroke else {})},'source_evidence':evidence})
    spec={'schema':'source-feature-function-1','source_hash':source_hash,'source_evidence':evidence,'bbox':parameters['bbox'],
          'name_separator':'__','parts':parts,'features':[{'id':'source_folded_paper','observed':evidence,'parts':list(ROLES)}],
          'assembly_function':{'version':VERSION,'parameters':copy.deepcopy(parameters),'covered_roles':list(ROLES),'scope':'assembly',
                               'edge_owners':{'AB':'outer','AC':'crease','CB':'crease'},'shared_vertices':{k:g[k] for k in ('A','B','C')}},
          'retained_objects':copy.deepcopy(retained or [])}
    return spec

def fit(rgb,roi,initial,exclusion=None):
    """Fit original-only edges; bitmap blur is a nuisance, never output blur."""
    from scipy.optimize import least_squares
    from scipy.special import ndtr
    data=np.asarray(rgb,float)/255.;hh,ww=data.shape[:2];x0,y0=roi[:2]
    yy,xx=np.indices((hh,ww),float);xx+=x0+.5;yy+=y0+.5
    x,y,w,h=initial['bbox'];u,v=initial['fold_size']
    if initial.get('corner','top_right')!='top_right':raise ValueError('This image fitter requires a source-observed top-right fold; other corners use transformed source windows')
    mask=(xx<x+3)|(xx>x+w-3)|(yy<y+3)|(yy>y+h-3)|((xx>x+w-u-3)&(yy<y+v+3))
    if exclusion is not None:mask &= ~np.asarray(exclusion,bool)
    darkness=1-data.mean(2)
    def distance(aa,bb):
        dx,dy=bb[0]-aa[0],bb[1]-aa[1];t=np.clip(((xx-aa[0])*dx+(yy-aa[1])*dy)/max(dx*dx+dy*dy,1e-10),0,1)
        return np.hypot(xx-aa[0]-t*dx,yy-aa[1]-t*dy)
    def predict(p):
        px,py,pw,ph,pu,pv,stroke,sigma=p;g=geometry({'bbox':[px,py,pw,ph],'fold_size':[pu,pv]});pts=g['outer'];dist=np.full((hh,ww),np.inf)
        for aa,bb in zip(pts,pts[1:]+pts[:1]):dist=np.minimum(dist,distance(aa,bb))
        for aa,bb in zip(g['crease'],g['crease'][1:]):dist=np.minimum(dist,distance(aa,bb))
        return ndtr((stroke/2-dist)/sigma)
    p=np.array([x,y,w,h,u,v,1.8,.55]);lower=np.array([x-2,y-2,w-3,h-3,max(2,u-4),max(2,v-4),.8,.15]);upper=np.array([x+2,y+2,w+3,h+3,u+4,v+4,3.8,1.5])
    result=least_squares(lambda z:(predict(z)-darkness)[mask],p,bounds=(lower,upper),max_nfev=100,loss='soft_l1',f_scale=.12)
    px,py,pw,ph,pu,pv,stroke,sigma=result.x
    return {'bbox':[px,py,pw,ph],'fold_size':[pu,pv],'corner':'top_right',
            'style':{'stroke':'000000','paper_fill':'FFFFFF','fold_fill':'FFFFFF','outer_width':float(stroke),'crease_width':float(stroke)},
            'fit':{'source_only':True,'source_roi':roi,'cost':float(result.cost),'success':bool(result.success),'nuisance_blur_sigma':float(sigma),'fit_samples':int(mask.sum()),'model':VERSION}}

def _paths(entry):
    props=entry['node'].find('p:spPr',NS);rows=[]
    for path in props.findall('a:custGeom/a:pathLst/a:path',NS):
        w,h=float(path.get('w')),float(path.get('h'));pts=[];closed=False
        for cmd in path:
            op=cmd.tag.split('}')[-1]
            if op in ('moveTo','lnTo'):
                p=cmd[0];pts.append((np.array([float(p.get('x'))/w,float(p.get('y'))/h,1.])@entry['matrix'].T)[:2].tolist())
            elif op=='close':closed=True
            else:raise ValueError('Fold subtype requires finite native line edges')
        rows.append({'points':pts,'closed':closed})
    if len(rows)!=1:raise ValueError('One explicit native path per coherent paper role required')
    return rows[0]

def check_saved(nodes,root,parameters,tolerance=.01):
    from .neighbor_geometry import _stroke
    from shapely.geometry import Polygon
    expected=geometry(parameters);errors=[];actual={};native={}
    for role in ROLES:
        name=root+'__'+role
        if name not in nodes:errors.append({'code':'PAPER_ROLE_MISSING','object':name});continue
        try:
            entry=nodes[name];path=_paths(entry);props=entry['node'].find('p:spPr',NS);width=_stroke(entry,props);fill=props.find('a:solidFill/a:srgbClr',NS)
            actual[role]=path;native[role]={'width':width,'fill':fill.get('val') if fill is not None else None,'order':list(nodes).index(name)}
            exp=expected[role];pts=path['points']
            error=max(float(np.linalg.norm(np.array(a)-b)) for a,b in zip(pts,exp)) if len(pts)==len(exp) else None
            if error is None or error>tolerance:errors.append({'code':'PAPER_SHARED_GEOMETRY_FAILED','role':role,'maximum_vertex_error_px':error,'tolerance_px':tolerance})
            if path['closed']!=(role!='crease'):errors.append({'code':'PAPER_CLOSURE_FAILED','role':role})
            required_width=parameters['style']['crease_width'] if role=='crease' else parameters['style']['outer_width'] if role=='outer' else 0
            if abs(width-required_width)>tolerance:errors.append({'code':'PAPER_VISIBLE_EDGE_STYLE_FAILED','role':role,'actual_width_px':width,'expected_width_px':required_width})
            expected_fill=parameters['style'].get('paper_fill','FFFFFF') if role=='paper' else parameters['style'].get('fold_fill','FFFFFF') if role=='fold' else None
            if native[role]['fill']!=expected_fill:errors.append({'code':'PAPER_FILL_FAILED','role':role,'actual':native[role]['fill'],'expected':expected_fill})
        except (ValueError,TypeError,KeyError) as e:errors.append({'code':'PAPER_NATIVE_MEASUREMENT_MISSING','role':role,'reason':str(e)})
    if len(actual)==4:
        outer=Polygon(actual['outer']['points']);fills=Polygon(actual['paper']['points']).union(Polygon(actual['fold']['points']))
        error=fills.symmetric_difference(outer).area
        if error>tolerance*outer.length:errors.append({'code':'PAPER_CUT_FILL_OR_HOLE_FAILED','area_error_px2':error})
        # Independently count matching visible edge segments in the saved file.
        owners={}
        for role,path in actual.items():
            if native[role]['width']<=0:continue
            pts=path['points'];edges=list(zip(pts,pts[1:]+pts[:1] if path['closed'] else pts[1:]))
            for label,aa,bb in [('AB',expected['A'],expected['B']),('AC',expected['A'],expected['C']),('CB',expected['C'],expected['B'])]:
                for a,b in edges:
                    if min(max(np.linalg.norm(np.array(a)-aa),np.linalg.norm(np.array(b)-bb)),max(np.linalg.norm(np.array(a)-bb),np.linalg.norm(np.array(b)-aa)))<=tolerance:owners.setdefault(label,[]).append(role)
        if owners!={'AB':['outer'],'AC':['crease'],'CB':['crease']}:errors.append({'code':'PAPER_DUPLICATE_OR_MISSING_EDGE','actual_owners':owners})
        if max(native[r]['order'] for r in ('paper','fold'))>=min(native[r]['order'] for r in ('outer','crease')):errors.append({'code':'PAPER_LAYER_FAILED'})
    return {'root':root,'passed':not errors,'errors':errors,'native_roles':native,'shared_vertex_precision_px':tolerance,'constructor':VERSION,
            'scope':'Actual saved native vertices, edge ownership, cut coverage, style and layers; actual host render required separately.'}

def report(task,state,candidate):
    from .source_feature_functions import specifications,semantic_root
    from .boundary_geometry import saved_nodes
    from .common import safe_path
    specs=specifications(task,state);rows=[];nodes=None
    for uid,spec in specs.items():
        meta=spec.get('assembly_function')
        if not meta:continue
        if meta.get('version')!=VERSION or meta.get('scope')!='assembly' or set(meta.get('covered_roles',[]))!=set(ROLES):
            rows.append({'unit':uid,'passed':False,'errors':[{'code':'PAPER_CONSTRUCTOR_SCOPE_INSUFFICIENT'}]});continue
        if nodes is None:nodes=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
        root=semantic_root(state['quality']['units'][uid],spec);row=check_saved(nodes,root,meta['parameters']);row['unit']=uid;rows.append(row)
    required=state.get('coherent_paper_required',[])
    missing=set(required)-{r['unit'] for r in rows}
    return {'passed':not missing and all(r['passed'] for r in rows),'items':rows,'missing':sorted(missing),'status':'COHERENT_PAPER_CLOSED' if not missing and all(r['passed'] for r in rows) else 'COHERENT_PAPER_WORK_REQUIRED'}
