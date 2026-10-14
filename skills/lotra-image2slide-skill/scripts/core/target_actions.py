"""Exact replay of finite authorized math/recursive-centering transactions.

Uses the existing native writer, snapshot, renderer and whole-result checks.
Plans are program-owned and source-bound. Unrelated ZIP entries, native
properties and content are inherited exactly; saving never means acceptance.
"""
import copy
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import identity,digest,read_json,write_json,safe_path,writer
from .mathml import NS,math_zone,el

VERSION='source-target-action-1'

def _math_payload(file,bodies,canvas_size=None):
    from .source_layout_actions import _xml
    tree,nodes=_xml(file)
    for name,request in bodies.items():
        node=nodes[name]
        graphic=request.get('graphical_carrier')
        if graphic:
            from .boundary_geometry import saved_nodes
            import numpy as np
            saved=saved_nodes(file,canvas_size);entry=saved[name];left,top,width,height=graphic['source_bbox']
            points=np.array([left,top,1.]),np.array([left+width,top+height,1.])
            inv=np.linalg.inv(entry['parent_matrix']);a,b=[inv@p for p in points]
            if b[0]<=a[0] or b[1]<=a[1]:raise ValueError('Rotated/skewed graphic glyph conversion requires its explicit local mathematical frame')
            replacement=el('p:sp');nv=el('p:nvSpPr');nv.append(copy.deepcopy(node.find('.//p:cNvPr',NS)));nv.append(el('p:cNvSpPr',txBox='1'));nv.append(el('p:nvPr'));replacement.append(nv)
            props=el('p:spPr');transform=el('a:xfrm');transform.append(el('a:off',x=round(a[0]),y=round(a[1])));transform.append(el('a:ext',cx=round(b[0]-a[0]),cy=round(b[1]-a[1])));props.append(transform)
            geo=el('a:prstGeom',prst='rect');geo.append(el('a:avLst'));props.append(geo);props.append(el('a:noFill'));ln=el('a:ln');ln.append(el('a:noFill'));props.append(ln);replacement.append(props)
            body=el('p:txBody');body.append(el('a:bodyPr',lIns='0',rIns='0',tIns='0',bIns='0',anchor='ctr'));body.append(el('a:lstStyle'))
            p=el('a:p');pp=el('a:pPr',algn='ctr');pp.append(el('a:defRPr',sz=round(graphic['font_size_pt']*100)));p.append(pp);body.append(p);replacement.append(body)
            node.getparent().replace(node,replacement);node=replacement
            for carrier in set(graphic['members'])-{name}:
                old=nodes[carrier];props=old.find('p:spPr',NS)
                if props is None:raise ValueError('A graphic mathematical carrier needs native drawing properties')
                for fill in ('solidFill','gradFill','pattFill','blipFill','noFill'):
                    for v in props.findall('a:'+fill,NS):props.remove(v)
                props.append(el('a:noFill'))
                line=props.find('a:ln',NS)
                if line is None:line=el('a:ln');props.append(line)
                for v in list(line):line.remove(v)
                line.set('w','0');line.append(el('a:noFill'))
        body=node.find('p:txBody',NS)
        bodies=[body] if body is not None else node.findall('.//a:tc/a:txBody',NS)
        if not bodies:raise ValueError('Mathematical owner lacks an editable native text body')
        # Native table cells retain their tracks, merge anchors and ownership.
        old=[p for owner in bodies for p in owner.findall('a:p',NS)]
        if len(old)!=len(request['paragraphs']):raise ValueError('Preserve actual paragraph count/read order; source corrections require separate bounded text restructuring')
        for paragraph,segments in zip(old,request['paragraphs']):
            default=paragraph.find('a:pPr/a:defRPr',NS)
            first=paragraph.find('a:r/a:rPr',NS)
            ordinary=[r.find('a:rPr',NS) for r in paragraph.findall('a:r',NS) if r.find('.//{urn:lotraai:native-math-span:1}span') is None]
            if ordinary:first=next((r for r in ordinary if r is not None),first)
            props=copy.deepcopy(first if first is not None else default)
            if props is not None:
                obsolete=props.findall('a:extLst/a:ext',NS)
                for ext in obsolete:
                    if ext.get('uri')=='urn:lotraai:native-math-span:1':
                        ext.getparent().remove(ext)
                        # A migrated mathematical run must not impose its
                        # italic variable formatting on adjacent ordinary prose.
                        props.attrib.pop('i',None)
                for extlst in props.findall('a:extLst',NS):
                    if not len(extlst):props.remove(extlst)
            math_props=paragraph.find('.//m:r/a:rPr',NS)
            base=first if first is not None else math_props if math_props is not None else default
            size=float(base.get('sz',1600))/100 if base is not None else 16.
            typography=request.get('typography',{})
            from .math_typography import validate as validate_typography,apply as apply_typography
            validate_typography(typography)
            if 'font_size_pt' in typography:
                if not 4<=typography['font_size_pt']<=96:raise ValueError('Mathematical typography target must be bounded')
                size=float(typography['font_size_pt'])
            # PowerPoint can use paragraph defaults for inline math instead
            # of each token's a:rPr size. Freeze the same actual base size;
            # otherwise a genuine equation can render much larger than its
            # neighboring prose despite identical serialized token sizes.
            pp=paragraph.find('a:pPr',NS)
            if pp is None:pp=el('a:pPr');paragraph.insert(0,pp)
            defaults=pp.find('a:defRPr',NS)
            if defaults is None:defaults=el('a:defRPr');pp.append(defaults)
            defaults.set('sz',str(round(size*100)))
            color_node=base.find('a:solidFill/a:srgbClr',NS) if base is not None else None
            color=color_node.get('val') if color_node is not None else None
            for c in list(paragraph):
                if c.tag not in ('{'+NS['a']+'}pPr','{'+NS['a']+'}endParaRPr'):paragraph.remove(c)
            end=paragraph.find('a:endParaRPr',NS)
            if end is not None:paragraph.remove(end)
            for segment in segments:
                if 'ast' in segment:
                    zone=math_zone(segment['ast'],size,segment.get('math_font','Cambria Math'),inline=True,color=color,font_policy='native_math')
                    if base is not None and base.get('b','0') in ('1','true'):
                        for run in zone.findall('.//m:r',NS):
                            rp=run.find('m:rPr',NS)
                            if rp is None:rp=el('m:rPr');run.insert(0,rp)
                            sty=rp.find('m:sty',NS)
                            if sty is None:sty=el('m:sty');rp.append(sty)
                            sty.set('{'+NS['m']+'}val','b' if rp.find('m:nor',NS) is not None else 'bi')
                    span_typography={**typography,**segment.get('typography',{})}
                    paragraph.append(apply_typography(zone,span_typography))
                else:
                    r=el('a:r')
                    if props is not None:r.append(copy.deepcopy(props))
                    t=el('a:t');t.text=segment['text'];r.append(t);paragraph.append(r)
            if end is not None:paragraph.append(end)
    return E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)

def _cell_offsets(file,size,data,offsets):
    from .boundary_geometry import saved_nodes
    import numpy as np
    from .inspect import inventory
    tree=E.fromstring(data);nodes=inventory(tree)[0];actual=saved_nodes(file,size)
    for key,row in offsets.items():
        name=row['object'];entry=actual[name];table=nodes[name]['node'].find('.//a:tbl',NS);r,c=row['cell']
        cell=table.findall('a:tr',NS)[r].findall('a:tc',NS)[c]
        # Opposite margins change in opposite directions. Their sum, actual
        # available size, typography, baseline spacing and table geometry stay
        # fixed; only the painted cell content is translated.
        world=np.array([row['delta']['x'],row['delta']['y']]);linear=entry['parent_matrix'][:2,:2]
        dx,dy=np.linalg.solve(linear,world)
        body=cell.find('a:tcPr',NS)
        if body is None:raise ValueError('Native cell lacks editable cell properties')
        values={k:int(body.get(k,d)) for k,d in (('marL',91440),('marR',91440),('marT',45720),('marB',45720))}
        desired={k:round(values[k]+v) for k,v in (('marL',dx),('marR',-dx),('marT',dy),('marB',-dy))}
        if min(desired.values())<0:
            if row.get('margin_policy')!='minimal_nonnegative_envelope' or not row.get('content_size_px'):
                raise ValueError('Cell translation needs measured bounded cell-layout repair, never negative margins')
            for left,right in (('marL','marR'),('marT','marB')):
                extra=max(0,-min(desired[left],desired[right]));desired[left]+=extra;desired[right]+=extra
            cell_width=int(table.find('a:tblGrid',NS)[c].get('w'));cell_height=int(table.findall('a:tr',NS)[r].get('h'))
            content=np.abs(np.linalg.solve(linear,np.array(row['content_size_px'])))
            if cell_width-desired['marL']-desired['marR']<content[0] or cell_height-desired['marT']-desired['marB']<content[1]:
                raise ValueError('Nonnegative glyph shift would force wrapping/clipping; bounded typography/track repair remains required')
        for k,value in desired.items():body.set(k,str(value))
    return E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)


def payload(file,size,plan):
    if plan['kind']=='recursive-containment-1':
        from .neighbor_actions import _payload
        data=_payload(file,size,plan['translations'])
        if plan.get('body_sizes'):
            import numpy as np
            from .boundary_geometry import saved_nodes
            from .inspect import inventory
            tree=E.fromstring(data);nodes=inventory(tree)[0];saved=saved_nodes(file,size)
            for name,frame in plan['body_sizes'].items():
                entry=saved[name];x,y,w,h=frame;inverse=np.linalg.inv(entry['parent_matrix']);lo=inverse@np.array([x,y,1]);hi=inverse@np.array([x+w,y+h,1])
                xf=nodes[name]['node'].find('p:spPr/a:xfrm',NS);off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
                off.set('x',str(round(lo[0])));off.set('y',str(round(lo[1])));ext.set('cx',str(round(hi[0]-lo[0])));ext.set('cy',str(round(hi[1]-lo[1])))
            data=E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)
        if plan.get('paragraph_alignment'):
            tree=E.fromstring(data)
            from .inspect import inventory
            nodes=inventory(tree)[0]
            for name,value in plan['paragraph_alignment'].items():
                if value not in ('l','ctr','r'):raise ValueError('Known native paragraph alignment required')
                for paragraph in nodes[name]['node'].findall('.//a:p',NS):
                    prop=paragraph.find('a:pPr',NS)
                    if prop is None:prop=el('a:pPr');paragraph.insert(0,prop)
                    prop.set('algn',value)
            data=E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)
        if plan.get('lane_typography'):
            tree=E.fromstring(data)
            from .inspect import inventory
            nodes=inventory(tree)[0]
            for name,typ in plan['lane_typography'].items():
                size=str(round(typ['font_size_pt']*100));node=nodes[name]['node']
                for prop in node.findall('.//a:rPr',NS)+node.findall('.//a:defRPr',NS)+node.findall('.//a:endParaRPr',NS):prop.set('sz',size)
            data=E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)
        return _cell_offsets(file,size,data,plan['cell_offsets']) if plan.get('cell_offsets') else data
    if plan['kind']=='office-math-contract-1':return _math_payload(file,plan['math_bodies'],size)
    raise ValueError('Finite source-target writer does not execute arbitrary code')

def execute(task,state,candidate,plan,request):
    from . import agent_runtime as a
    from .execution_contract import resource,_implementation
    from .native_snapshot import snapshot
    if not candidate.get('render') or not candidate.get('preview'):
        raise ValueError('Complete the current actual render before planning another native layout/content transaction')
    source_contract=resource(task,plan['source_contract'])
    before=resource(task,candidate['pptx']);data=payload(before,state['source_size'],plan)
    with ZipFile(before) as z:
        if z.read('ppt/slides/slide1.xml')==data:raise ValueError('No effective finite action; do not create a fake improvement')
    branch=identity({'source_contract':plan['source_contract'],'kind':plan['kind'],'scope':plan['write_set']})
    attempts=state.get('source_target_attempts',[])
    if any(r['baseline']['pptx']['sha256']==candidate['pptx']['sha256'] and r['branch']==branch for r in attempts):raise ValueError('Repeated unchanged source-target action requires a different diagnosis')
    contract={'schema':VERSION,'plan':plan,'request':request,'baseline':copy.deepcopy(candidate),
        'source_hash':state['source']['sha256'],'implementation':_implementation(),
        'baseline_mattes':copy.deepcopy(state.get('neighbor_mattes',{})),
        'baseline_cell_mattes':copy.deepcopy(state.get('cell_mattes',{}))}
    folder=task/'versions'/('target-'+identity(contract)[:18]);folder.mkdir(parents=True,exist_ok=True);output=folder/'drawing.pptx'
    from .neighbor_actions import _same_zip
    if output.exists():
        if not _same_zip(before,output,data):raise ValueError('Uncommitted output differs from exact program replay; preserve it')
    else:
        with ZipFile(before) as z,ZipFile(output,'x',ZIP_DEFLATED,compresslevel=9) as out:
            for info in z.infolist():out.writestr(info,data if info.filename=='ppt/slides/slide1.xml' else z.read(info.filename))
    scene=snapshot(task,state,output,read_json(resource(task,candidate['scene'])));scene['revision']=state['revision']+1
    sf=folder/'scene.json';write_json(sf,scene);cf=folder/'Contract.json';write_json(cf,contract)
    current=copy.deepcopy(candidate);current.update(pptx=a._file(task,output),scene=a._file(task,sf),revision=scene['revision'],allowed=plan['write_set'])
    current['prior_render']=current.pop('render');current.pop('preview',None);current['reason']={'kind':VERSION,'contract':a._file(task,cf)}
    from .neighbor_capture import transport
    contract['owner_transport']=transport(task,state,current,candidate,contract['baseline_mattes'])
    write_json(cf,contract)
    # Transport adds evidence to the contract. Freeze its final bytes before
    # binding either candidate.reason or the execution record to that file.
    current['reason']={'kind':VERSION,'contract':a._file(task,cf)}
    record={'schema':VERSION,'branch':branch,'candidate':current['pptx']['sha256'],'baseline':copy.deepcopy(candidate),
        'contract':a._file(task,cf),'status':'SAVED_REQUIRES_ACTUAL_RENDER_AND_CURRENT_WHOLE_CHECKS','write_set':plan['write_set'],'check_set':plan['check_set']}
    with writer(task):
        state.setdefault('source_target_attempts',[]).append(record);state.update(active_candidate=current,scene=current['scene'],revision=scene['revision'],stage='host_render',packet=None)
        state.pop('acceptance',None);state.pop('quality_result',None);state.pop('office_math_behavior',None)
        a._event(task,'finite_source_target_action_saved',record);a._save(task,state)
    return record

def guard(task,state,candidate,approved,_chain_only=False):
    from .execution_contract import resource
    from .neighbor_actions import _same_zip
    record=next((r for r in state.get('source_target_attempts',[]) if r['candidate']==candidate['pptx']['sha256']),None)
    if not record:return {'passed':False,'objects':[],'reason':'Missing original-bound finite target transaction'}
    c=read_json(resource(task,record['contract']));baseline=c['baseline'];plan=c['plan']
    source=read_json(resource(task,plan['source_contract']))
    if source['source_hash']!=state['source']['sha256']:raise ValueError('Wrong original target transaction')
    if plan['source_contract']!=state.get('recursive_containment' if plan['kind']=='recursive-containment-1' else 'office_math_contract'):
        history='containment_history' if plan['kind']=='recursive-containment-1' else 'office_math_history'
        if plan['source_contract'] not in state.get(history,[]):raise ValueError('Unregistered original target contract; replay cannot invent source authority')
    replay_state=copy.deepcopy(state)
    replay_state['_historical_target_replay']=True
    replay_state['neighbor_mattes']=c.get('baseline_mattes',{})
    replay_state['cell_mattes']=c.get('baseline_cell_mattes',{})
    if plan['kind']=='recursive-containment-1':
        from .recursive_containment import repair_plan,spacing_plan
        replay_state['recursive_containment']=plan['source_contract']
        generated=spacing_plan(task,replay_state,baseline,c['request']) if c['request'].get('spacing_relations') else repair_plan(task,replay_state,baseline,c['request'])
        keys=('container','containers','spacing_relations','alignment_tracks','paragraph_alignment','lane_typography','translations','cell_offsets','body_sizes','write_set','check_set','protected_set')
    else:
        from .office_math_contract import repair_plan
        replay_state['office_math_contract']=plan['source_contract']
        generated=repair_plan(task,replay_state,baseline,c['request'])
        keys=('math_bodies','write_set','check_set','protected_set')
    if any(generated.get(k,{})!=plan.get(k,{}) for k in keys):raise ValueError('Stored action differs from the program-computed original-bound plan')
    replay=payload(resource(task,baseline['pptx']),state['source_size'],plan)
    passed=_same_zip(resource(task,baseline['pptx']),resource(task,candidate['pptx']),replay)
    prior={'passed':True,'objects':[]}
    if baseline['pptx']['sha256']!=approved['pptx']['sha256']:
        from .source_layout_actions import guard as prior_guard
        prior=prior_guard(task,state,baseline,approved,_chain_only=True);passed &= prior['passed']
    names=set(plan['write_set'])|set(prior.get('objects',[]))
    return {'passed':bool(passed),'objects':sorted(names),'method':VERSION,'contract':record['contract'],
        'protected':'Exact ZIP and native property replay; transform-only centering preserves every sibling relative gap, order and baseline. Math changes only source-owned paragraph content.',
        'check_set':plan['check_set'],'requires_current_target_recheck':True,'source_function_items':prior.get('source_function_items',[])}
