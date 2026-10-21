"""Batch actual owner rendering while preserving every native slide transform."""
from functools import lru_cache
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import digest,read_json,write_json,safe_path
from .mathml import NS

def package(parts,slides):
    if not 1<=len(slides)<=32:raise ValueError('A native owner batch has 1..32 declared pages')
    presentation=E.fromstring(parts['ppt/presentation.xml']);listing=presentation.find('p:sldIdLst',NS)
    if listing is None or len(listing)!=1:raise ValueError('Owner observations require the exact single-page candidate')
    original=listing[0];rid=original.get('{'+NS['r']+'}id');listing.remove(original)
    relationships=E.fromstring(parts['ppt/_rels/presentation.xml.rels']);rel_ns=E.QName(relationships).namespace
    for row in list(relationships):
        if row.get('Id')==rid:relationships.remove(row)
    types=E.fromstring(parts['[Content_Types].xml']);type_ns=E.QName(types).namespace
    payload=dict(parts)
    for index,blob in enumerate(slides,1):
        name='ppt/slides/slide'+str(index)+'.xml';relationship='lotraOwnerPage'+str(index)
        E.SubElement(listing,'{'+NS['p']+'}sldId',id=str(255+index),attrib={'{'+NS['r']+'}id':relationship})
        E.SubElement(relationships,'{'+rel_ns+'}Relationship',Id=relationship,Type=NS['r']+'/slide',Target='slides/slide'+str(index)+'.xml')
        if index>1:E.SubElement(types,'{'+type_ns+'}Override',PartName='/'+name,ContentType='application/vnd.openxmlformats-officedocument.presentationml.slide+xml')
        payload[name]=blob
        if 'ppt/slides/_rels/slide1.xml.rels' in parts:
            payload['ppt/slides/_rels/slide'+str(index)+'.xml.rels']=parts['ppt/slides/_rels/slide1.xml.rels']
    for name,root in [('ppt/presentation.xml',presentation),('ppt/_rels/presentation.xml.rels',relationships),('[Content_Types].xml',types)]:
        payload[name]=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    return payload

def save_immutable(file,payload):
    if file.is_file():
        with ZipFile(file) as z:
            if {n:z.read(n) for n in z.namelist()}!=payload:raise ValueError('Preserve differing immutable native owner batch')
    else:
        with ZipFile(file,'x',compression=ZIP_DEFLATED) as z:
            for name,data in payload.items():z.writestr(name,data)

def capture(task,state,candidate,request_ref,request,parts,tree,capabilities,records):
    from .semantic_composition import isolated_parts,ingest_capture,portable_capture_hash
    from .tool_router import render_saved
    render_folder=safe_path(task,candidate['render']['path']).parent
    directory=render_folder/'owner-captures'/('batch-'+request_ref['sha256'][:24]);directory.mkdir(parents=True,exist_ok=True)
    done={r['id'] for r in records};items=[r for r in request['captures'] if r['id'] not in done]
    if not items:return {'status':'NO_MISSING_OWNERS'}
    slides=[isolated_parts(parts,tree,item,colour)['ppt/slides/slide1.xml'] for item in request['captures'] for colour in ('black','white')]
    pptx=directory/'Owners.pptx';save_immutable(pptx,package(parts,slides))
    output=directory/'render'
    if (output/'render.json').is_file():
        host=read_json(output/'render.json')
        verify_actual_render(pptx,output/'render.json')
    else:
        if output.exists():
            serial=1
            while output.with_name('render-resume-'+str(serial)).exists():serial+=1
            if serial>4:raise ValueError('Native batch renderer exhausted its bounded resume attempts')
            output=output.with_name('render-resume-'+str(serial))
        host=render_saved(pptx,output,capabilities,state['source_size'][0]*4)
    if len(host['pages'])!=2*len(request['captures']):raise ValueError('Actual owner pages differ from the requested native batch')
    for index,item in enumerate(request['captures']):
        if item['id'] in done:continue
        views={};artifacts=[]
        for colour,page_index in [('black',2*index),('white',2*index+1)]:
            page=host['pages'][page_index];file=output/page['path']
            views[colour]={'path':file.relative_to(render_folder).as_posix(),'sha256':digest(file)}
            artifacts.append({'path':pptx.relative_to(task).as_posix(),'sha256':digest(pptx),'slide':page_index+1,
                'render':{'path':(output/'render.json').relative_to(task).as_posix(),'sha256':digest(output/'render.json')}})
        row={**{k:item[k] for k in ('id','objects','owner_hash')},**views,'measurement':item.get('measurement','paint_support'),
            'native_bindings':[{'id':i,'name':n} for i,n in zip(item['native_ids'],item['leaf_objects'])],
            'backend':host['backend'],'backend_version':host.get('backend_version'),
            'provider':'portable_native_batch','provider_script_hash':portable_capture_hash(),
            'renderer_script_hash':host['renderer_script_hash'],'isolated_artifacts':artifacts}
        records.append(row)
        write_json(render_folder/'composition-capture.json',{'schema':'office-composition-observation-1',
            'pptx_hash':candidate['pptx']['sha256'],'canvas':state['source_size'],'request_hash':request_ref['sha256'],
            'captures':records,'status':'PARTIAL_VERIFIED_OWNER_BATCH'})
        ingest_capture(task,state,candidate)
    return {'status':'ACTUAL_PORTABLE_BATCH_CAPTURE','owners':len(records),'actual_render_calls':1}

def verify_actual_render(pptx,receipt_file):
    """Check the actual backend's own export chain, without relabelling it."""
    from pathlib import Path
    pptx,receipt_file=Path(pptx),Path(receipt_file);receipt=read_json(receipt_file)
    if receipt.get('schema')=='presentation-backend-1.36.0':
        from .presentation_backend import verify_render
        return verify_render(pptx,receipt_file)
    if receipt.get('backend')=='LibreOffice':
        from .render import verify_alternative_render
        return verify_alternative_render(pptx,receipt_file)
    if receipt.get('backend')!='PowerPoint' or receipt.get('status')!='PASS' or receipt.get('scope')!='target_render_only':
        raise ValueError('Unsupported actual owner-batch backend or export scope')
    directory=receipt_file.parent;job=read_json(directory/'job-receipt.json');session=read_json(directory/'office-session.json')
    scripts=Path(__file__).resolve().parent.parent
    sha=digest(pptx)
    if (receipt.get('pptx_hash')!=sha or job.get('input_pptx_hash')!=sha or session.get('pptx_hash')!=sha
            or job.get('kind')!='render' or job.get('status')!='COMPLETED_REQUIRES_RESULT_REVIEW'
            or session.get('backend')!='PowerPoint' or job.get('wrapper_hash')!=digest(scripts/'run_office_job.ps1')
            or receipt.get('renderer_script_hash')!=digest(scripts/'render_office.ps1')):
        raise ValueError('Actual PowerPoint batch is not its current isolated native job')
    from pptx import Presentation
    from PIL import Image
    pages=receipt.get('pages',[])
    presentation=Presentation(pptx)
    if len(pages)!=len(presentation.slides) or not pages:raise ValueError('Actual PowerPoint batch pages are incomplete')
    canvas=None
    for index,page in enumerate(pages,1):
        if page.get('slide')!=index:raise ValueError('Actual PowerPoint page ordering changed')
        file=safe_path(directory,page['path'])
        if digest(file)!=page['sha256']:raise ValueError('Actual PowerPoint owner page changed')
        with Image.open(file) as pixels:
            if canvas is None:canvas=pixels.size
            if pixels.size!=canvas or pixels.height!=round(pixels.width*presentation.slide_height/presentation.slide_width):
                raise ValueError('Actual PowerPoint owner canvas changed')
    pdf=receipt.get('pdf',{})
    if (pdf.get('status')!='EXPORTED' or digest(safe_path(directory,pdf['path']))!=receipt.get('pdf_hash')
            or pages[0]['sha256']!=receipt.get('preview_hash')):
        raise ValueError('Actual PowerPoint batch PDF/preview identity changed')
    return {'status':'PASS','scope':'actual_PowerPoint_owned_pages_and_exact_saved_native_job','native_editing_claim':False}


@lru_cache(maxsize=64)
def _verified_render(pptx,pptx_hash,receipt,receipt_hash,pdf_hash,job_hash=None,session_hash=None):
    return verify_actual_render(pptx,receipt)

def verify_record(task,state,candidate,native,row,render_folder):
    """Check saved page ownership, unchanged native bytes and actual PNG page."""
    from .semantic_composition import isolated_parts,_ref,portable_capture_hash
    if row['provider_script_hash']!=portable_capture_hash():raise ValueError('Native batch implementation changed')
    original=_ref(task,candidate['pptx'])
    with ZipFile(original) as z:parts={n:z.read(n) for n in z.namelist()}
    tree=E.fromstring(parts['ppt/slides/slide1.xml'])
    artifacts=row.get('isolated_artifacts',[])
    if len(artifacts)!=2:raise ValueError('Both actual backdrop observations are required')
    for colour,artifact in zip(('black','white'),artifacts):
        pptx=_ref(task,artifact);receipt=_ref(task,artifact['render']);observed=read_json(receipt)
        office=observed.get('backend')=='PowerPoint' and observed.get('schema')!='presentation-backend-1.36.0'
        _verified_render(str(pptx),digest(pptx),str(receipt),digest(receipt),digest(receipt.parent/'Final.pdf'),
                         digest(receipt.parent/'job-receipt.json') if office else None,
                         digest(receipt.parent/'office-session.json') if office else None)
        index=artifact['slide']
        if type(index) is not int or not 1<=index<=len(observed['pages']):raise ValueError('Native page index changed')
        page=observed['pages'][index-1];image=render_folder/row[colour]['path']
        if image.resolve()!=(receipt.parent/page['path']).resolve() or digest(image)!=page['sha256']:
            raise ValueError('Owner matte is not its independently rendered batch page')
        with ZipFile(pptx) as z:
            actual=z.read('ppt/slides/slide'+str(index)+'.xml')
            expected=isolated_parts(parts,tree,native,colour)['ppt/slides/slide1.xml']
            if actual!=expected:raise ValueError('Owner batch changed geometry, parent transforms or paint ownership')
            rel='ppt/slides/_rels/slide'+str(index)+'.xml.rels'
            if z.read(rel)!=parts['ppt/slides/_rels/slide1.xml.rels']:raise ValueError('Owner batch resource relationships changed')
