"""Original-only visual catalog comparison and program-owned instance debt.

The host identifies meaning. Programs render the shipped geometry, freeze each
located interpretation and require its own constructed root. A nearby caption
or a later renamed native class cannot erase an observed assembly.
"""
import copy,math,re
from .common import ROOT,read_json,write_json,digest,identity,safe_path
from .source_contract import fields,finite

VERSION='source-catalog-review-1'

def _catalog():
    value=read_json(ROOT/'config/natural-components.json')
    for row in value['items']:
        if digest(safe_path(ROOT,row['path']))!=row['sha256']:
            raise ValueError('Public construction catalog geometry changed: '+row['id'])
    return value

def _svg(model):
    from .semantic_icons import construct,bake_pose,native_ink_samples
    from .geometry import path_operations
    elements=['<svg xmlns="http://www.w3.org/2000/svg" width="480" height="240" viewBox="0 0 480 240"><rect width="480" height="240" fill="white"/>']
    for column,degrees in enumerate((0,90)):
        nodes=bake_pose(construct({'model':model}),degrees)
        ink=native_ink_samples(nodes);xs=[p[0] for p in ink];ys=[p[1] for p in ink]
        x,y,w,h=min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)
        scale=min(200/w,200/h);tx=column*240+120-scale*(x+w/2);ty=120-scale*(y+h/2)
        elements.append(f'<g transform="translate({tx} {ty}) scale({scale})">')
        for obj in nodes[1:]:
            bx,by,bw,bh=obj['bbox'];style=obj['style'];content=obj['content']
            rotation=style.get('rotation',0)
            attr=(f'fill="#{style["fill"]}"' if style.get('fill') else 'fill="none"')+' '+(f'stroke="#{style["stroke"]}"' if style.get('stroke') else 'stroke="none"')
            attr+=f' stroke-width="{style.get("line_width",0)*96/72}" stroke-linejoin="round" stroke-linecap="round" transform="rotate({rotation} {bx+bw/2} {by+bh/2})"'
            if obj['render_type']=='shape':
                if content['preset']=='ellipse':elements.append(f'<ellipse cx="{bx+bw/2}" cy="{by+bh/2}" rx="{bw/2}" ry="{bh/2}" {attr}/>')
                else:
                    radius=min(bw,bh)*(content.get('adjustments') or [0])[0]
                    elements.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="{radius}" {attr}/>')
            elif obj['render_type']=='path':
                operations=[];letters={'moveTo':'M','lnTo':'L','cubicBezTo':'C','quadBezTo':'Q','close':'Z'}
                for contour in content['contours']:
                    for op,points in path_operations(contour):
                        operations.append(letters[op]+' '.join(str(v) for p in points for v in (bx+p[0]*bw,by+p[1]*bh)))
                elements.append('<path d="'+' '.join(operations)+'" '+attr+'/>')
            else:raise ValueError('Catalog preview requires supported native geometry')
        elements.append('</g>')
    return (''.join(elements)+'</svg>').encode('utf-8')

def guide(task,state):
    catalog=_catalog()
    if not catalog['items']:return None
    from .svg_backend import svg2png
    items=[]
    folder=task/'source/catalog';folder.mkdir(parents=True,exist_ok=True)
    for row in catalog['items']:
        model=read_json(safe_path(ROOT,row['path']));data=_svg(model)
        key=identity({'geometry':row['sha256'],'renderer':digest(__file__)})
        svg=folder/(key+'.svg');png=folder/(key+'.png')
        if not svg.exists():svg.write_bytes(data)
        if svg.read_bytes()!=data:raise ValueError('Catalog inspection geometry changed')
        pixels=svg2png(data,output_width=480,output_height=240,mode='portable')
        if not png.exists():png.write_bytes(pixels)
        if png.read_bytes()!=pixels:raise ValueError('Catalog inspection preview changed')
        items.append({'catalog_id':row['id'],'family':row['family'],'roles':row['roles'],'properties':row['properties'],
            'model_sha256':row['sha256'],'preview':{'path':png.relative_to(task).as_posix(),'sha256':digest(png)},
            'preview_meaning':'Program-rendered public construction reference at two poses; no previous task, original annotation or accepted drawing.'})
    return {'schema':VERSION,'catalog_hash':identity(catalog),'source_hash':state['source']['sha256'],'items':items,
        'instruction':'Open each preview and compare visible anatomy against the whole raw original and enlarged small assemblies. Treat repeated and legend instances separately. A nearby label is context; observed contours, windows, appendages and pose decide compatibility. A catalog match is conditional, never a forced class for photographs or incompatible views.',
        'return':'analysis.catalog_review{source_hash,catalog_hash,decisions[{catalog_id,status:present|absent|uncertain,evidence,anatomy:role_counts_if_present,instances[{id,source_roi,source_note,pose_degrees?,purpose?,palette?,source_anchor?,source_container?}]}]}; each present instance id must occur as its own component.parts entry under exactly one enclosing component. Use its current source_traits in recursive children or recipe_instances. Do not collapse multiple instances into one part.'}

def compile_review(state,review,components):
    catalog=_catalog()
    if not catalog['items'] and review is None:
        review={'source_hash':state['source']['sha256'],'catalog_hash':identity(catalog),'decisions':[]}
    fields(review,{'source_hash','catalog_hash','decisions'},'analysis.catalog_review')
    if review.get('source_hash')!=state['source']['sha256'] or review.get('catalog_hash')!=identity(catalog):
        raise ValueError('Catalog review must bind the current raw original and public catalog')
    decisions=review.get('decisions');rows={r['id']:r for r in catalog['items']}
    if (not isinstance(decisions,list) or any(not isinstance(d,dict) for d in decisions)
            or len(decisions)!=len(rows) or {d.get('catalog_id') for d in decisions}!=set(rows)):
        raise ValueError('An original visual decision is required for each public catalog item')
    instances=[];ids=set();width,height=state['source_size']
    for decision in decisions:
        fields(decision,{'catalog_id','status','evidence','anatomy','instances'},'catalog_decision')
        row=rows[decision['catalog_id']];status=decision.get('status');parts=decision.get('instances')
        if status=='uncertain':raise ValueError('unresolved catalog anatomy requires original inspection before construction')
        if status not in ('present','absent') or not isinstance(decision.get('evidence'),str) or not decision['evidence'].strip() or not isinstance(parts,list):
            raise ValueError('Typed original visual evidence and present/absent catalog decision required')
        if (status=='absent' and parts) or (status=='present' and not parts):raise ValueError('Catalog status and located instances disagree')
        if status=='present' and decision.get('anatomy')!=row['roles']:raise ValueError('Observed role anatomy must match the proposed catalog family')
        for item in parts:
            fields(item,{'id','source_roi','source_note','pose_degrees','purpose','palette','source_anchor','source_container'},'catalog_instance')
            name=item.get('id');roi=item.get('source_roi')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*',name) or name in ids:raise ValueError('Distinct portable catalog instance ids required')
            if (not isinstance(roi,list) or len(roi)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in roi)
                    or min(roi[:2])<0 or min(roi[2:])<=0 or roi[0]+roi[2]>width+.001 or roi[1]+roi[3]>height+.001):
                raise ValueError('Catalog instance needs a finite located original ROI')
            if not isinstance(item.get('source_note'),str) or not item['source_note'].strip():raise ValueError('Each original instance needs observed anatomy evidence')
            pose=item.get('pose_degrees',0)
            if type(pose) not in (int,float) or not math.isfinite(pose):raise ValueError('Finite source pose required')
            enclosing=[c for c in components if name in c.get('parts',[]) and roi[0]>=c['roi'][0]-.001 and roi[1]>=c['roi'][1]-.001
                and roi[0]+roi[2]<=c['roi'][0]+c['roi'][2]+.001 and roi[1]+roi[3]<=c['roi'][1]+c['roi'][3]+.001]
            if len(enclosing)!=1:raise ValueError('Each catalog instance '+name+' needs a separate source part under exactly one enclosing owner')
            purpose=item.get('purpose','illustrative')
            if purpose not in row['purpose']:raise ValueError('Catalog purpose is incompatible with original identity requirements')
            traits={'source_hash':state['source']['sha256'],'source_roi':copy.deepcopy(roi),'source_instance_id':name,
                'evidence':item['source_note'],'status':'inferred','family':row['family'],'roles':copy.deepcopy(row['roles']),
                'purpose':purpose,**{k:v for k,v in row['properties'].items() if k!='construction'}}
            if 'palette' in item:traits['palette']=copy.deepcopy(item['palette'])
            from .natural_catalog import parameters
            params={'source_traits':traits,'pose_degrees':pose}
            parameters(params)
            for field in ('source_anchor','source_container'):
                if field in item:params[field]=copy.deepcopy(item[field])
            ids.add(name);instances.append({'id':name,'owner':enclosing[0]['id'],'catalog_id':row['id'],'model_sha256':row['sha256'],
                'source_traits':traits,'method':{'recipe':row['recipe'],'parameters':params}})
    return {'schema':VERSION,'source_hash':review['source_hash'],'catalog_hash':review['catalog_hash'],
        'decisions':copy.deepcopy(decisions),'instances':instances}

def bind(task,state,compiled):
    file=task/'source/catalog'/('review-'+identity(compiled)+'.json');write_json(file,compiled)
    state['source_catalog']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    state['source_catalog_data']=copy.deepcopy(compiled)

def activate(task,state):
    write_json(task/'source/catalog/Activation.json',{'schema':VERSION,'source_hash':state['source']['sha256'],
        'catalog_hash':identity(_catalog()),'required':'Original-only visual decisions and one constructed root per compatible located instance'})

def verify_frozen(task,state):
    activation=task/'source/catalog/Activation.json'
    if activation.exists():
        active=read_json(activation)
        if (state.get('objectives',{}).get('source_catalog_review') is not True or active['source_hash']!=state['source']['sha256']
                or active['catalog_hash']!=identity(_catalog())):raise ValueError('Activated original visual catalog review cannot be disabled or rebound')
    ref=state.get('source_catalog')
    if not ref:
        if state.get('analysis') is not None and state.get('objectives',{}).get('source_catalog_review') and not state.get('native_import'):
            raise ValueError('Original visual catalog review is missing')
        return
    file=safe_path(task,ref['path']);value=read_json(file)
    if (digest(file)!=ref['sha256'] or identity(value)!=identity(state.get('source_catalog_data'))
            or value['source_hash']!=state['source']['sha256'] or value['catalog_hash']!=identity(_catalog())):
        raise ValueError('Frozen original catalog interpretation changed')

def verify_constructed(state,owner,objects):
    expected=[r for r in state.get('source_catalog_data',{}).get('instances',[]) if r['owner']==owner]
    roots=[o for o in objects if o.get('content',{}).get('natural_icon')];items=[]
    for required in expected:
        found=[]
        for obj in roots:
            marker=obj['content']['natural_icon'];evidence=marker.get('source_evidence',{});current=evidence.get('current_source',{})
            if current.get('source_instance_id')==required['id'] and current.get('source_hash')==required['source_traits']['source_hash']:
                found.append(obj)
        valid=len(found)==1 and found[0]['content']['natural_icon']['source_evidence'].get('catalog_id')==required['catalog_id']
        valid=valid and found[0]['content']['natural_icon']['source_evidence'].get('catalog_sha256')==required['model_sha256']
        valid=valid and found[0]['content']['natural_icon']['source_evidence']['current_source']==required['source_traits']
        items.append({'source_instance':required['id'],'constructed_roots':[o['id'] for o in found],'passed':bool(valid)})
        if not valid:raise ValueError('Original catalog instance '+required['id']+' requires exactly one current-source compatible natural root; a renamed raw device or combined group cannot replace it')
    return {'passed':True,'required_instances':len(expected),'items':items}
