"""Source-owned small-icon materials, proposed before a scoped actual draw.

The host locates the icon and optional continuous underlays. This operator does
not classify an arbitrary image, infer hidden scientific content or accept a
result. It reuses source_fit and the existing native protected commit.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from .common import safe_path,digest,identity,write_json,read_json
from .source_context import background


def propose(task,request):
    from .agent_runtime import _state
    task,state=_state(task);selected=state.get('selected')
    if not selected or selected['pptx']['sha256']!=request.get('baseline_hash'):
        raise ValueError('Bind an actually observed saved baseline')
    unit=state['quality']['units'][request['unit']]
    if unit['profile'] not in ('flat','structured','curve','three_dimensional'):
        raise ValueError('Locate a small semantic icon, not text/math/photography or an unidentified scene')
    if request.get('surfaces'):
        from .source_surfaces import propose as surface_proposal
        return surface_proposal(task,request)
    if unit['profile']=='three_dimensional':
        # A smooth lens/cap/shell is geometry, not many disconnected colours.
        # Return an executable planning transition, never a misleading method.
        return {'status':'RECURSIVE_NATIVE_SURFACE_PLAN_REQUIRED',
            'unit':unit['id'],'baseline_hash':selected['pptx']['sha256'],
            'source_hash':state['source']['sha256'],
            'next_action':'Observe and measure housing, lens, support and signals independently; submit their native preset/continuous-path/gradient method through the existing scoped repair packet.',
            'available_methods':['native preset ellipse/rect','continuous native cubic path','source-measured native gradients','source-bound SVG proposal with actual important-part benefit'],
            'source_requirements':[f['id'] for f in unit['features']],
            'limits':'Do not trace an entire smooth 3D icon as colour-cell patches. Original projection, semantic completeness, important-part targets and protected content remain mandatory.'}
    x,y,w,h=map(int,unit['roi'])
    if min(w,h)<6 or max(w,h)>400 or w*h>60000:
        raise ValueError('Recurse a large component into source-owned natural parts')
    if not unit['objects']:raise ValueError('Bind the independently movable semantic icon')
    scene=read_json(safe_path(task,selected['scene']['path']));objects={o['id']:o for o in scene['objects']}
    def owned(oid):
        while oid in objects:
            if oid in unit['objects']:return True
            oid=objects[oid].get('parent')
        return False
    if any(o['render_type'] in ('text','equation','connector','table') and owned(o['id']) for o in objects.values()):
        raise ValueError('Recurse artwork away from independent native text/math/scientific relations')
    rgb=np.asarray(Image.open(safe_path(task,state['source']['path'])).convert('RGB').crop((x,y,x+w,y+h)))
    descriptor=unit.get('reference_mask')
    if descriptor:
        # Reuse the independent original ownership oracle, never mask against
        # the candidate. This separates a car from a similarly coloured river
        # and allows existing source-constrained chassis-under-pane material.
        file=safe_path(task,descriptor['path'])
        if digest(file)!=descriptor['sha256']:raise ValueError('Frozen source ownership changed')
        fg=np.asarray(Image.open(file).convert('L'))>0
        if fg.shape!=(h,w):raise ValueError('Original ownership must use the fixed unit canvas')
        context={'status':'SOURCE_OWNED_FOREGROUND_DOMAIN','reference_mask':descriptor,
                 'source_hash':state['source']['sha256'],
                 'feature_ids':[f['id'] for f in unit['features']],
                 'limits':'Frozen original semantic ownership only; no candidate masking or global hole filling.'}
    else:
        context=background(task,state,unit['roi'])
        if context['status']!='SOURCE_CONTEXT_BACKGROUND':
            raise ValueError('Mixed source surroundings need an explicit frozen source-owned mask')
        bg=context['background_rgb']
        fg=np.linalg.norm(rgb.astype(float)-bg,axis=2)>=unit['protocol']['foreground_distance_rgb']*255
    if not fg.any():raise ValueError('No original source material; refine the source reading')
    mode=request.get('palette','interior_cells' if unit['profile'] in ('flat','structured','curve') and min(w,h)<50 else 'source_cells')
    count=request.get('colors',8 if mode=='interior_cells' else 22);underlays=request.get('underlays',[])
    if type(count) is not int or not 8<=count<=22 or len(underlays)>2:
        raise ValueError('Use a compact source palette and at most two explicitly observed continuous underlays')
    if count+max(1,len(underlays))>24:raise ValueError('Recurse named natural materials before exceeding source_fit bounds')
    dependencies={'source':state['source']['sha256'],'unit':identity({k:v for k,v in unit.items() if k not in ('status','built_fingerprint')}),
        'context':context,'request':request,'implementation':digest(Path(__file__))}
    folder=task/'scratch/source-material'/identity(dependencies)[:24];folder.mkdir(parents=True,exist_ok=True)
    saved=folder/'proposal.json'
    if saved.is_file():return read_json(saved)
    if mode in ('source_cells','interior_cells'):
        # Source RGB cells preserve the population of observed tones; median
        # cut can shift a whole pale material across a colour-bin boundary.
        data=rgb[fg];cells=data//32;keys,inverse,counts=np.unique(cells,axis=0,return_inverse=True,return_counts=True)
        if mode=='interior_cells':
            from scipy.ndimage import binary_erosion
            # Edge AA is evidence of a boundary, not a new opaque material.
            # Preserve dominant original interior shades before fitting clear
            # continuous parts, instead of recreating blurred edge mottling.
            interior=binary_erosion(fg)
            sample=rgb[interior] if interior.sum()>=12 else data
            ikeys,icounts=np.unique(sample//32,axis=0,return_counts=True)
            population={tuple(k):int(n) for k,n in zip(ikeys,icounts)}
            chosen=sorted(range(len(keys)),key=lambda k:(-population.get(tuple(keys[k]),0),-int(counts[k]),k))[:count]
        else:chosen=np.argsort(-counts,kind='stable')[:count]
        palette=np.array([np.median(data[inverse==k],axis=0) for k in chosen]).astype('uint8')
        bycell={int(k):i for i,k in enumerate(chosen)};mapping=[]
        for k in range(len(keys)):
            center=np.median(data[inverse==k],axis=0)
            mapping.append(bycell.get(k,int(np.linalg.norm(palette.astype(float)-center,axis=1).argmin())))
        labels=np.full((h,w),-1,int);labels[fg]=np.array(mapping)[inverse]
    elif mode=='median_cut':
        sample=Image.fromarray(rgb).quantize(colors=count,method=Image.Quantize.MEDIANCUT)
        labels=np.asarray(sample);palette=np.asarray(sample.getpalette(),int).reshape(-1,3)
    else:raise ValueError('Unknown source-only palette method')
    layers=[]
    def layer(role,mask,color,evidence):
        if not mask.any():raise ValueError('Empty declared continuous material '+role)
        file=folder/(role+'.png');Image.fromarray(mask.astype('uint8')*255).save(file)
        return {'part_id':role,'roi':unit['roi'],'semantic_class':'source_owned_icon_material',
            'evidence':evidence,'colors_rgb':[list(map(int,color))],'fill':''.join(format(int(v),'02X') for v in color),
            'mask':{'path':file.relative_to(task).as_posix(),'sha256':digest(file)},
            'smooth_px':.45 if mode=='interior_cells' else .20,
            'epsilon_px':.20 if mode=='interior_cells' else .10,'smooth_curves':True,
            'curve_tension':.06 if mode=='interior_cells' else .03,'minimum_area_px':.5}
    if underlays:
        for item in underlays:
            if not item.get('part') or not item.get('evidence'):raise ValueError('Name and explain the observed continuous material')
            file=safe_path(task,item['mask']['path'])
            if digest(file)!=item['mask']['sha256']:raise ValueError('Source material support changed')
            mask=np.asarray(Image.open(file).convert('L'))>0
            if mask.shape!=(h,w) or np.any(mask & ~fg):raise ValueError('Underlay cannot fill unsupported natural negative space')
            layers.append(layer(item['part']+'_underlay',mask,np.median(rgb[mask],axis=0),item['evidence']))
    else:
        layers.append(layer('continuous_material_underlay',fg,np.median(rgb[fg],axis=0),
            'The original foreground is opaque at these source-supported pixels. Exterior gaps stay open; no global hole filling or hidden-content inference.'))
    for index in sorted(np.unique(labels[fg]),key=lambda i:int(palette[i].sum()),reverse=True):
        layers.append(layer('shade_'+str(index),(labels==index)&fg,palette[index],
            'Original observed material shade inside '+unit['id']+'; preserve its source projection and independently owned foreground.'))
    result={'status':'SOURCE_MATERIAL_PROPOSAL_REQUIRES_SCOPED_DRAW_AND_ACTUAL_OBSERVATION','unit':unit['id'],
        'baseline_hash':selected['pptx']['sha256'],'source_hash':state['source']['sha256'],'background_evidence':context,
        'method':{'source_fit':{'source_hash':state['source']['sha256'],'layers':layers}},
        'limits':'No quality acceptance, generic subtype substitution or silent amodal/HD claim. Native text/math/relations and non-target parts remain protected.'}
    write_json(saved,result);return result
