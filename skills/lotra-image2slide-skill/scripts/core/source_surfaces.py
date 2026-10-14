"""Original-owned projected surfaces compiled into a compact native/SVG proposal.

The host supplies source plane coordinates and immutable visibility masks. This
operator does not recognize an arbitrary scene, invent projection or accept a
drawing. Native support precedes one continuous shared surface material field.
"""
from pathlib import Path
import copy,math,re
import numpy as np
from PIL import Image,ImageDraw
from .common import safe_path,digest,identity,write_json,read_json
from .recipes import node


def propose(task,request):
    from .agent_runtime import _state
    from .source_gradients import construct
    task,state=_state(task);selected=state.get('selected')
    if not selected or selected['pptx']['sha256']!=request.get('baseline_hash'):
        raise ValueError('Bind the actual selected source-surface baseline')
    if request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Surface programs require the immutable original source')
    unit=state['quality']['units'][request['unit']];x,y,w,h=unit['roi']
    if unit['profile'] not in ('flat','structured','three_dimensional') or max(w,h)>400 or w*h>60000:
        raise ValueError('Recurse into one identified natural icon or bounded icon family')
    root=request.get('root')
    if root not in unit['objects']:
        raise ValueError('Use an actual bound semantic root, not a planned native ID')
    source=np.asarray(Image.open(safe_path(task,state['source']['path'])).convert('RGB'));height,width=source.shape[:2]
    groups=request.get('surfaces',[])
    identifiers=[g['id'] for g in groups]+[f['id'] for g in groups for f in g.get('faces',[])]
    if any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*',v) for v in identifiers):
        raise ValueError('Surface IDs must be safe native identities, never filesystem paths')
    if not 1<=len(groups)<=24 or len(set(identifiers))!=len(identifiers):
        raise ValueError('At most24 independently named source surface groups per proposal')
    code=digest(Path(__file__));key=identity({'source':state['source']['sha256'],'unit':{k:v for k,v in unit.items() if k not in ('status','built_fingerprint')},'request':request,'code':code})[:24]
    folder=task/'scratch/source-surfaces'/key;folder.mkdir(parents=True,exist_ok=True);saved=folder/'proposal.json'
    if saved.is_file():return read_json(saved)
    scene=read_json(safe_path(task,selected['scene']['path']));byid={o['id']:o for o in scene['objects']}
    for obj in byid.values():
        parent=obj['id']
        while parent in byid and parent!=root:parent=byid[parent].get('parent')
        if parent==root and obj['render_type'] in ('text','equation','table','connector'):
            raise ValueError('Keep native scientific text, formulas and connectors independent')
    objects=[node(root,'group',byid[root]['bbox'],semantic=byid[root].get('semantic_type','original_owned_projected_surfaces'))];bindings={unit['part']:[root]};inventory=[]
    def polygon(points):
        if not 3<=len(points)<=24 or any(len(v)!=2 or any(not math.isfinite(k) for k in v) for v in points):
            raise ValueError('Bounded original source polygon coordinates required')
        if any(not x-1<=px<=x+w+1 or not y-1<=py<=y+h+1 for px,py in points):
            raise ValueError('Surface coordinates must remain in the source-owned unit')
        im=Image.new('L',(width,height));ImageDraw.Draw(im).polygon([tuple(v) for v in points],fill=255)
        return np.asarray(im)>0
    def native(ident,parent,points,fill,semantic,status):
        xs,ys=zip(*points);xx,yy=min(xs),min(ys);ww,hh=max(xs)-xx,max(ys)-yy
        if min(ww,hh)<=0:raise ValueError('A source surface has no area')
        result=node(ident,'path',[xx,yy,ww,hh],{'contours':[{'closed':True,'points':[[(px-xx)/ww,(py-yy)/hh] for px,py in points]}]},parent,semantic,fill=fill,stroke=None)
        result['style'].pop('line_width',None);result['evidence_status']=status;return result
    def mask(descriptor,roi):
        file=safe_path(task,descriptor['path'])
        if digest(file)!=descriptor['sha256']:raise ValueError('Original surface visibility mask changed')
        data=np.asarray(Image.open(file).convert('L'))>0;xx,yy,ww,hh=map(int,roi)
        if data.shape!=(hh,ww):raise ValueError('Surface mask uses its declared source coordinates')
        out=np.zeros((height,width),bool);out[yy:yy+hh,xx:xx+ww]=data;return out
    for group in groups:
        if not group.get('evidence') or unit['owner']+':'+group.get('quality_part','') not in state['quality']['units']:
            raise ValueError('Each original surface group needs evidence and a source part binding')
        faces=group.get('faces',[])
        if not 1<=len(faces)<=8:raise ValueError('Recurse a complex object into named natural surfaces')
        gid=group['id'];groi=group['roi'];gx,gy,gw,gh=map(int,groi)
        if gx<x-1 or gy<y-1 or gx+gw>x+w+1 or gy+gh>y+h+1:raise ValueError('Group leaves its source-owned unit')
        objects.append(node(gid,'group',groi,parent=root,semantic=group.get('semantic','source_projected_icon')));owned=np.zeros((height,width),bool);face_inventory=[]
        for face in faces:
            if not face.get('evidence') or unit['owner']+':'+face.get('quality_part','') not in state['quality']['units']:raise ValueError('Every important plane needs original evidence and a binding')
            points=face['points'];support=polygon(points);visible=mask(face['visible_mask'],face['roi'])
            # Source antialias context may extend one original pixel past the
            # analytic face. It must be explicitly original-owned, not inferred
            # from background colour or from the candidate.
            from scipy.ndimage import binary_dilation
            if np.any(visible & ~binary_dilation(support,iterations=1)) or not visible.any():
                raise ValueError('Visible source samples must belong to the observed plane/context')
            owned|=visible;fill=face.get('fill') or ''.join(f'{v:02X}' for v in np.rint(np.median(source[visible],axis=0)).astype(int));ident=face['id'];objects.append(native(ident,gid,points,fill,'observed_'+face.get('semantic','surface'),'observed'));face_inventory.append({'part':face['quality_part'],'native':ident,'visibility':face['visible_mask'],'evidence':face['evidence']})
        body=group.get('complete_body')
        if body:
            if not body.get('constraints') or not body.get('evidence'):raise ValueError('Hidden body continuation needs explicit semantic constraints')
            body_id=gid+'__complete_body';fill=body.get('fill') or ''.join(f'{v:02X}' for v in np.rint(np.median(source[owned],axis=0)).astype(int));support=native(body_id,gid,body['points'],fill,'constrained_complete_body','inferred');objects.insert(len(objects)-len(faces),support)
        local=owned[gy:gy+gh,gx:gx+gw];visible_file=folder/(gid+'-original-visible.png');Image.fromarray(np.uint8(local)*255).save(visible_file);material_id=gid+'__shared_material';component={'id':material_id,'roi':groi,'semantic_class':'source_shared_surface_material'}
        material=construct(task,state,component,{'edge_overlap_px':.2,'field_sampling':group.get('field_sampling','horizontal_rows'),'vertical_subdivisions':group.get('vertical_subdivisions',4)},source[gy:gy+gh,gx:gx+gw],local,local,{'source':state['source']['sha256'],'mask':digest(visible_file)})[0];material['parent']=gid;material['evidence_status']='observed';objects.append(material)
        bindings[group['quality_part']]=[gid]
        for face in face_inventory:bindings[face['part']]=[face['native'],material_id]
        inventory.append({'id':gid,'source_roi':groi,'faces':face_inventory,'complete_body':copy.deepcopy(body),'shared_material':material_id,'source_samples':int(local.sum())})
    result={'status':'SOURCE_SURFACE_PROPOSAL_REQUIRES_SCOPED_DRAW_AND_ACTUAL_OBSERVATION','unit':unit['id'],'baseline_hash':selected['pptx']['sha256'],'source_hash':state['source']['sha256'],'method':{'coordinate_space':'source_px','objects':objects,'source_bindings':bindings},'surfaces':inventory,'native_object_count':len(objects),'limits':'Source-bound native scaffold and one continuous SVG material field per semantic group. All important faces keep independent source windows/targets. No semantic acceptance, HD-generation claim, image-wide tracing or unauthorized non-target edit.'}
    write_json(saved,result);return result
