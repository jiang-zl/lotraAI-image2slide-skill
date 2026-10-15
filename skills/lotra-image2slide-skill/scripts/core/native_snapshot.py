"""Complete saved-native working baseline import, never a quality approval.

The source plan stays separate. Exact native objects/media/parents are read
from the actual file; stale Scene recipes cannot omit nodes or rebuild fonts.
"""
import copy
import hashlib
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from lxml import etree as E
from .common import digest, write_json
from .mathml import NS


def snapshot(task,state,pptx,hints=None):
    from .boundary_geometry import saved_nodes
    from .semantic_interfaces import root_map
    from .frame_plan import _media
    nodes=saved_nodes(pptx,state['source_size'])
    hint_scene=hints or {}
    hints={o['id']:o for o in hint_scene.get('objects',[])}
    objects=[];assetdir=Path(task)/'source/native-assets';assetdir.mkdir(exist_ok=True)
    def blob(data,extension):
        sha=hashlib.sha256(data).hexdigest();p=assetdir/(sha+'.'+extension)
        if p.exists() and digest(p)!=sha:raise ValueError('Immutable imported media changed')
        if not p.exists():p.write_bytes(data)
        return {'path':p.relative_to(task).as_posix(),'sha256':sha}
    with ZipFile(pptx) as z:
        canvas=E.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz',NS)
        for name,entry in nodes.items():
            if entry.get('error'):raise ValueError('Saved native import cannot measure '+name+': '+entry['error'])
            parent_name=entry['parent_name']
            obj=copy.deepcopy(hints.get(name,{}))
            obj.update(id=name,parent=parent_name,bbox=entry['frame'],
                       versions={k:0 for k in ('content','structure','style','placement')},
                       locks={k:False for k in ('content','structure','style','placement')})
            obj.setdefault('style',{});obj.setdefault('semantic_type','saved_native_unclassified')
            obj['evidence_status']='observed'
            node=entry['node'];kind=entry['tag']
            if kind=='grpSp':
                obj['render_type']='group';obj['content']={}
                matrix=root_map(entry)
                points=np.array([[0,0,1],[1,0,1],[1,1,1],[0,1,1]])@matrix.T
                lo,hi=points[:,:2].min(0),points[:,:2].max(0)
                obj['bbox']=[*lo.tolist(),*(hi-lo).tolist()]
            elif kind=='pic':
                svg=_media(z,node,True);raster=_media(z,node)
                if raster is None:raise ValueError('Saved picture needs its actual compatibility media: '+name)
                preview=blob(raster,'png')
                obj['render_type']='svg' if svg is not None else 'photo'
                obj['content']=dict(blob(svg,'svg'),preview=preview) if svg is not None else preview
            elif node.find('.//a:tbl',NS) is not None:
                obj['render_type']='table'
                obj['content']={'native_snapshot_table':True,
                    'rows':[[''.join(t.text or '' for t in c.findall('a:txBody//a:t',NS)) for c in r.findall('a:tc',NS)] for r in node.findall('.//a:tbl/a:tr',NS)]}
            elif node.find('.//m:oMath',NS) is not None:
                from .office_math_contract import _segments
                rows=_segments(node)
                if len(rows)==1 and len(rows[0])==1 and 'ast' in rows[0][0]:
                    obj['render_type']='equation'
                    obj['content']={'ast':rows[0][0]['ast'],'render_mode':'office_math','native_snapshot_math':True}
                else:
                    obj['render_type']='text'
                    obj['content']={'paragraphs':rows,'inline_math':'office_math','native_snapshot_math':True}
            elif any((t.text or '').strip() for t in node.findall('p:txBody//a:t',NS)):
                obj['render_type']='text';obj['content']={'text':'\n'.join(''.join(t.text or '' for t in p.findall('.//a:t',NS)) for p in node.findall('p:txBody/a:p',NS))}
            elif kind=='cxnSp':
                obj['render_type']='connector';obj.setdefault('content',{})
            else:
                preset=node.find('p:spPr/a:prstGeom',NS)
                if preset is not None:
                    obj['render_type']='shape';obj['content']={'preset':preset.get('prst')}
                else:
                    obj['render_type']='path';contours=[]
                    for path in node.findall('p:spPr/a:custGeom/a:pathLst/a:path',NS):
                        width,height=float(path.get('w')),float(path.get('h'));commands=[]
                        for op in path:
                            commands.append({'op':E.QName(op).localname,'points':[[float(p.get('x'))/width,float(p.get('y'))/height] for p in op.findall('a:pt',NS)]})
                        contours.append({'closed':any(c['op']=='close' for c in commands),'commands':commands,
                            **({'compound':True} if sum(c['op']=='moveTo' for c in commands)>1 else {})})
                    obj['content']={'contours':contours}
            # Retain only source semantic annotations from the hash-bound hints.
            # Geometry, literals and mathematical AST above still come from OOXML.
            original_content=hints.get(name,{}).get('content',{})
            for semantic_key in ('natural_icon','natural_part'):
                if semantic_key in original_content:
                    obj['content'][semantic_key]=copy.deepcopy(original_content[semantic_key])
            obj['content']['native_snapshot']={'owner':name,
                'native_xml_sha256':hashlib.sha256(E.tostring(node,method='c14n',exclusive=True)).hexdigest()}
            if entry.get('compatibility'):obj['content']['native_snapshot']['compatibility']=copy.deepcopy(entry['compatibility'])
            objects.append(obj)
    result={'schema_version':'0.1','revision':1,'canvas':{'width':state['source_size'][0],
        'height':state['source_size'][1],'target_width_inches':int(canvas.get('cx'))/914400,
        'unit':'px','background_rgb':[255,255,255]},'source':state['source'],
        'evidence':{'path':'source/evidence.json','sha256':digest(Path(task)/'source/evidence.json')},
        'profile':{'path':'source/profile.json','sha256':digest(Path(task)/'source/profile.json')},
        'objects':objects,'relations':copy.deepcopy(hint_scene.get('relations',[])),'prototypes':[],
        'native_authority':{'mode':'snapshot_only','pptx_sha256':digest(pptx),
            'scope':'Complete working baseline; no source/visual/font acceptance is inherited by import'}}
    for field in ('font_plan','frame_plan','semantic_composition'):
        if hint_scene.get(field):result[field]=copy.deepcopy(hint_scene[field])
    return result

def normalize_compound_hints(scene,nodes):
    """Migrate old imported compound hints only against exact actual XML."""
    changed=[]
    for obj in scene['objects']:
        contours=obj.get('content',{}).get('contours',[])
        needed=[c for c in contours if sum(q.get('op')=='moveTo' for q in c.get('commands',[]))>1 and not c.get('compound')]
        if not needed:continue
        entry=nodes.get(obj['id']);snapshot=obj['content'].get('native_snapshot',{})
        if not entry or snapshot.get('native_xml_sha256')!=hashlib.sha256(E.tostring(entry['node'],method='c14n',exclusive=True)).hexdigest():raise ValueError('Compound hint migration requires unchanged saved native XML: '+obj['id'])
        native=entry['node'].findall('p:spPr/a:custGeom/a:pathLst/a:path',NS)
        actual=[len(p.findall('a:moveTo',NS)) for p in native]
        expected=[sum(q.get('op')=='moveTo' for q in c.get('commands',[])) for c in contours]
        if actual!=expected:raise ValueError('Compound subpath count differs from actual native path')
        for contour in needed:contour['compound']=True
        changed.append(obj['id'])
    for obj in scene['objects']:
        content=obj.get('content',{});rows=content.get('rows',[])
        if not content.get('native_snapshot_table') or not rows or not any(isinstance(cell,dict) for row in rows for cell in row):continue
        if any(not isinstance(cell,dict) or set(cell)!={'text'} for row in rows for cell in row):raise ValueError('Legacy table hint has unsupported cell fields')
        entry=nodes.get(obj['id']);snapshot=content.get('native_snapshot',{})
        if not entry or snapshot.get('native_xml_sha256')!=hashlib.sha256(E.tostring(entry['node'],method='c14n',exclusive=True)).hexdigest():raise ValueError('Table hint migration requires unchanged actual native XML')
        actual=[[''.join(t.text or '' for t in cell.findall('a:txBody//a:t',NS)) for cell in row.findall('a:tc',NS)] for row in entry['node'].findall('.//a:tbl/a:tr',NS)]
        if actual!=[[cell['text'] for cell in row] for row in rows]:raise ValueError('Legacy table strings differ from actual native cells')
        content['rows']=actual;changed.append(obj['id'])
    return changed
