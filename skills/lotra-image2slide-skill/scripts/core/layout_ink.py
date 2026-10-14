"""Automatic native-owner ink envelopes for frozen source relationships.

Interpretation and original owned extents belong to the source contract. The
program requests isolated, full-canvas black/white captures from the actual
saved deck and measures their alpha support. It never synthesizes glyphs from
text frames, projects candidate paint into the original or fits a translation.
"""
import copy
from functools import lru_cache
from pathlib import Path
from .common import digest,identity,safe_path,read_json

ALPHA_CUTOFF=128

def required_owners(task,state,pptx):
    from .relative_layout import contracts,painted_bounds,measure
    rows=contracts(task,state)
    if not rows:return []
    frames=painted_bounds(pptx,state['source_size']);names=set()
    for row in rows:
        if measure(row,frames)['status']=='required_unmeasured':
            names.update(n for n in row['objects'] if n in frames and frames[n]['error'])
    return sorted(names)

@lru_cache(maxsize=96)
def _bounds(black,black_hash,white,white_hash,width,height):
    import numpy as np
    from PIL import Image
    if digest(black)!=black_hash or digest(white)!=white_hash:raise ValueError('Actual owner matte changed')
    with Image.open(black) as a,Image.open(white) as b:
        if a.size!=b.size or a.width<width*4 or a.height<height*4:
            raise ValueError('Use the complete original canvas at least fourfold native sampling')
        sx,sy=a.width/width,a.height/height
        if abs(sx-sy)>1e-6:raise ValueError('Owner matte changed the original aspect ratio')
        response=np.max(np.abs(np.asarray(b.convert('RGB'),dtype=np.int16)-np.asarray(a.convert('RGB'),dtype=np.int16)),axis=2)
        ys,xs=np.nonzero(response<ALPHA_CUTOFF)
        if not len(xs):raise ValueError('Actual owner has no measurable alpha support')
        return (float(xs.min()/sx),float(ys.min()/sy),float((xs.max()-xs.min()+1)/sx),float((ys.max()-ys.min()+1)/sy))

def evaluate(task,state,candidate,row,frames):
    from . import semantic_composition as sc
    from .relative_layout import measure
    if not candidate.get('preview') or not candidate.get('render'):return None
    pptx=safe_path(task,candidate['pptx']['path']);receipt_path=safe_path(task,candidate['render']['path'])
    receipt=read_json(receipt_path)
    if (digest(pptx)!=candidate['pptx']['sha256'] or digest(receipt_path)!=candidate['render']['sha256']
            or receipt.get('pptx_hash')!=candidate['pptx']['sha256']
            or digest(safe_path(task,candidate['preview']['path']))!=receipt.get('preview_hash')
            or candidate['preview']['sha256']!=receipt.get('preview_hash')):
        raise ValueError('Actual layout ink requires this exact saved drawing and full-page host render')
    nodes,parents,_=sc._native(pptx);patched=copy.deepcopy(frames);proof=[]
    cache=state.get('semantic_composition',{}).get('captures',{})
    for name in row['objects']:
        entry=patched.get(name)
        if entry is None or not entry.get('error'):continue
        key=sc._capture_key(nodes,parents,[name],pptx,'paint_support');capture=cache.get(key)
        if not capture or not sc._cached_capture(task,capture,state):return None
        if (capture.get('objects')!=[name] or capture.get('owner_hash')!=key
                or capture.get('backend')!=receipt.get('backend')):
            raise ValueError('Layout ink must come from the exact semantic owner and same actual renderer')
        black=safe_path(task,capture['black']['path']);white=safe_path(task,capture['white']['path'])
        try:
            box=_bounds(str(black),capture['black']['sha256'],str(white),capture['white']['sha256'],*state['source_size'])
        except ValueError as error:
            return {'id':row['id'],'kind':row['kind'],'objects':row['objects'],'status':'required_unmeasured',
                'error':str(error),'measurement_domain':'actual_native_owner_alpha_support'}
        entry['box']=list(box);entry['error']=None
        proof.append({'object':name,'capture_key':key,'capture_hash':identity(capture),'black':capture['black'],
            'white':capture['white'],'host_context':capture['host_context'],'paint_bounds':list(box)})
    if not proof:return None
    result=measure(row,patched)
    result.update(measurement_domain='actual_native_owner_alpha_envelope_on_original_canvas',
        ink_evidence=proof,render_hash=digest(receipt_path),preview_hash=candidate['preview']['sha256'],
        source_extent_basis={'contract_hash':identity(row),'source_hash':row['source_hash'],
            'source_bounds':row['source_bounds'],'source_view':row['source_view']},
        protocol={'alpha_cutoff':ALPHA_CUTOFF,'sampling':'at_least_4x','registration':'none',
            'domain':'Independent owner support envelope; visible occlusion and pixel collisions are separate composition contracts.'})
    return result
