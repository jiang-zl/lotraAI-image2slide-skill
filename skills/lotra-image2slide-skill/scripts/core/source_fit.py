"""Fit declared, source-isolated flat layers to compact editable native paths.

The agent identifies the semantic part, palette, occluders and inference.
The program extracts its geometry and preserves a single continuous contour.
This route is not permitted to vectorize an unidentified whole scene.
"""
import math
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage.measure import find_contours, approximate_polygon
from .common import digest, safe_path
from .recipes import node


def construct(task, state, component, specification):
    if specification.get('source_hash') != state['source']['sha256']:
        raise ValueError('Source fitting must bind the original')
    layers = specification.get('layers', [])
    if not 1 <= len(layers) <= 24:
        raise ValueError('Fit bounded natural flat layers, not an unidentified whole image')
    source = np.asarray(Image.open(safe_path(task,state['source']['path'])).convert('RGB'),float)
    cid = component['id']
    out = [node(cid,'group',component['roi'],semantic=component['semantic_class'])]
    for layer in layers:
        if not layer.get('part_id') or not layer.get('semantic_class') or not layer.get('evidence'):
            raise ValueError('Layer needs its own natural meaning and source evidence')
        x,y,w,h = map(int,layer['roi'])
        if min(x,y)<0 or min(w,h)<=0 or x+w>source.shape[1] or y+h>source.shape[0]:
            raise ValueError('Fit ROI is outside the source')
        tolerance=layer.get('color_tolerance',25)
        colors=np.asarray(layer['colors_rgb'],float)
        if colors.ndim!=2 or colors.shape[1]!=3 or not 1<=len(colors)<=12:
            raise ValueError('Declare a small observed layer palette')
        if not 0<tolerance<=100:
            raise ValueError('Color isolation tolerance must be bounded')
        roi=source[y:y+h,x:x+w]
        foreground_distance=np.min(np.linalg.norm(roi[...,None,:]-colors,axis=3),axis=2)
        observed=foreground_distance<=tolerance
        backgrounds=layer.get('background_colors_rgb')
        if backgrounds is not None:
            backgrounds=np.asarray(backgrounds,dtype=float)
            margin=float(layer.get('foreground_margin_rgb_255',0))
            if (backgrounds.ndim!=2 or backgrounds.shape[1]!=3 or not len(backgrounds)
                    or not np.isfinite(backgrounds).all() or np.any((backgrounds<0)|(backgrounds>255))
                    or not np.isfinite(margin) or not 0<=margin<=32):
                raise ValueError('Contrastive fitting needs independently observed source-background colours')
            background_distance=np.min(np.linalg.norm(roi[...,None,:]-backgrounds,axis=3),axis=2)
            observed &= foreground_distance+margin<background_distance
        # Source-observed channel bounds distinguish equally coloured neighbours
        # such as a dark teal device and a lighter teal river. Not output masks.
        if layer.get('channel_bounds'):
            for channel,bounds in layer['channel_bounds'].items():
                index={'r':0,'g':1,'b':2}[channel];lo,hi=bounds
                if not 0<=lo<=hi<=255:raise ValueError('Bounded original colour channels')
                observed &= (roi[...,index]>=lo)&(roi[...,index]<=hi)
        for descriptor in layer.get('exclude_source_masks',[]):
            excluded=safe_path(task,descriptor['path'])
            if digest(excluded)!=descriptor['sha256']:raise ValueError('Source exclusion changed')
            excluded_mask=np.asarray(Image.open(excluded).convert('L'))>0
            if excluded_mask.shape!=observed.shape:raise ValueError('Source exclusion shares the fixed ROI')
            observed &= ~excluded_mask
        if layer.get('mask'):
            path=safe_path(task,layer['mask']['path'])
            if digest(path)!=layer['mask']['sha256']:
                raise ValueError('Source layer mask changed')
            observed=np.asarray(Image.open(path).convert('L'))>0
            if observed.shape!=(h,w):
                raise ValueError('Layer mask must match its fixed ROI')
        labels,count=ndi.label(observed)
        if layer.get('seed'):
            px,py=layer['seed'];label=labels[py-y,px-x]
            if not label:raise ValueError('Source seed does not lie in the declared color layer')
            observed=labels==label
        else:
            areas=np.bincount(labels.ravel())
            observed &= areas[labels]>=layer.get('minimum_area_px',2)
        if layer.get('primitive_family')=='native_flat_mark':
            if backgrounds is None or len(backgrounds)!=1 or len(colors)!=1:
                raise ValueError('One original small mark and uniform ground are required')
            from .source_preset_fit import fit_flat_mark
            from .native_source_units import points_per_source_pixel,planned_points_per_source_pixel
            from .common import identity,write_json
            fitted=fit_flat_mark(roi,observed,colors[0],backgrounds[0],layer.get('family_evidence',{}))
            style=fitted['style'];width=style.pop('source_line_width',None)
            if width is not None:
                ratio=points_per_source_pixel(task,state,state['selected']) if state.get('selected') else planned_points_per_source_pixel(state)
                style['line_width']=width*ratio
                fitted['audit']['native_style_calibration']={'source_width_px':width,'points_per_source_pixel':ratio,'native_width_points':width*ratio}
            audit=fitted['audit'];audit.update(source_hash=state['source']['sha256'],roi=layer['roi'],owner=cid,part=layer['part_id'])
            write_json(Path(task)/'scratch'/('source-native-mark-'+identity(audit)[:20]+'.json'),audit)
            bx,by,bw,bh=fitted['bbox_local']
            out.append(node(cid+'__'+layer['part_id'],fitted['render_type'],[x+bx,y+by,bw,bh],fitted['content'],cid,layer['semantic_class'],**style))
            out[-1]['evidence_status']='observed'
            continue
        if layer.get('primitive_family')=='native_hollow_right_arrow':
            if backgrounds is None or len(backgrounds)!=1 or len(colors)!=1:
                raise ValueError('One observed arrow ink and its uniform original ground are required')
            from .source_preset_fit import fit_hollow_right_arrow
            from .common import identity,write_json
            fitted=fit_hollow_right_arrow(roi,observed,colors[0],backgrounds[0],layer.get('family_evidence',{}))
            from .native_source_units import points_per_source_pixel,planned_points_per_source_pixel
            ratio=(points_per_source_pixel(task,state,state['selected']) if state.get('selected')
                   else planned_points_per_source_pixel(state))
            fitted['audit']['native_style_calibration']={'source_width_px':fitted['line_width'],
                'points_per_source_pixel':ratio,'native_width_points':fitted['line_width']*ratio,
                'basis':'Exact saved native canvas' if state.get('selected') else 'Explicit planned native canvas with builder rounding'}
            audit=fitted['audit'];audit.update(source_hash=state['source']['sha256'],roi=layer['roi'],owner=cid,part=layer['part_id'])
            write_json(Path(task)/'scratch'/('source-native-arrow-'+identity(audit)[:20]+'.json'),audit)
            bx,by,bw,bh=fitted['bbox_local']
            out.append(node(cid+'__'+layer['part_id'],'shape',[x+bx,y+by,bw,bh],
                {'preset':'rightArrow','adjustments':fitted['adjustments']},cid,layer['semantic_class'],
                fill=''.join(f'{int(v):02X}' for v in backgrounds[0]),stroke=''.join(f'{int(v):02X}' for v in colors[0]),line_width=fitted['line_width']*ratio))
            out[-1]['evidence_status']='observed'
            continue
        if layer.get('primitive_family')=='parallel_curved_bands':
            if not layer.get('mask') or backgrounds is None or len(colors)!=3:
                raise ValueError('Declare the natural pair ownership and original rim/inner/outer paints')
            from .source_parallel import fit_parallel
            from .common import identity,write_json
            def original_mask(descriptor):
                file=safe_path(task,descriptor['path'])
                if digest(file)!=descriptor['sha256']:raise ValueError('Original natural-band ownership changed')
                data=np.asarray(Image.open(file).convert('L'))>0
                if data.shape!=observed.shape:raise ValueError('Natural band masks use the same fixed original frame')
                return data
            materials=layer.get('material_masks',[])
            if len(materials)!=2:raise ValueError('Read both original colored band owners independently')
            family=dict(layer.get('family_evidence',{}))
            family['evaluation_mask']=original_mask(layer['evaluation_mask'])
            contours,audit=fit_parallel(roi,observed,[original_mask(m) for m in materials],colors,backgrounds,family)
            audit.update(source_hash=state['source']['sha256'],roi=layer['roi'],owner=cid,part=layer['part_id'])
            write_json(Path(task)/'scratch'/('source-parallel-'+identity(audit)[:20]+'.json'),audit)
            for role,paths,paint in zip(('rim','inner_wave','outer_wave'),contours,colors):
                out.append(node(cid+'__'+layer['part_id']+'__'+role,'path',[x,y,w,h],{'contours':paths},cid,
                    'original_parallel_signal_'+role,fill=''.join(f'{int(v):02X}' for v in paint),stroke=None))
                out[-1]['evidence_status']='observed'
            continue
        if layer.get('primitive_family'):
            if layer['primitive_family']!='open_radial_mast' or not layer.get('mask') or backgrounds is None or len(colors)!=1:
                raise ValueError('Use one independently source-confirmed radial glyph with exact original ownership/paint')
            from .source_radial import fit_radio
            from .common import identity,write_json
            contours,audit=fit_radio(roi,observed,colors[0],backgrounds,layer.get('family_evidence',{}))
            audit.update(source_hash=state['source']['sha256'],roi=layer['roi'],owner=cid,part=layer['part_id'])
            write_json(Path(task)/'scratch'/('source-radial-'+identity(audit)[:20]+'.json'),audit)
            out.append(node(cid+'__'+layer['part_id'],'path',[x,y,w,h],{'contours':contours},cid,
                            layer['semantic_class'],fill=layer['fill'],stroke=layer.get('stroke'),line_width=layer.get('line_width',0)))
            out[-1]['evidence_status']='observed'
            continue
        # Smooth subpixel sampling boundaries, never a broad semantic blur.
        sigma=layer.get('smooth_px',.45)
        epsilon=layer.get('epsilon_px',.25)
        if not 0<=sigma<=.8 or not 0<=epsilon<=.8:
            raise ValueError('Source fitting preserves the source feature scale')
        mask=ndi.gaussian_filter(observed.astype(float),sigma)>=.5 if sigma else observed
        completion_only=None
        if layer.get('completion'):
            completion=layer['completion']
            if not layer.get('mask') or not completion.get('basis') or layer.get('complete_holes'):
                raise ValueError('Explicit plane completion needs an original visible mask, basis and one unambiguous method')
            def completion_mask(key):
                descriptor=completion[key];file=safe_path(task,descriptor['path'])
                if digest(file)!=descriptor.get('sha256'):
                    raise ValueError('Frozen plane completion evidence changed')
                data=np.asarray(Image.open(file).convert('L'))>0
                if data.shape!=observed.shape:
                    raise ValueError('Completion and observed plane use the same source ROI')
                return data
            completed=completion_mask('completed_mask')
            occluder=completion_mask('occlusion_mask')
            if np.any(observed & ~completed):
                raise ValueError('Plane completion cannot remove original visible samples')
            completion_only=completed & ~observed
            if np.any(completion_only & ~occluder):
                raise ValueError('Plane completion must stay under its observed occluder')
            mask |= completion_only
        if layer.get('complete_holes'):
            # Complete only explicitly bounded occluders; do not fill negative space.
            completion=layer['complete_holes']
            if not completion.get('basis') or not completion.get('occlusion_mask'):
                raise ValueError('Occluded layer completion needs its observed occluder and semantic basis')
            path=safe_path(task,completion['occlusion_mask']['path'])
            if digest(path)!=completion['occlusion_mask']['sha256']:
                raise ValueError('Occluder mask changed')
            occluder=np.asarray(Image.open(path).convert('L'))>0
            if occluder.shape!=mask.shape:
                raise ValueError('Occluder and layer share the same fixed canvas')
            filled=ndi.binary_fill_holes(mask)
            mask |= filled & occluder
        if layer.get('primitive'):
            preset=layer['primitive']
            if preset not in ('rect','ellipse','roundRect'):
                raise ValueError('Use an expressible single native primitive')
            yy,xx=np.where(mask)
            if not len(xx):raise ValueError('Source primitive has no observed foreground')
            box=layer.get('geometry_bbox',[x+float(xx.min()),y+float(yy.min()),
                float(xx.max()-xx.min()+1),float(yy.max()-yy.min()+1)])
            if min(box[2:])<=0 or box[0]<x-1 or box[1]<y-1 or box[0]+box[2]>x+w+1 or box[1]+box[3]>y+h+1:
                raise ValueError('Primitive fitting cannot leave the source evidence extent')
            ident=cid+'__'+layer['part_id']
            out.append(node(ident,'shape',box,{'preset':preset},cid,layer['semantic_class'],
                fill=layer['fill'],stroke=layer.get('stroke'),line_width=layer.get('line_width',0)))
            out[-1]['evidence_status']='observed'
            continue
        contours=[]
        # Preserve the continuous level set instead of thresholding it back to
        # staircase pixels before tracing. Curve fitting is explicit per layer.
        field_mode=layer.get('field_mode','binary')
        if field_mode not in ('binary','color_contrast'):
            raise ValueError('Choose an explicit source boundary field')
        if field_mode=='color_contrast':
            if backgrounds is None:
                raise ValueError('Continuous source boundaries need observed foreground and background palettes')
            # Retain the actual antialias transition instead of first rounding
            # grey samples into pixel cells. Support stays within one source
            # pixel of the identified foreground; natural holes stay empty.
            support=ndi.binary_dilation(observed,structure=np.ones((3,3),bool))
            for descriptor in layer.get('exclude_source_masks',[]):
                excluded=safe_path(task,descriptor['path'])
                support &= ~(np.asarray(Image.open(excluded).convert('L'))>0)
            scalar=background_distance/np.maximum(foreground_distance+background_distance,1e-8)
            scalar=np.where(support,scalar,0.)
        else:
            scalar=observed.astype(float)
        if completion_only is not None:
            # Only unobserved, occluder-owned samples are inferred. Preserve
            # the original continuous grey field on every visible boundary.
            scalar=np.maximum(scalar,completion_only.astype(float))
        field=ndi.gaussian_filter(scalar,sigma) if sigma else scalar
        if layer.get('complete_holes'):field=np.maximum(field,mask.astype(float))
        for contour in find_contours(np.pad(field,1),.5):
            if len(contour)<5:continue
            # Pixel cells occupy [i,i+1]; their centres are i+.5.
            # Padding adds one sample, so subtract .5, not 1.
            points=approximate_polygon(contour,epsilon)-.5
            coordinates=[[float(c)/w,float(r)/h] for r,c in points]
            if layer.get('smooth_curves') and len(coordinates)>4:
                if np.allclose(coordinates[0],coordinates[-1]):coordinates.pop()
                commands=[{'op':'moveTo','points':[coordinates[0]]}]
                count=len(coordinates);tension=layer.get('curve_tension',.12)
                if not 0<=tension<=1/6:raise ValueError('Source-bounded smooth curve tension')
                for i,start in enumerate(coordinates):
                    previous=coordinates[(i-1)%count];end=coordinates[(i+1)%count];following=coordinates[(i+2)%count]
                    c1=[start[k]+(end[k]-previous[k])*tension for k in (0,1)]
                    c2=[end[k]-(following[k]-start[k])*tension for k in (0,1)]
                    commands.append({'op':'cubicBezTo','points':[c1,c2,end]})
                commands.append({'op':'close','points':[]})
                contours.append({'closed':True,'commands':commands})
            else:
                contours.append({'closed':True,'points':coordinates})
        if not contours:
            raise ValueError('Declared layer has no isolated source contour')
        ident=cid+'__'+layer['part_id']
        out.append(node(ident,'path',[x,y,w,h],{'contours':contours},cid,
                        layer['semantic_class'],fill=layer['fill'],stroke=layer.get('stroke'),
                        line_width=layer.get('line_width',0)))
        out[-1]['evidence_status']='observed'
    # Container clipping is semantic geometry, never automatic relayout.
    for layer in layers:
        if not layer.get('container'):continue
        from .source_preset_fit import clip_plane_to_ellipse
        ident=cid+'__'+layer['part_id']
        indices=[i for i,node in enumerate(out) if node['id']==ident]
        if len(indices)!=1:raise ValueError('A source container needs exactly one natural native plane')
        out[indices[0]]=clip_plane_to_ellipse(out[indices[0]],layer['container'])
    return out


def bounded_body_material(colored_body,source_pose_degrees,body_width_fraction=.23):
    """Complete one identified chassis under its panes, never radio/ground gaps.

    The supplied mask contains original body-colour samples. Source pose is an
    independently observed attribute, not the orientation of a future recipe.
    This is an explicitly constrained inference, not observed hidden pixels.
    """
    from skimage.morphology import convex_hull_image
    if not .12<=body_width_fraction<=.30:raise ValueError('Declare the observed narrow body extent')
    data=np.asarray(colored_body,bool);h,w=data.shape
    yy,xx=np.indices(data.shape);angle=math.radians(source_pose_degrees)
    transverse=(xx-w/2)*math.cos(angle)+(yy-h/2)*math.sin(angle)
    inner=data & (np.abs(transverse)<=min(w,h)*body_width_fraction)
    if inner.sum()<6:raise ValueError('Insufficient source chassis samples; refine the source reading')
    hull=convex_hull_image(inner)
    return hull & (np.abs(transverse)<=min(w,h)*body_width_fraction+.75)


def palette_protocol(task,state,layer):
    """Propose the same original colour class for ownership and scoring.

    Return source-only parameters for the existing typed palette selector.
    The host must apply any source revision through the normal history route;
    no drawing/threshold/acceptance is changed by this proposal.
    """
    from .common import identity,write_json
    if not layer.get('evidence') or not layer.get('mask') or not layer.get('background_colors_rgb'):
        raise ValueError('Read a named original layer, owned mask and observed foreground/background palettes')
    file=safe_path(task,layer['mask']['path'])
    if digest(file)!=layer['mask']['sha256']:raise ValueError('Original layer ownership changed')
    x,y,w,h=map(int,layer['roi']);mask=np.asarray(Image.open(file).convert('L'))>0
    if mask.shape!=(h,w) or not mask.any():raise ValueError('Nonempty original layer ownership uses its exact source frame')
    pixels=np.asarray(Image.open(safe_path(task,state['source']['path'])).convert('RGB'),float)[y:y+h,x:x+w]
    colors=np.asarray(layer['colors_rgb'],float);backgrounds=np.asarray(layer['background_colors_rgb'],float)
    if colors.ndim!=2 or colors.shape[1]!=3 or backgrounds.ndim!=2 or backgrounds.shape[1]!=3:
        raise ValueError('Use observed original RGB palettes')
    foreground=np.min(np.linalg.norm(pixels[...,None,:]-colors,axis=3),axis=2)
    background=np.min(np.linalg.norm(pixels[...,None,:]-backgrounds,axis=3),axis=2)
    cap=min(442.,float(np.ceil(foreground[mask].max())+1))
    selector={'mode':'color_distance','colors_rgb':colors.tolist(),
        'distance_rgb_255':cap,'background_colors_rgb':backgrounds.tolist(),
        'foreground_margin_rgb_255':float(layer.get('foreground_margin_rgb_255',0))}
    ambiguous=mask&~((foreground<=cap)&(foreground+selector['foreground_margin_rgb_255']<background))
    result={'status':'SOURCE_PALETTE_PROTOCOL_PROPOSAL_NOT_DRAWING_GAIN',
        'source_hash':state['source']['sha256'],'roi':layer['roi'],'original_mask':layer['mask'],
        'foreground_selector':selector,'source_owned_samples':int(mask.sum()),
        'source_palette_boundary_ambiguity_samples':int(ambiguous.sum()),
        'source_evidence':layer['evidence'],
        'limits':'Original-only palette distance/contrast parameters feed the existing typed selector identically for before/after. Resolve named neighbors and ambiguous source boundaries from original evidence; this proposal cannot approve source ownership, weaken targets, change the native drawing or imply improvement.'}
    folder=Path(task)/'scratch/source-palette-protocol';folder.mkdir(parents=True,exist_ok=True)
    target=folder/(identity(result)[:24]+'.json');write_json(target,result)
    result['proposal']={'path':target.relative_to(task).as_posix(),'sha256':digest(target)}
    return result
