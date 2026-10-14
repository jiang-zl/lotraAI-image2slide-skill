"""Actual host dual-backdrop ownership mattes for unsupported native paint."""
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from PIL import Image
from lxml import etree as E
from .common import read_json,write_json,safe_path,digest,identity
from .mathml import NS
from functools import lru_cache


@lru_cache(maxsize=16)
def _transport_inputs(file,sha256,size):
    from .boundary_geometry import saved_nodes
    import hashlib
    if digest(Path(file))!=sha256:raise ValueError('Native transport bytes changed')
    with ZipFile(file) as z:
        dependencies={p:hashlib.sha256(z.read(p)).hexdigest() for p in z.namelist() if p!='ppt/slides/slide1.xml'}
    return saved_nodes(file,size),dependencies


def _transport_verify(task,candidate,name,record):
    """Reuse measured pixels only under proven identical paint + translation.

    No candidate registration or new pixels. Media/themes/fonts and linear
    transforms remain byte-identical; an altered glyph/path/style must be
    captured again. The original actual capture remains the evidence origin.
    """
    import copy
    from .boundary_geometry import saved_nodes
    origin=record['origin_pptx'];current=candidate['pptx'];size=record['canvas']
    for ref in (origin,current):
        if digest(safe_path(task,ref['path']))!=ref['sha256']:raise ValueError('Transport native input changed')
    before,deps=_transport_inputs(str(safe_path(task,origin['path'])),origin['sha256'],tuple(size))
    after,changed=_transport_inputs(str(safe_path(task,current['path'])),current['sha256'],tuple(size))
    if deps!=changed:raise ValueError('Owner paint transport cannot cross changed media, fonts, themes or other package dependencies')
    old=before[name];new=after[name]
    def shape(entry):
        node=copy.deepcopy(entry['node'])
        for point in node.findall('p:spPr/a:xfrm/a:off',NS)+node.findall('p:xfrm/a:off',NS):point.set('x','0');point.set('y','0')
        return E.tostring(node,method='c14n',exclusive=True)
    if shape(old)!=shape(new) or old['error'] or new['error'] or not np.allclose(old['matrix'][:2,:2],new['matrix'][:2,:2],atol=1e-9,rtol=0):
        raise ValueError('Owner paint changed beyond a rigid world translation')
    signature=lambda row:identity({'xml':E.tostring(row['node'],method='c14n',exclusive=True).decode('utf-8'),'matrix':row['matrix'].tolist()})
    ref=record['origin_matte']
    if ref.get('pptx_hash')!=origin['sha256'] or ref.get('owner')!=name or ref.get('owner_native_signature')!=signature(old):raise ValueError('Transport origin does not bind its actually captured native owner')
    delta=(new['matrix'][:2,2]-old['matrix'][:2,2]).tolist()
    x,y,w,h=ref['roi'];expected={**copy.deepcopy(ref),'pptx_hash':current['sha256'],'owner_native_signature':signature(new),'roi':[x+delta[0],y+delta[1],w,h]}
    return expected,delta


def verify_transport(task,candidate,name,ref):
    if not ref.get('transport'):return
    evidence=ref['transport'];file=safe_path(task,evidence['path'])
    if digest(file)!=evidence['sha256']:raise ValueError('Owner transport evidence changed')
    record=read_json(file);expected,delta=_transport_verify(task,candidate,name,record)
    if record['candidate']!=candidate['pptx']:raise ValueError('Transport receipt refers to a different current artifact')
    if candidate.get('render'):
        actual=read_json(safe_path(task,candidate['render']['path']))
        if actual.get('backend')!=ref['backend']:raise ValueError('Geometric paint transport cannot cross an actual renderer change')
    if {k:v for k,v in ref.items() if k!='transport'}!=expected or record.get('delta')!=delta:raise ValueError('Owner transport ROI or identity differs from independently computed native transform')
    from .execution_contract import resource
    for key in ('capture_pptx','host_render'):resource(task,record['origin_matte'][key])


def transport(task,state,candidate,baseline,mattes):
    """Finite geometric evidence reuse, followed by current full-page render."""
    import copy
    migrated={};rejected=[]
    for name,ref in mattes.items():
        try:
            if ref.get('transport'):
                file=safe_path(task,ref['transport']['path'])
                if digest(file)!=ref['transport']['sha256']:raise ValueError('Historical transport changed')
                prior=read_json(file);origin=prior['origin_pptx'];original=prior['origin_matte']
            else:origin=baseline['pptx'];original=ref
            record={'schema':'actual-owner-translation-1','canvas':state['source_size'],'owner':name,
                'origin_pptx':copy.deepcopy(origin),'origin_matte':copy.deepcopy(original),'candidate':copy.deepcopy(candidate['pptx'])}
            current,delta=_transport_verify(task,candidate,name,record);record['delta']=delta
            file=task/'audits/owner-transport'/('proof-'+identity(record)+'.json');write_json(file,record)
            current['transport']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
            migrated[name]=current
        except (ValueError,KeyError,TypeError) as exc:rejected.append({'object':name,'reason':str(exc),'next':'fresh actual owner capture'})
    state['neighbor_mattes']=migrated
    return {'status':'PROVEN_OWNER_TRANSLATIONS_REUSED','migrated':sorted(migrated),'capture_required':rejected,'new_pixel_measurement':False}

def capture(task,state,candidate,names):
    from .boundary_geometry import saved_nodes
    from .semantic_composition import isolated_parts
    from .native_capture_batch import package,save_immutable
    from .office_bridge import render,discover
    native=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    signatures={n:identity({'xml':E.tostring(native[n]['node'],method='c14n',exclusive=True).decode('utf-8'),'matrix':native[n]['matrix'].tolist()}) for n in names}
    key=identity({'pptx':candidate['pptx'],'owners':signatures,'sampling':2,'checker':'neighbor-owner-capture-1'})
    root=Path(task)/'neighbor-captures'/key;receipt=root/'Result.json'
    if receipt.is_file():
        existing=read_json(receipt)
        for r in existing['mattes'].values():
            if digest(safe_path(task,r['path']))!=r['sha256']:raise ValueError('Actual neighbor matte changed')
        state.setdefault('neighbor_mattes',{}).update(existing['mattes']);return existing
    root.mkdir(parents=True,exist_ok=True)
    with ZipFile(safe_path(task,candidate['pptx']['path'])) as archive:parts={n:archive.read(n) for n in archive.namelist()}
    tree=E.fromstring(parts['ppt/slides/slide1.xml']);slides=[]
    for name in names:
        entry=native[name]
        if entry['tag']=='grpSp':raise ValueError('Capture actual leaves, then form group unions')
        nid=int(entry['node'].find('.//p:cNvPr',NS).get('id'))
        item={'leaf_objects':[name],'native_ids':[nid]}
        for colour in ('black','white'):slides.append(isolated_parts(parts,tree,item,colour)['ppt/slides/slide1.xml'])
    pptx=root/'Owners.pptx';save_immutable(pptx,package(parts,slides));output=root/'actual-host'
    if (output/'render.json').is_file():host=read_json(output/'render.json')
    else:host=render(pptx,output,discover(),width=state['source_size'][0]*2)
    if host['pptx_hash']!=digest(pptx) or len(host['pages'])!=2*len(names):raise ValueError('Actual owner capture identities/pages mismatch')
    mattes={}
    for i,name in enumerate(names):
        pages=[]
        for p in host['pages'][i*2:i*2+2]:
            file=output/p['path']
            if digest(file)!=p['sha256']:raise ValueError('Actual owner render changed')
            with Image.open(file) as image:pages.append(np.array(image.convert('RGB'),dtype=np.uint8))
        black,white=pages
        # Sum channel differences in the exact integer quantization domain.
        # The previous float64 pages used 144 MiB each at this canvas size.
        # No uint8 subtraction wraparound and no repeated full float images.
        coverage=np.clip(765-np.subtract(white,black,dtype=np.int16).sum(2,dtype=np.int32),0,765)
        peak_count=int(coverage.max());peak=peak_count/765.;threshold=max(.02,peak*.5)
        if peak_count<=15:raise ValueError('Owner paint is below the measured host quantization floor: '+name)
        binary=coverage>=max(16,(peak_count+1)//2)
        yy,xx=np.where(binary)
        if not len(xx):raise ValueError('Required actual painted owner is empty: '+name)
        l,t,r,b=int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1);mask=binary[t:b,l:r].astype('uint8')*255
        file=root/(identity(name)[:20]+'.png');Image.fromarray(mask).save(file)
        sx,sy=state['source_size'][0]/coverage.shape[1],state['source_size'][1]/coverage.shape[0]
        mattes[name]={'path':file.relative_to(task).as_posix(),'sha256':digest(file),'pptx_hash':candidate['pptx']['sha256'],
                     'owner':name,'owner_native_signature':signatures[name],'roi':[l*sx,t*sy,(r-l)*sx,(b-t)*sy],'pixel_size':[r-l,b-t],
                     'sampling_error_px':max(sx,sy),'stroke_upper_px':max(sx,sy)*4,'alpha_threshold':threshold,'measured_peak_alpha':peak,'capture_pptx':{'path':pptx.relative_to(task).as_posix(),'sha256':digest(pptx)},
                     'host_render':{'path':(output/'render.json').relative_to(task).as_posix(),'sha256':digest(output/'render.json')},'backend':host['backend']}
    result={'status':'ACTUAL_HOST_OWNERS_MEASURED','mattes':mattes,'source':state['source'],'pptx':candidate['pptx'],'sampling':2}
    write_json(receipt,result);state.setdefault('neighbor_mattes',{}).update(mattes)
    return result


def capture_missing(task,state,candidate,batch_size=12):
    from . import neighbor_geometry as ng
    from .boundary_geometry import saved_nodes
    if type(batch_size) is not int or not 1<=batch_size<=12:raise ValueError('Bounded actual-owner capture batch required')
    _,errors=ng.read(task,state,candidate,state.get('neighbor_mattes'))
    nodes=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    names=sorted({r['object'] for r in errors if r.get('object') in nodes and nodes[r['object']]['tag']!='grpSp'})
    if not names:return {'passed':not errors,'status':'ACTUAL_NEIGHBOR_GEOMETRY_READY' if not errors else 'GEOMETRY_DIAGNOSIS_REQUIRED','errors':errors}
    result=capture(task,state,candidate,names[:batch_size]);_,remaining=ng.read(task,state,candidate,state.get('neighbor_mattes'))
    return {'passed':not remaining,'status':'ACTUAL_NEIGHBOR_GEOMETRY_READY' if not remaining else 'MORE_OWNER_CAPTURES_REQUIRED',
            'captured_owners':names[:batch_size],'remaining_errors':remaining,'evidence':result}
