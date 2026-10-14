"""Classify original same-root part spacing before checking or repairing output.

The model supplies original segmentation and named roles. This module reads
only the immutable original/crops/masks to decide contact versus separation.
Neither a candidate matte nor a desired relationship is a classification input.
Raster uncertainty crossing the fixed threshold remains unresolved.
"""
import copy, math
from pathlib import Path
import numpy as np
from .common import digest, identity, read_json, write_json, safe_path, writer

VERSION='original-spacing-1'
POLICY={'version':VERSION,'distance_unit':'source_px',
    'classification_threshold_px':2.5,'attached_output_max_distance_px':.75,
    'source_contact_width_fraction':.5,'minimum_output_solid_width_px':1.,
    'connectivity':4,'source_sampling':'unchanged_original_grid',
    'uncertainty':'sum_of_two_half_pixel_diagonals'}


def binding(row):
    # Equivalent number spellings, set order and tangent magnitude/sign are
    # the same measurement fact. They cannot obtain a fresh source budget.
    def numbers(values):
        result=[float(v) for v in values]
        if not all(math.isfinite(v) for v in result):raise ValueError('Finite original interface coordinates required')
        return [0. if v==0 else v for v in result]
    pairs=sorted(zip(row['source_roles'],row['part_sets']))
    port=row['port'];tangent=numbers(port['tangent'])
    if len(tangent)!=2:raise ValueError('A two-coordinate original tangent is required')
    scale=max(abs(v) for v in tangent)
    if not scale:raise ValueError('A nonzero original tangent is required')
    # A direction is an unoriented ratio, not a freshly normalized unit
    # vector. Fix the largest magnitude at exactly one and round only this
    # dimensionless identity to 12 decimals. Rebinding this representation
    # divides by exactly one, so it is idempotent; scalar multiples and
    # opposite signs cannot refresh source constraints or repair budgets.
    tangent=[round(v/scale,12) for v in tangent]
    if next(v for v in tangent if v!=0)<0:tangent=[-v for v in tangent]
    return {'root':row['root'],'source_roles':[r for r,_ in pairs],
        'part_sets':[sorted(set(names)) for _,names in pairs],
        'source_root_frame':numbers(row['source_root_frame']),
        'port':{'domain':numbers(port['domain']),'anchor':numbers(port['anchor']),
                'tangent':numbers(tangent)}}


def key(row):
    return identity(binding(row))


def _ledger_refs(task,state,row):
    from .semantic_composition import _ref
    # Scan canonical facts too, so pre-normalization ledger IDs, integer vs
    # float spelling, or a renamed contract cannot bypass old constraints.
    result=[]
    for ref in state.get('source_spacing',{}).get('bindings',{}).values():
        saved=read_json(_ref(task,ref))
        if binding(saved['binding'])==binding(row) and ref not in result:result.append(ref)
    return result


def _preserve(before,after):
    if before['status']!='ORIGINAL_SPACING_CLASSIFIED':return
    old=before['output_rule'];new=after.get('output_rule',{})
    if (after['classification']!=before['classification'] or not new
            or new['distance_px'][0]<old['distance_px'][0]
            or new['distance_px'][1]>old['distance_px'][1]
            or new['solid_width_px']<old['solid_width_px']):
        raise ValueError('Re-segmentation cannot relax or reverse the same frozen original spacing; correct the located source domain through the source-reading workflow')


def classified(task,state,row,request):
    result=compile_original(task,state,row,request)
    from . import semantic_composition as sc
    for ref in _ledger_refs(task,state,row):
        _preserve(read_json(sc._ref(task,ref))['measurement'],result['measurement'])
    # Full contracts() validates embedded spacing itself. Read immutable raw
    # active records here to avoid recursively validating this same input.
    for ref in state.get('semantic_composition',{}).get('contracts',[]):
        prior=read_json(sc._ref(task,ref))
        if prior['id'] in state.get('semantic_composition',{}).get('superseded',{}):continue
        if prior['kind']=='interface' and prior.get('original_spacing') and binding(prior)==binding(row):
            _preserve(compile_original(task,state,prior,prior['original_spacing'])['measurement'],result['measurement'])
    return result


def targets(task,state):
    from . import semantic_composition as sc
    rows=[{'target':{'kind':'interface','id':r['id']},'row':r}
          for r in sc.contracts(task,state) if r['kind']=='interface']
    for root,declaration in state.get('rule_coverage',{}).get('roots',{}).items():
        roles={r['id']:r for r in declaration.get('roles',[])}
        for relation in declaration.get('native_relations',[]):
            if relation['kind'] not in ('attached','adjacent','intentional_separation'):continue
            names=relation['roles'];frame=declaration['source_view']['roi']
            rows.append({'target':{'kind':'native_relation','root':root,'roles':names},
                'row':{'root':root,'source_roles':names,
                    'part_sets':[roles[n]['objects'] for n in names],
                    'source_root_frame':frame,
                    'port':{'domain':[0.,0.,1.,1.],'anchor':[.5,.5],'tangent':[1.,0.]},
                    'relationship':relation['kind'],'limits':{
                        'distance_px':relation.get('distance_px',[0.,.75]),
                        'solid_width_px':0.,'anchor_error_px':max(frame[2:])}}})
    return rows


def locate(task,state,target):
    found=[r['row'] for r in targets(task,state) if r['target']==target]
    if len(found)!=1:raise ValueError('Locate one current same-root interface or native relation')
    return found[0]


def measure_masks(a,b,frame,port):
    """Exact EDT on original centers with conservative source-pixel bounds.

    A face-adjacent original pair has center distance one pixel. At the
    unchanged 1px grid its two half-diagonal errors give [0, 2.414..]. A
    2.5px threshold admits that near-contact only with positive 4-connected
    interface width. A one-pixel blank strip straddles the threshold and is
    deliberately ambiguous. Widely separated parts retain a positive range.
    """
    from scipy.ndimage import distance_transform_edt,label
    from PIL import Image,ImageDraw
    if a.shape!=b.shape or a.ndim!=2:raise ValueError('Two original-grid masks are required')
    x,y,w,h=frame;dx,dy,dw,dh=port['domain']
    image=Image.new('1',(a.shape[1],a.shape[0]))
    ImageDraw.Draw(image).polygon([(x+px*w-.5,y+py*h-.5) for px,py in
        ((dx,dy),(dx+dw,dy),(dx+dw,dy+dh),(dx,dy+dh))],fill=1)
    domain=np.asarray(image,dtype=bool);a=a&domain;b=b&domain
    result={'policy':POLICY,'core_pixels_in_source_port':[int(a.sum()),int(b.sum())],
        'classification':'ambiguous','status':'ORIGINAL_SPACING_UNRESOLVED'}
    if not a.any() or not b.any():return {**result,'reason':'missing_original_part_in_port'}
    if (a&b).any():return {**result,'reason':'visible_source_ownership_overlap_requires_segmentation_review'}
    da=distance_transform_edt(~a);db=distance_transform_edt(~b)
    distance=float(db[a].min());uncertainty=math.sqrt(2.)
    interval=[max(0.,distance-uncertainty),distance+uncertainty]
    threshold=POLICY['classification_threshold_px']
    near=(a&(db<=threshold))|(b&(da<=threshold))
    components,count=label(near,structure=np.array([[0,1,0],[1,1,1],[0,1,0]],int))
    tangent=np.asarray(port['tangent'],float)*np.array([w,h],float)
    tangent/=np.linalg.norm(tangent)
    contacts=[]
    for number in range(1,count+1):
        component=components==number
        if not (np.any(component&a) and np.any(component&b)):continue
        yy,xx=np.where(component);points=np.column_stack((xx+.5,yy+.5))
        projected=points@tangent
        contacts.append({'component':number,'width_lower_px':max(0.,float(np.ptp(projected))-uncertainty)})
    solid=max((r['width_lower_px'] for r in contacts),default=0.)
    result.update(nearest_original_center_distance_px=distance,
        original_distance_interval_px=interval,sampling_uncertainty_px=uncertainty,
        original_contact_components=contacts,original_solid_width_lower_px=solid)
    if interval[0]>threshold:
        result.update(classification='intentional_separation',status='ORIGINAL_SPACING_CLASSIFIED',
            output_rule={'distance_px':interval,'solid_width_px':0.})
    elif interval[1]<=threshold and solid>0:
        result.update(classification='attached',status='ORIGINAL_SPACING_CLASSIFIED',
            output_rule={'distance_px':[0.,POLICY['attached_output_max_distance_px']],
                'solid_width_px':max(POLICY['minimum_output_solid_width_px'],solid*POLICY['source_contact_width_fraction'])})
    else:result['reason']='threshold_or_solid_width_not_resolved_on_original_grid'
    return result


def compile_original(task,state,row,request):
    from . import semantic_composition as sc
    allowed={'schema','source_hash','source_view','mask_origin','masks','segmentation'}
    if set(request)-allowed or request.get('schema')!=VERSION:
        raise ValueError('Original spacing accepts segmentation only; desired relation, thresholds and output actions are not inputs')
    if request.get('source_hash')!=state['source']['sha256'] or request.get('mask_origin')!='original_observed':
        raise ValueError('Bind unchanged original ownership masks, never candidate-derived geometry')
    sc._ref(task,state['source']);sc._original_view(task,state,request['source_view'])
    records=request.get('segmentation',[])
    if (len(records)!=2 or [r.get('role') for r in records]!=row['source_roles'] or
            any(not r.get('evidence') or type(r.get('uncertain')) is not bool for r in records)):
        raise ValueError('Each original role needs a segmentation protocol and explicit uncertainty')
    refs=request.get('masks',[])
    if len(refs)!=2:raise ValueError('Supply two full original-grid ownership masks')
    from PIL import Image
    masks=[];x,y,w,h=request['source_view']['roi']
    inside=np.zeros((state['source_size'][1],state['source_size'][0]),bool);inside[y:y+h,x:x+w]=True
    for ref in refs:
        if not ref.get('path','').replace('\\','/').startswith('source/'):
            raise ValueError('Original segmentation resources belong under source/')
        with Image.open(sc._ref(task,ref)) as image:
            if list(image.size)!=state['source_size']:raise ValueError('Original masks cannot be oversampled, resized or recropped')
            pixels=np.asarray(image.convert('L'))
        if not np.isin(pixels,[0,255]).all():raise ValueError('Freeze binary original ownership; do not threshold candidate alpha')
        mask=pixels==255
        if not mask.any() or (mask&~inside).any():raise ValueError('A nonempty original part mask must remain inside its exact raw-source view')
        masks.append(mask)
    measured=measure_masks(*masks,row['source_root_frame'],row['port'])
    if any(r['uncertain'] for r in records):
        measured.update(classification='ambiguous',status='ORIGINAL_SPACING_UNRESOLVED',reason='source_segmentation_uncertain')
        measured.pop('output_rule',None)
    return {'schema':VERSION,'source_hash':state['source']['sha256'],
        'binding':binding(row),'binding_key':key(row),'input':copy.deepcopy(request),
        'measurement':measured,'drawing_gain':False,
        'limits':'The program decides spacing from fixed original masks. Semantic ownership remains a source interpretation requiring independent source-quality review.'}


def original(task,state,row):
    embedded=row.get('original_spacing')
    if embedded:return classified(task,state,row,embedded)
    refs=_ledger_refs(task,state,row)
    if not refs:return None
    from .semantic_composition import _ref
    saved=read_json(_ref(task,refs[-1]))
    if binding(saved['binding'])!=binding(row) or saved['source_hash']!=state['source']['sha256']:
        raise ValueError('Original spacing is bound to a different root/role/port')
    return classified(task,state,row,saved['input'])


def prepare(task,state,row):
    calibration=original(task,state,row)
    if not calibration:return {'status':'ORIGINAL_SPACING_REQUIRED','passed':False,'values':{}},None
    measured=calibration['measurement']
    if measured['status']!='ORIGINAL_SPACING_CLASSIFIED':
        return {'status':measured['status'],'passed':False,'values':measured},None
    if row['relationship']!=measured['classification']:
        return {'status':'SOURCE_RELATION_DISAGREEMENT','passed':False,'values':measured},None
    result=copy.deepcopy(row);limits=result['limits'];rule=measured['output_rule']
    limits['distance_px']=[max(limits['distance_px'][0],rule['distance_px'][0]),min(limits['distance_px'][1],rule['distance_px'][1])]
    limits['solid_width_px']=max(limits.get('solid_width_px',0.),rule['solid_width_px'])
    if limits['distance_px'][1]<limits['distance_px'][0]:
        return {'status':'FROZEN_SOURCE_RULES_DISAGREE','passed':False,'values':measured},None
    return {'status':'ORIGINAL_SPACING_CLASSIFIED','passed':True,'values':measured},result


def evaluate(task,state,row,responses,nodes,parents,size):
    source,effective=prepare(task,state,row)
    if effective is None:return source
    from .semantic_interfaces import evaluate as actual_evaluate
    actual=actual_evaluate(effective,responses,nodes,parents,size)
    actual['values']['original_spacing']=source['values']
    return actual


def bind(task,state,request):
    entries=request.get('entries',[])
    if set(request)-{'entries'} or not 0<len(entries)<=16:
        raise ValueError('Use a bounded original-spacing packet with entries only')
    ledger=state.setdefault('source_spacing',{'schema':VERSION,'bindings':{},'history':[]})
    saved=[]
    for entry in entries:
        if set(entry)!={'target','original'}:raise ValueError('Bind a target and original segmentation, never an output operation')
        row=locate(task,state,entry['target']);result=classified(task,state,row,entry['original'])
        path=task/'source/spacing'/(identity(result)+'.json');write_json(path,result)
        ref={'path':path.relative_to(task).as_posix(),'sha256':digest(path)};prior=ledger['bindings'].get(key(row))
        if prior and prior!=ref:
            # An original interpretation can be corrected, but prior evidence
            # and all old output thresholds remain. This does not award gain.
            ledger['history'].append({'binding':key(row),'prior':prior,'new':ref,'drawing_gain':False})
        ledger['bindings'][key(row)]=ref
        saved.append({'target':entry['target'],'classification':result['measurement'],'ref':ref})
    return {'status':'ORIGINAL_SPACING_COMPUTED','entries':saved,'acceptance':False}


def bind_task(task,request):
    from . import agent_runtime as a
    task,state=a._state(task)
    with writer(task):
        result=bind(task,state,request)
        if (state.get('packet') or {}).get('kind')=='source_spacing_source':state['packet']=None
        state.pop('acceptance',None);a._save(task,state)
    return result


def report(task,state):
    rows=[]
    for target in targets(task,state):
        value,_=prepare(task,state,target['row'])
        rows.append({'target':target['target'],'binding_key':key(target['row']),**value})
    return {'schema':VERSION,'policy':POLICY,'items':rows,'passed':all(r['passed'] for r in rows)}


def packet(task,state):
    current=report(task,state);missing=[r for r in current['items'] if not r['passed']]
    if not missing:return None
    return {'kind':'source_spacing_source','source_image':state['source'],'policy':POLICY,
        'pairs':missing[:8],'remaining':len(missing),
        'required':'Segment original same-root roles on the unchanged source grid. The program computes distance intervals and contact/separation. Do not submit a desired relationship, tolerance or output translation. Ambiguous segmentation/threshold stays pending.',
        'submit':{'kind':'source_spacing_source','entries':[]}}
