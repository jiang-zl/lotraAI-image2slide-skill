"""Fixed-frame correspondence and approved-appearance measurements.

These are explicit engineering proxies, not a learned universal beauty oracle.
No alignment, blur matching, source mutation or candidate-based crop search.
"""
import copy,math,posixpath
from pathlib import Path
import numpy as np
from .common import digest,identity,safe_path

def native_signatures(file,sha256):
    from lxml import etree as E
    from .resource_facts import derived_value
    return derived_value(file,sha256,{'native_signatures':digest(__file__),'lxml':E.LXML_VERSION},
                         lambda: _native_signatures(file,sha256))

def _native_signatures(file,sha256):
    from lxml import etree as E
    from .inspect import xml,inventory
    from .mathml import NS
    if digest(file)!=sha256:raise ValueError('Native signature input changed')
    nodes,duplicates=inventory(xml(file))
    if duplicates:raise ValueError('Ambiguous native identity')
    result={}
    from .resource_facts import package_read,xml_part
    with package_read(file,sha256) as z:
        rels={r.get('Id'):posixpath.normpath(posixpath.join('ppt/slides',r.get('Target','')))
              for r in xml_part(file,'ppt/slides/_rels/slide1.xml.rels',sha256) if r.get('TargetMode')!='External'}
        for name,record in nodes.items():
            node=copy.deepcopy(record['node']);parent=record.get('parent');ancestors=[]
            if E.QName(node).localname=='grpSp':
                # Every descendant has its own policy. Parent signatures bind
                # the parent's native properties, without granting a text edit
                # permission over every sibling in the containing group.
                # Office can wrap mathematical children in AlternateContent.
                # Their own policies cover both native branches; retaining a
                # wrapped child here would wrongly ascribe its edit to the
                # parent's own properties.
                for child in list(node.iterdescendants()):
                    if E.QName(child).namespace==NS['p'] and E.QName(child).localname in ('sp','grpSp','pic','cxnSp','graphicFrame'):
                        child.getparent().remove(child)
            while parent:
                group=nodes[parent];props=group['node'].find('p:grpSpPr',NS)
                ancestors.append(E.tostring(props,method='c14n',exclusive=True).decode() if props is not None else '')
                parent=group.get('parent')
            resources=[]
            for elem in node.iter():
                rid=elem.get('{'+NS['r']+'}embed')
                if rid and rid in rels and rels[rid] in z.namelist():
                    import hashlib
                    resources.append(hashlib.sha256(z.read(rels[rid])).hexdigest())
            # Rendering properties and owned vector assets are fixed. All
            # descendants are independently covered; ZIP timestamps irrelevant.
            result[name]=identity({'native':E.tostring(node,method='c14n',exclusive=True).decode(),
                'ancestors':ancestors,'media':resources})
    return result

def canvas(file,sha256,size):
    from PIL import Image
    from .resource_facts import image_dimensions,image_region
    if digest(file)!=sha256:raise ValueError('Appearance image changed')
    operations=[] if image_dimensions(file,sha256)==tuple(size) else [('resize',size,Image.Resampling.LANCZOS)]
    with image_region(file,operations,sha256,mode='RGB_WHITE') as image:
        return np.asarray(image,dtype=np.float32)/255.

def image_values(first,second,requested=None):
    from skimage.metrics import structural_similarity
    from scipy.ndimage import gaussian_filter,laplace,binary_erosion,distance_transform_edt
    if first.shape!=second.shape:raise ValueError('Appearance frames must share a fixed canvas')
    all_metrics={'ssim','boundary_f1','clarity_first','clarity_second','clarity_ratio','color_histogram_tv','raw_hard_color_histogram_tv','mean_absolute_rgb_error'}
    wanted=all_metrics if requested is None else set(requested)&all_metrics
    values={}
    if 'ssim' in wanted:
        minimum=min(first.shape[:2]);win=min(7,minimum if minimum%2 else minimum-1)
        ssim=float(structural_similarity(first,second,data_range=1.,channel_axis=2,win_size=win)) if win>=3 else None
        values.update(ssim=ssim,ssim_applicability='measured' if ssim is not None else 'too_few_pixels_native_construction_remains_required')
    def gray(data):return data@np.array([.2126,.7152,.0722])
    ga,gb=map(gray,(first,second)) if wanted&{'boundary_f1','clarity_first','clarity_second','clarity_ratio'} else (None,None)
    def edges(data):
        # Fixed operator/threshold across source/baseline/candidate.
        dx=gaussian_filter(data,.6,order=(0,1));dy=gaussian_filter(data,.6,order=(1,0))
        return np.hypot(dx,dy)>.06
    if 'boundary_f1' in wanted:
        ea,eb=edges(ga),edges(gb)
        if ea.any() and eb.any():
            precision=float((distance_transform_edt(~ea)[eb]<=1).mean())
            recall=float((distance_transform_edt(~eb)[ea]<=1).mean())
            boundary=2*precision*recall/max(precision+recall,1e-12)
        else:boundary=float(not ea.any() and not eb.any())
        values['boundary_f1']=boundary
    def clarity(g):return float(np.mean(laplace(gaussian_filter(g,.35))**2))
    if wanted&{'clarity_first','clarity_second','clarity_ratio'}:
        ca,cb=clarity(ga),clarity(gb)
        group={'clarity_first':ca,'clarity_second':cb,'clarity_ratio':cb/ca if ca>1e-12 else (1. if cb<=1e-12 else None)}
        values.update({k:v for k,v in group.items() if k in wanted})
    from .typed_metrics import color_histogram
    def distance(mode):
        hist=[]
        for data in (first,second):
            h=color_histogram(data.reshape(-1,3),8,mode)
            hist.append(h/max(1,h.sum()))
        return float(np.abs(hist[0]-hist[1]).sum()/2)
    for key,mode in (('color_histogram_tv','trilinear'),('raw_hard_color_histogram_tv','hard')):
        if key in wanted:values[key]=distance(mode)
    if wanted&{'color_histogram_tv','raw_hard_color_histogram_tv'}:
        values['color_protocol']={'version':'fixed-color-2','bins':8,'membership':'trilinear','domain':'unchanged full fixed frame'}
    if 'mean_absolute_rgb_error' in wanted:values['mean_absolute_rgb_error']=float(np.abs(first-second).mean())
    return values

def rank(values,weights):
    present={k:v for k,v in values.items() if v is not None}
    if set(weights)-set(present):return None
    if any(not math.isfinite(v) for v in present.values()):raise ValueError('Nonfinite visual measurement')
    return sum(weights[k]*max(0.,min(1.,present[k])) for k in weights)

def measure(task,state,candidate,item,plan,context=None):
    from .native_core import appearance
    native=appearance(task,state,candidate,item)
    if native is not None:return native
    size=tuple(state['source_size']);source=state['source'];approved=plan.get('approved')
    x,y,w,h=item['roi'];box=(max(0,math.floor(x)),max(0,math.floor(y)),min(size[0],math.ceil(x+w)),min(size[1],math.ceil(y+h)))
    if box[2]<=box[0] or box[3]<=box[1]:raise ValueError('Empty fixed semantic appearance window')
    def crop(ref):
        from PIL import Image
        from .resource_facts import image_dimensions,image_region
        path=safe_path(task,ref['path'])
        operations=[] if image_dimensions(path,ref['sha256'])==size else [('resize',size,Image.Resampling.LANCZOS)]
        operations.append(('crop',box))
        with image_region(path,operations,ref['sha256'],mode='RGB_WHITE') as image:
            return np.asarray(image,dtype=np.float32)/255.
    original=crop(source);actual=crop(candidate['preview']);correspondence=image_values(original,actual)
    result={'source_correspondence':correspondence,'fixed_source_roi':list(box),'passed':True,
        'target':item['appearance_target'],'constraints':[]}
    current=native_signatures(str(safe_path(task,candidate['pptx']['path'])),candidate['pptx']['sha256'])
    names=item['objects'];context=context or {};construction=float(context['native_inventory']) if 'native_inventory' in context else None;style=None;clarity=None
    if approved:
        appearance=image_values(crop(approved['preview']),actual)
        baseline=native_signatures(str(safe_path(task,approved['pptx']['path'])),approved['pptx']['sha256'])
        changed=[n for n in names if current.get(n)!=baseline.get(n)];construction=float(not changed)
        if item['appearance_target']=='source_content':
            from .source_text_actions import guard
            proof=guard(task,state,candidate,item,approved);result['source_content_revision']=proof
            construction=float(proof['passed'])
        elif changed:
            from .source_text_actions import guard
            from .source_layout_actions import guard as layout_guard
            protection=context.get('approved_source_correction_protection',{})
            layout_proof=protection.get('constructor') if protection.get('applicable') else None
            if layout_proof is None:layout_proof=layout_guard(task,state,candidate,approved)
            layout_names=set(layout_proof['objects']) if layout_proof['passed'] else set()
            result['source_layout_revision']=layout_proof
            corrections={n:r for r in plan['items'] if r['appearance_target']=='source_content' for n in r['objects']}
            retained=[];resolved=[]
            for name in changed:
                policy=corrections.get(name)
                if policy and guard(task,state,candidate,policy,approved)['passed']:resolved.append(name)
                elif name in layout_names:resolved.append(name)
                else:retained.append(name)
            result['independently_verified_source_text_corrections']=resolved
            construction=float(not retained);changed=retained
        result['approved_appearance']=appearance;result['changed_native_owners']=changed
        ratio=appearance['clarity_ratio'];low,high=plan['profile_configuration']['appearance_tolerances']['clarity_ratio']
        clarity=1. if ratio is not None and low<=ratio<=high else (min(ratio/low,high/ratio) if ratio is not None and ratio>0 else 0.)
        style=appearance['ssim'] if appearance['ssim'] is not None else float(not changed)
        if item['appearance_target'] in ('approved','baseline','source_content'):
            checks=[('approved_native_properties',construction==1.),('actual_size_clarity',ratio is not None and low<=ratio<=high),
                ('approved_render_style',style>=plan['profile_configuration']['appearance_tolerances']['approved_style_ssim_min'])]
            if item['appearance_target']=='source_content':
                # A correct replacement glyph necessarily differs from the
                # old wrong glyph. Exact source text/script construction,
                # retained frame/fonts and actual nonempty ink are the gates;
                # old-glyph SSIM/energy remain reported diagnostics.
                checks=[('source_confirmed_native_text_and_protected_properties',construction==1.),
                        ('actual_nonempty_rendered_ink',appearance['clarity_second']>1e-12)]
            elif result.get('source_layout_revision',{}).get('passed') and set(names)&set(result['source_layout_revision']['objects']):
                # A frozen source-position repair changes fixed-ROI SSIM by
                # design. Keep that numeric observation, while the exact
                # constructor protects every painted/font/content property.
                # No registration or replacement beauty score is performed.
                checks=[('source_constructor_and_protected_properties',construction==1.),
                        ('every_actual_source_layout_relation',context.get('layout_integrity')==1.),
                        ('actual_nonempty_rendered_ink',appearance['clarity_second']>1e-12)]
            elif item['appearance_target'] in ('approved','baseline') and context.get('approved_source_correction_protection',{}).get('passed'):
                # Unchanged owners can share a fixed ROI with a corrected
                # neighbour. Preserve raw scores; complete native construction
                # and actual exterior pixels establish retained context.
                protection=context['approved_source_correction_protection']
                result['approved_context_render_protection']={k:protection[k] for k in ('method','passed','native_objects','changed_pixels_outside_program_owned_frames','edge_margin_source_px')}
                checks=[('protected_native_properties',construction==1.),
                        ('every_actual_source_layout_relation',context.get('layout_integrity')==1.),
                        ('actual_context_pixels_preserved',protection['passed'])]
            result['constraints']=[{'id':k,'passed':bool(v)} for k,v in checks]
            result['passed']=all(v for _,v in checks)
    if item['appearance_target']=='source':
        constraints=item.get('source_constraints',[])
        if not constraints:raise ValueError('Source-fidelity purpose requires explicit fixed correspondence bounds')
        for rule in constraints:
            value=correspondence.get(rule['id']);passed=value is not None and (rule.get('min') is None or value>=rule['min']) and (rule.get('max') is None or value<=rule['max'])
            result['constraints'].append({**rule,'value':value,'passed':passed});result['passed']&=passed
    if item['appearance_target']=='design':
        # A new design is measured against explicit construction/appearance
        # bounds supplied before the candidate; unsupported metrics block.
        bounds=item['design_contract'].get('constraints',[])
        if not bounds:raise ValueError('Design constraints are empty')
        for rule in bounds:
            value=correspondence.get(rule['id'])
            passed=value is not None and (rule.get('min') is None or value>=rule['min']) and (rule.get('max') is None or value<=rule['max'])
            result['constraints'].append({**rule,'value':value,'passed':passed});result['passed']&=passed
    if not approved:
        # A first reconstruction has no historical approved icon. Its clarity
        # interval is declared before drawing, rather than invented from the
        # candidate or silently borrowed from a blurred source.
        band=item.get('design_contract',{}).get('clarity_band')
        if band:
            value=correspondence['clarity_second'];low,high=band
            clarity=1. if low<=value<=high else min(value/low,high/value) if value>0 else 0.
            result['constraints'].append({'id':'declared_actual_size_clarity_band','value':value,'min':low,'max':high,'passed':low<=value<=high})
            result['passed']&=low<=value<=high
        style=1.-correspondence['color_histogram_tv']
    content_rows=[r for r in context.get('content',[]) if r['unit'] in item.get('quality_units',[])]
    content_fidelity=float(all(r['passed'] for r in content_rows)) if content_rows else None
    ratio=correspondence['clarity_ratio']
    texture=math.exp(-abs(math.log(ratio))) if ratio is not None and ratio>0 else float(ratio==1.)
    scores={'source_ssim':correspondence['ssim'],'source_boundary':correspondence['boundary_f1'],
            'approved_clarity':clarity,'approved_style':style,'native_construction':construction,
            'source_color':1.-correspondence['color_histogram_tv'],'source_texture':texture,
            'content_fidelity':content_fidelity,'layout_integrity':context.get('layout_integrity'),
            'relation_integrity':context.get('relation_integrity')}
    result['score_dimensions']=scores;result['weighted_score']=rank(scores,item['weights'])
    result['selected_dimensions']=list(item['weights']);result['weighted_score_status']='MEASURED' if result['weighted_score'] is not None else 'NOT_APPLICABLE_OR_REQUIRED_CONTEXT_MISSING'
    result['limits']='Fixed-frame proxies and approved-design preservation; not a universal beauty score. Tiny inapplicable SSIM is never replaced with a fabricated value.'
    return result
