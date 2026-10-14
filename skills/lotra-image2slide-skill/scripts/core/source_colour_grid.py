"""Bounded original RGB interpolation for one identified natural surface.

Original sample centres, masks and source coordinates remain authoritative.
This interpolates colour; it does not recover unseen texture or generate
scientific/semantic detail. SVG uses bounded sub-row fields; paper PDF uses
the original two-input sampled vector shading function directly.
"""
import base64,hashlib,math,zlib
import numpy as np

NS='https://lotra.ai/ns/colour-grid/1'

def fields(rgb,visible,spec):
    mode=spec.get('field_sampling','horizontal_rows')
    if mode not in ('horizontal_rows','bilinear_grid'):raise ValueError('Unknown original material field model')
    height,width=visible.shape
    subdivisions=spec.get('vertical_subdivisions',4) if mode=='bilinear_grid' else 1
    if not isinstance(subdivisions,int) or not 2<=subdivisions<=8 and mode=='bilinear_grid':raise ValueError('Use2..8bounded SVG vertical subdivisions')
    if mode=='bilinear_grid' and (min(width,height)<2 or max(width,height)>400 or width*height>60000):raise ValueError('Recurse into one bounded natural surface before 2D material interpolation')
    overlap=float(spec.get('edge_overlap_px',.2))/subdivisions
    for index in range(height*subdivisions):
        top=max(0,index/subdivisions-overlap/2);bottom=min(height,(index+1)/subdivisions+overlap/2)
        if not visible[math.floor(top):math.ceil(bottom)].any():continue
        if mode=='horizontal_rows':line=rgb[index]
        else:
            centre=min(height-1,max(0,(index+.5)/subdivisions-.5));lo=int(math.floor(centre));hi=min(height-1,lo+1);alpha=centre-lo
            line=np.rint(rgb[lo].astype(float)*(1-alpha)+rgb[hi].astype(float)*alpha).astype(np.uint8)
        yield index,line,top,bottom

def metadata(rgb,spec):
    if spec.get('field_sampling')!='bilinear_grid':return ''
    height,width=rgb.shape[:2];raw=np.asarray(rgb,dtype=np.uint8).tobytes();encoded=base64.b64encode(zlib.compress(raw)).decode('ascii')
    return '<metadata><sourceGrid xmlns="'+NS+'" width="'+str(width)+'" height="'+str(height)+'" encoding="zlib+base64" sha256="'+hashlib.sha256(raw).hexdigest()+'" interpolation="bilinear">'+encoded+'</sourceGrid></metadata>'

def load(root,width,height):
    item=root.find('{http://www.w3.org/2000/svg}metadata/{'+NS+'}sourceGrid')
    if item is None:return None
    if (item.get('interpolation')!='bilinear' or item.get('encoding')!='zlib+base64'
        or item.get('width')!=str(width) or item.get('height')!=str(height)
        or min(width,height)<2 or max(width,height)>400 or width*height>60000):raise ValueError('Unknown or unbounded original 2D source-grid metadata')
    if len(item.text or '')>width*height*5+100:raise ValueError('Source-grid metadata exceeds bounded native material')
    inflater=zlib.decompressobj();raw=inflater.decompress(base64.b64decode(item.text,validate=True),width*height*3+1)
    if not inflater.eof or inflater.unused_data or len(raw)!=width*height*3 or hashlib.sha256(raw).hexdigest()!=item.get('sha256'):raise ValueError('Original material grid checksum/extent changed')
    return raw

def restore_pdf(document,xref,plan):
    width,height=plan['width'],plan['height'];samples=plan['original_grid'];function=document.get_new_xref()
    document.update_object(function,'<< /FunctionType 0 /Domain [0 '+str(width)+' 0 '+str(height)+'] /Range [0 1 0 1 0 1] /Size ['+str(width)+' '+str(height)+'] /BitsPerSample 8 /Order 1 /Encode [-0.5 '+str(width-.5)+' -0.5 '+str(height-.5)+'] /Decode [0 1 0 1 0 1] >>')
    document.update_stream(function,samples,compress=True)
    document.update_object(xref,'<< /ShadingType 1 /ColorSpace /DeviceRGB /Domain [0 '+str(width)+' 0 '+str(height)+'] /Matrix [1 0 0 1 0 0] /Function '+str(function)+' 0 R /BBox [0 0 '+str(width)+' '+str(height)+'] >>')
    return {'source_rows':height,'source_columns':width,'sample_bytes':len(samples),
            'representation':'PDF Type1 vector shading with2-input Type0/Order1 original RGB function',
            'source_coordinate_model':'Original pixel-centre samples; bilinear interpolation and constant endpoint extension',
            'scope':'Original semantic clip, hidden underlay, native geometry and page layout retained. No image XObject or generated semantic/texture detail.'}

def propose(task,request):
    import copy
    from PIL import Image
    from . import agent_runtime as a,source_quality as q,source_gradients
    from .common import read_json,safe_path,digest,write_json,identity
    task,state=a._state(task);selected=state.get('selected')
    if not selected or request.get('baseline_hash')!=selected['pptx']['sha256'] or request.get('source_hash')!=state['source']['sha256'] or not request.get('source_evidence'):raise ValueError('Bind current native baseline and actual original-owned material evidence')
    unit=q.unit(state,request['unit'])
    if not unit or unit['profile'] not in ('flat','structured','curve','detail','three_dimensional') or len(unit['objects'])!=1:raise ValueError('One independently bound natural surface is required')
    scene=read_json(safe_path(task,selected['scene']['path']));old=next(o for o in scene['objects'] if o['id']==unit['objects'][0]);lineage=old.get('content',{}).get('lineage',{})
    if old['render_type']!='svg' or lineage.get('method')!='continuous_original_colour_gradients' or lineage.get('source_hash')!=state['source']['sha256'] or lineage.get('completion')!='none':raise ValueError('This existing-surface route retains original non-completed RGB ownership; use the explicit underlay surface program for occlusions')
    mask_file=safe_path(task,request['visible_mask']['path'])
    if digest(mask_file)!=request['visible_mask']['sha256'] or digest(mask_file)!=lineage['source_mask_hash']:raise ValueError('Reuse the exact previous original-owned visibility mask; do not alter a protocol to admit a drawing')
    roi=old['bbox']
    if any(float(v)!=int(v) for v in roi):raise ValueError('Existing original RGB grid has integral source coordinates')
    x,y,w,h=map(int,roi);mask=np.array(Image.open(mask_file).convert('L'))>0
    if mask.shape==(state['source_size'][1],state['source_size'][0]):mask=mask[y:y+h,x:x+w]
    if mask.shape!=(h,w) or not mask.any():raise ValueError('Use exact source-frame visibility dimensions')
    rgb=np.array(Image.open(safe_path(task,state['source']['path'])).convert('RGB'))[y:y+h,x:x+w]
    spec={'field_sampling':'bilinear_grid','vertical_subdivisions':request.get('vertical_subdivisions',4),'edge_overlap_px':.2}
    if old['content'].get('office_display')=='preview':
        for key in ('office_display','display_reason','display_evidence'):spec[key]=old['content'].get(key)
    if request.get('office_display')=='preview':
        proof_file=safe_path(task,request['display_evidence']['path'])
        if digest(proof_file)!=request['display_evidence']['sha256']:raise ValueError('Actual material display evidence changed')
        proof=read_json(proof_file);failed=proof['failed_native_result']
        if proof['before']['pptx']['sha256']!=selected['pptx']['sha256']:raise ValueError('Material display failure must originate from this saved baseline')
        for artifact in ('pptx','scene','preview','render'):
            descriptor=failed[artifact]
            if digest(safe_path(task,descriptor['path']))!=descriptor['sha256']:raise ValueError('Actual native material/display artifact changed')
        native_scene=read_json(safe_path(task,failed['scene']['path']));native=next(o for o in native_scene['objects'] if o['id']==old['id'])
        if any(native.get(k)!=old.get(k) for k in ('id','render_type','bbox','parent','style')) or native['content'].get('lineage',{}).get('field_sampling')!='bilinear_grid':raise ValueError('Compatibility preview changes only the already drawn original-grid material owner, never geometry or native identity')
        own=q.evaluate(task,state,failed,unit)
        if own['status']=='numeric_minimum_met':raise ValueError('This measured compatibility route needs its own actual native material failure')
        spec.update(office_display='preview',display_reason='Actual native SVG material failed its unchanged independent source targets; retain this exact original2Dvector mother with an HD local-converter display.',
            display_evidence=request['display_evidence'])
    elif request.get('office_display') not in (None,'native_svg'):raise ValueError('Unknown controlled material display choice')
    component={'id':old['id'],'roi':roi,'semantic_class':old.get('semantic_type','original_owned_surface')}
    replacement=source_gradients.construct(task,state,component,spec,rgb,mask,mask,{'source':state['source']['sha256'],'mask':digest(mask_file)})[0]
    node=copy.deepcopy(old);node['content']=replacement['content'];folder=task/'scratch/source-colour-grid';folder.mkdir(exist_ok=True)
    result={'status':'ORIGINAL_GRID_SURFACE_PROPOSAL_REQUIRES_SCOPED_DRAW','unit':unit['id'],'baseline_hash':selected['pptx']['sha256'],'source_hash':state['source']['sha256'],
            'object':node,'allowed_changes':{old['id']:['replace_component']},'source_evidence':request['source_evidence'],'visible_mask':request['visible_mask'],
            'limits':'Same saved semantic owner, native frame, original samples/mask and source targets. Only the SVG material resource changes; regular scoped subtree submit and actual own-unit/context/PDF evaluation remain required. Not a native-leaf writer grant or generated hidden texture.'}
    file=folder/(identity(result)[:24]+'.json');write_json(file,result)
    result['proposal']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return result
