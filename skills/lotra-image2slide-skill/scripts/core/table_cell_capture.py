"""Actual glyph ownership for cells whose COM bounds are local or undefined.

Reuse the dual-background native capture writer. The private projection keeps
the original table tracks, cell margins, paragraphs, transforms and math; only
other paint is hidden. A nominal cell frame is never substituted for its ink.
"""
import copy
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from PIL import Image
from lxml import etree as E
from .common import digest,identity,read_json,write_json,safe_path
from .mathml import NS,el

def _projection(parts,tree,native,name,row,col,colour):
    from .semantic_composition import isolated_parts
    from .inspect import inventory
    nid=int(native[name]['node'].find('.//p:cNvPr',NS).get('id'))
    projected=isolated_parts(parts,tree,{'leaf_objects':[name],'native_ids':[nid]},colour)
    doc=E.fromstring(projected['ppt/slides/slide1.xml']);node=inventory(doc)[0][name]['node']
    table=node.find('.//a:tbl',NS)
    for ri,tr in enumerate(table.findall('a:tr',NS)):
        for ci,cell in enumerate(tr.findall('a:tc',NS)):
            props=cell.find('a:tcPr',NS)
            if props is None:props=el('a:tcPr');cell.append(props)
            for old in list(props):
                if E.QName(old).localname in ('solidFill','gradFill','pattFill','blipFill','noFill') or E.QName(old).localname.startswith('ln'):
                    props.remove(old)
            props.append(el('a:noFill'))
            for side in ('L','R','T','B','TlToBr','BlToTr'):
                line=el('a:ln'+side,w='0');line.append(el('a:noFill'));props.append(line)
            if (ri,ci)!=(row,col):
                body=cell.find('a:txBody',NS)
                for para in body.findall('a:p',NS):
                    for child in list(para):
                        if child.tag not in ('{'+NS['a']+'}pPr','{'+NS['a']+'}endParaRPr'):para.remove(child)
    return E.tostring(doc,encoding='utf-8',xml_declaration=True,standalone=True)

def _signature(entry,row,col):
    return identity({'table':E.tostring(entry['node'],method='c14n',exclusive=True).decode('utf-8'),
                    'matrix':entry['matrix'].tolist(),'cell':[row,col]})

def capture(task,state,candidate,keys):
    from .boundary_geometry import saved_nodes
    from .native_capture_batch import package,save_immutable
    from .office_bridge import render,discover
    if not keys or len(keys)>12:raise ValueError('Capture 1..12 real table glyph owners per batch')
    native=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    ids={}
    for key in keys:
        name,slot=key.split('@cell:');row,col=map(int,slot.split(':'))
        ids[key]=(name,row,col,_signature(native[name],row,col))
    tables={r[0] for r in ids.values()}
    if len(tables)!=1:raise ValueError('One actual table per cell-glyph capture batch')
    table_name=next(iter(tables))
    basis=identity({'pptx':candidate['pptx'],'cells':ids,'sampling':2,'projection':'actual-native-cell-glyph-2'})
    folder=task/'neighbor-captures/cells'/basis;folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/'Result.json'
    if receipt.exists():
        record=read_json(receipt)
        state.setdefault('cell_mattes',{}).update(record['mattes']);return record
    with ZipFile(safe_path(task,candidate['pptx']['path'])) as z:parts={p:z.read(p) for p in z.namelist()}
    tree=E.fromstring(parts['ppt/slides/slide1.xml']);pages=[]
    for name,row,col,signature in ids.values():
        for colour in ('black','white'):pages.append(_projection(parts,tree,native,name,row,col,colour))
    # Office table styles may retain grid paint despite explicit noFill/lines.
    # Capture the exact same empty table, then isolate changed glyph pixels.
    # Grid/style paint is observed and canceled, never interpreted as glyphs.
    for colour in ('black','white'):pages.append(_projection(parts,tree,native,table_name,-1,-1,colour))
    carrier=folder/'Cells.pptx';save_immutable(carrier,package(parts,pages));out=folder/'actual-host'
    host=read_json(out/'render.json') if (out/'render.json').exists() else render(carrier,out,discover(),width=state['source_size'][0]*2)
    if host['pptx_hash']!=digest(carrier) or len(host['pages'])!=2*len(keys)+2:raise ValueError('Actual table glyph capture pages changed')
    blank=[]
    for page in host['pages'][-2:]:
        file=out/page['path']
        if digest(file)!=page['sha256']:raise ValueError('Empty table control bytes changed')
        blank.append(np.asarray(Image.open(file).convert('RGB'),float))
    mattes={}
    for i,(key,values) in enumerate(ids.items()):
        pair=[]
        for page in host['pages'][2*i:2*i+2]:
            file=out/page['path']
            if digest(file)!=page['sha256']:raise ValueError('Table glyph render bytes changed')
            pair.append(np.asarray(Image.open(file).convert('RGB'),float))
        alpha=np.maximum(np.abs(pair[0]-blank[0]).max(2),np.abs(pair[1]-blank[1]).max(2))/255.;threshold=max(.02,float(alpha.max())*.5)
        yy,xx=np.where(alpha>=threshold)
        if not len(xx):raise ValueError('Required visible cell content has no actual painted glyph: '+key)
        l,t,r,b=int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)
        mask=(alpha[t:b,l:r]>=threshold).astype('uint8')*255;file=folder/(identity(key)[:20]+'.png');Image.fromarray(mask).save(file)
        sx,sy=state['source_size'][0]/alpha.shape[1],state['source_size'][1]/alpha.shape[0]
        mattes[key]={'path':file.relative_to(task).as_posix(),'sha256':digest(file),'pixel_size':[r-l,b-t],
          'roi':[l*sx,t*sy,(r-l)*sx,(b-t)*sy],'pptx_hash':candidate['pptx']['sha256'],'owner_native_signature':values[3],
          'owner':key,'origin_pptx':copy.deepcopy(candidate['pptx']),'capture_index':i,'capture_keys':list(ids),'capture_pptx':{'path':carrier.relative_to(task).as_posix(),'sha256':digest(carrier)},
          'host_render':{'path':(out/'render.json').relative_to(task).as_posix(),'sha256':digest(out/'render.json')},
          'sampling_error_px':max(sx,sy),'backend':host['backend'],'projection':'actual-native-cell-glyph-2','blank_index':2*len(keys)}
    result={'status':'ACTUAL_CELL_GLYPHS_MEASURED','mattes':mattes,'pptx':candidate['pptx']}
    write_json(receipt,result)
    history=state.setdefault('cell_matte_history',[])
    prior=copy.deepcopy(state.get('cell_mattes',{}))
    if prior and prior not in history:history.append(prior)
    state.setdefault('cell_mattes',{}).update(mattes);return result

def read(task,state,candidate,key,native):
    from .execution_contract import resource
    from .neighbor_geometry import _matte
    ref=state.get('cell_mattes',{}).get(key)
    if not ref:raise ValueError('Actual cell ownership capture required: '+key)
    name,slot=key.split('@cell:');row,col=map(int,slot.split(':'))
    if ref['owner_native_signature']!=_signature(native[name],row,col):
        raise ValueError('Stale actual table cell glyph evidence: '+key)
    from .neighbor_capture import _transport_inputs
    origin,dependencies=_transport_inputs(str(resource(task,ref['origin_pptx'])),ref['origin_pptx']['sha256'],tuple(state['source_size']))
    current,actual_dependencies=_transport_inputs(str(resource(task,candidate['pptx'])),candidate['pptx']['sha256'],tuple(state['source_size']))
    if dependencies!=actual_dependencies or _signature(origin[name],row,col)!=ref['owner_native_signature']:
        raise ValueError('Changed table/font/media evidence requires a fresh actual cell capture')
    host=read_json(resource(task,ref['host_render']));resource(task,ref['capture_pptx'])
    if host['pptx_hash']!=ref['capture_pptx']['sha256']:raise ValueError('Table glyph evidence is not bound to its actual native projection')
    with ZipFile(resource(task,ref['origin_pptx'])) as z:parts={p:z.read(p) for p in z.namelist()}
    tree=E.fromstring(parts['ppt/slides/slide1.xml'])
    with ZipFile(resource(task,ref['capture_pptx'])) as z:
        for j,colour in enumerate(('black','white')):
            expected=E.fromstring(_projection(parts,tree,origin,name,row,col,colour))
            actual=E.fromstring(z.read('ppt/slides/slide'+str(ref['capture_index']*2+j+1)+'.xml'))
            if E.tostring(expected,method='c14n')!=E.tostring(actual,method='c14n'):
                raise ValueError('Cell glyph capture differs from its deterministic original native projection')
        for j,colour in enumerate(('black','white')):
            expected=E.fromstring(_projection(parts,tree,origin,name,-1,-1,colour))
            actual=E.fromstring(z.read('ppt/slides/slide'+str(ref['blank_index']+j+1)+'.xml'))
            if E.tostring(expected,method='c14n')!=E.tostring(actual,method='c14n'):
                raise ValueError('Empty-table glyph control differs from the actual native projection')
    if ref.get('projection')!='actual-native-cell-glyph-2':raise ValueError('Table grid is not glyph ownership; recapture with its blank control')
    return {'geometry':_matte(task,ref,state['source_size']),'method':'ACTUAL_HOST_CELL_OWNER_MATTE','parent':name}
