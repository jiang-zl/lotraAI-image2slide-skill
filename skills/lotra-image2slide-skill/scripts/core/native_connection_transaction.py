"""Bounded native connection construction, nonpainted ports and replay proof.

The transaction preserves native IDs, resources and unrelated XML. Native
ports follow their semantic group's transform; moving a physical child is
detected by the next contour check and requires program redocking.
"""
import copy,json,math
import numpy as np
from lxml import etree as E
from zipfile import ZipFile,ZIP_DEFLATED
from .common import identity,digest,read_json,write_json,safe_path,writer
from .mathml import NS

PREFIX='connection_port__'

def anchor_name(connection,port):return PREFIX+identity([connection,port['object'],port['end']])[:22]

def anchor_metadata(node):
    prop=node.find('p:nvSpPr/p:cNvPr',NS)
    if prop is None or not prop.get('name','').startswith(PREFIX):return None
    try:return json.loads(prop.get('descr',''))
    except (TypeError,ValueError):return None

def verify_anchor(entry):
    node=entry['node'];meta=anchor_metadata(node)
    props=node.find('p:spPr',NS)
    if not meta or meta.get('kind')!='program_connection_port' or props is None:return False
    if set(E.QName(c).localname for c in node)!={'nvSpPr','spPr'} or set(E.QName(c).localname for c in props)!={'xfrm','custGeom','noFill','ln'}:return False
    if meta.get('object') is None or meta.get('end') not in (0,1) or node.find('p:nvSpPr/p:cNvPr',NS).get('name')!=anchor_name(meta['connection'],meta):return False
    site=props.find('a:custGeom/a:cxnLst/a:cxn/a:pos',NS)
    if props.find('a:noFill',NS) is None or props.find('a:ln/a:noFill',NS) is None or node.find('.//a:t',NS) is not None or site is None:return False
    extent=props.find('a:xfrm/a:ext',NS)
    if extent is None:return False
    try:
        error=max(abs(float(site.get(k))-float(extent.get(e))/2) for k,e in (('x','cx'),('y','cy')))
    except (ValueError,TypeError):return False
    # a:cxn/a:pos uses shape transform coordinates (EMU), not the
    # independently scaled path w/h coordinate system. Half an EMU is only
    # integer serialization precision; an out-of-bounds legacy site fails.
    return error<=.5 and max(entry['frame'][2:])<=.101

def same_original_connection_facts(before,after):
    """Only recursion/coverage bookkeeping can change an existing port basis.

    Every actual original stroke, text, pair candidate, observation parameter
    and measurement stays exact. A different target/endpoint is checked again
    against the current connection contract and cannot use this proof.
    """
    if before.get('source_hash')!=after.get('source_hash'):return False
    def facts(graph):
        value=copy.deepcopy(graph)
        for key in ('source_recursion_hash','region_coverage'):value.pop(key,None)
        observation=value.get('original_observation',{})
        for key in ('source_recursion_hash','region_coverage'):observation.pop(key,None)
        return value
    return facts(before)==facts(after)


def derived_receipt(task,state,candidate,name,nodes):
    from .connection_geometry import _load_contract,line
    try:
        entry=nodes[name];meta=anchor_metadata(entry['node'])
        if not verify_anchor(entry):raise ValueError('Unverified derived native port')
        lineage=None
        if meta['source_graph']!=state['source_connection_graph']['sha256']:
            from .execution_contract import resource
            prior=next((r for r in state.get('source_connection_graph_history',[]) if r['sha256']==meta['source_graph']),None)
            if not prior or not same_original_connection_facts(read_json(resource(task,state['source_connection_graph'])),read_json(resource(task,prior))):
                raise ValueError('Derived port original facts changed; a new finite docking transaction is required')
            lineage={'prior':prior,'current':state['source_connection_graph'],'proof':'Exact unchanged original connection facts; recursion/coverage bookkeeping only'}
        contract=_load_contract(task,state)
        row=next(r for r in contract['items'] if r['id']==meta['connection'])
        port=next(p for p in row['ports'] if p['object']==meta['object'] and p['end']==meta['end'])
        if port['target']!=meta['target'] or port['semantic_owner']!=meta['semantic_owner'] or port['profile']!=meta['profile']:raise ValueError('Derived port disagrees with frozen source contract')
        endpoint=np.array(line(nodes[meta['object']])['points'][meta['end']]);error=float(np.linalg.norm(anchor_center(entry)-endpoint))
        return {'passed':error<=.15 and entry['parent_name']==nodes[meta['target']]['parent_name'],
                'status':'PROGRAM_DERIVED_NONPAINTED_NATIVE_PORT','endpoint_error_px':error,'source_target':port['target'],'source_graph_lineage':lineage,
                'scope':'Nonpainted connection site is checked as a program artifact; the true terminal independently checks its physical boundary/gap and native binding.'}
    except (ValueError,KeyError,TypeError,StopIteration) as error:return {'passed':False,'reason':str(error)}

def anchor_center(entry):return (entry['matrix']@np.array([.5,.5,1]))[:2]

def _set_points(node,entry,points):
    props=node.find('p:spPr',NS);xf=props.find('a:xfrm',NS)
    local=np.c_[points,np.ones(2)]@np.linalg.inv(entry['parent_matrix']).T
    x0,y0=local[0,:2];x1,y1=local[1,:2]
    for attr in ('rot','flipH','flipV'):xf.attrib.pop(attr,None)
    if x1<x0:xf.set('flipH','1')
    if y1<y0:xf.set('flipV','1')
    off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
    for key,v in [('x',min(x0,x1)),('y',min(y0,y1))]:off.set(key,str(round(v)))
    for key,v in [('cx',abs(x1-x0)),('cy',abs(y1-y0))]:ext.set(key,str(max(1,round(v))))

def _set_filled(node,entry,points):
    props=node.find('p:spPr',NS);preset=props.find('a:prstGeom',NS)
    if preset is None or preset.get('prst') not in ('rightArrow','leftArrow','upArrow','downArrow'):raise ValueError('Filled curve/polygon requires its specific source function constructor')
    local=np.c_[points,np.ones(2)]@np.linalg.inv(entry['parent_matrix']).T
    xf=props.find('a:xfrm',NS);off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
    if preset.get('prst') in ('rightArrow','leftArrow'):
        if abs(local[0,1]-local[1,1])>1:raise ValueError('Source filled horizontal axis must be horizontal in parent space')
        height=int(ext.get('cy'));off.set('x',str(round(min(local[:,0]))));off.set('y',str(round(local[:,1].mean()-height/2)));ext.set('cx',str(round(abs(local[1,0]-local[0,0]))))
    else:
        if abs(local[0,0]-local[1,0])>1:raise ValueError('Source filled vertical axis must be vertical in parent space')
        width=int(ext.get('cx'));off.set('x',str(round(local[:,0].mean()-width/2)));off.set('y',str(round(min(local[:,1]))));ext.set('cy',str(round(abs(local[1,1]-local[0,1]))))

def _set_curve(node,entry,points):
    """Editable native freeform Bezier, never a picture/custom connector.

    Office custom-geometry connectors are not portable. A freeform shape
    preserves native edit-points and arrow styles; physical attachment is
    audited geometrically rather than claimed as a draggable connector.
    """
    if len(points) not in (3,4):raise ValueError('One quadratic/cubic source segment required')
    local=(np.c_[points,np.ones(len(points))]@np.linalg.inv(entry['parent_matrix']).T)[:,:2]
    low=local.min(0);size=local.max(0)-low
    if min(size)<=1:raise ValueError('Degenerate native curve bounds')
    if E.QName(node).localname=='cxnSp':
        old=node.find('p:nvCxnSpPr',NS);nv=E.Element('{'+NS['p']+'}nvSpPr')
        nv.append(copy.deepcopy(old.find('p:cNvPr',NS)));E.SubElement(nv,'{'+NS['p']+'}cNvSpPr');nv.append(copy.deepcopy(old.find('p:nvPr',NS)))
        node.replace(old,nv);node.tag='{'+NS['p']+'}sp'
    props=node.find('p:spPr',NS);xf=props.find('a:xfrm',NS)
    for attr in ('rot','flipH','flipV'):xf.attrib.pop(attr,None)
    for key,v in zip(('x','y'),low):xf.find('a:off',NS).set(key,str(round(v)))
    for key,v in zip(('cx','cy'),size):xf.find('a:ext',NS).set(key,str(round(v)))
    for key in ('prstGeom','custGeom'):
        old=props.find('a:'+key,NS)
        if old is not None:props.remove(old)
    geom=E.Element('{'+NS['a']+'}custGeom');props.insert(1,geom)
    for key in ('avLst','gdLst','ahLst','cxnLst'):E.SubElement(geom,'{'+NS['a']+'}'+key)
    E.SubElement(geom,'{'+NS['a']+'}rect',l='l',t='t',r='r',b='b')
    path=E.SubElement(E.SubElement(geom,'{'+NS['a']+'}pathLst'),'{'+NS['a']+'}path',w='100000',h='100000',fill='none',stroke='1',extrusionOk='0')
    coords=(local-low)/size*100000
    for key,values in (('moveTo',coords[:1]),('quadBezTo' if len(points)==3 else 'cubicBezTo',coords[1:])):
        command=E.SubElement(path,'{'+NS['a']+'}'+key)
        for q in values:E.SubElement(command,'{'+NS['a']+'}pt',x=str(round(q[0])),y=str(round(q[1])))

def _set_polyline(node,entry,points):
    """Preserve bends with real editable Office elbow presets and handles.

    Office rejects some custom connector path encodings at document open.
    An orthogonal 2..5 segment path has an exact preset representation.
    """
    local=np.c_[points,np.ones(len(points))]@np.linalg.inv(entry['parent_matrix']).T
    local=local[:,:2];first=local[1]-local[0];angle=math.atan2(first[1],first[0])
    rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    oriented=local@rotation;start,end=oriented[0],oriented[-1];delta=end-start
    count=len(points)-1
    if count not in (2,3,4,5) or min(abs(delta))<1:raise ValueError('Observed elbow needs a registered nondegenerate 2..5 segment native preset')
    for i,(p,q) in enumerate(zip(oriented,oriented[1:])):
        if abs((q-p)[1 if i%2==0 else 0])>3:raise ValueError('Nonorthogonal path needs its native segment/curve constructor')
    extent=np.abs(delta);center=(start+end)/2@rotation.T
    props=node.find('p:spPr',NS);xf=props.find('a:xfrm',NS)
    for attr in ('rot','flipH','flipV'):xf.attrib.pop(attr,None)
    if abs(angle)>1e-9:xf.set('rot',str(round(math.degrees(angle)%360*60000)))
    if delta[0]<0:xf.set('flipH','1')
    if delta[1]<0:xf.set('flipV','1')
    for key,value in zip(('x','y'),center-extent/2):xf.find('a:off',NS).set(key,str(round(value)))
    for key,value in zip(('cx','cy'),extent):xf.find('a:ext',NS).set(key,str(round(value)))
    old=props.find('a:prstGeom',NS)
    if old is None:old=props.find('a:custGeom',NS)
    index=list(props).index(old) if old is not None else 1
    if old is not None:props.remove(old)
    geom=E.Element('{'+NS['a']+'}prstGeom',prst='bentConnector'+str(count));props.insert(index,geom)
    av=E.SubElement(geom,'{'+NS['a']+'}avLst');adjustments={}
    if count>=3:adjustments['adj1']=(oriented[1,0]-start[0])/delta[0]*100000
    if count>=4:adjustments['adj2']=(oriented[2,1]-start[1])/delta[1]*100000
    if count>=5:adjustments['adj3']=(oriented[3,0]-start[0])/delta[0]*100000
    for key,value in adjustments.items():
        if not -2147483647<=value<=2147483647:raise ValueError('Elbow adjustment exceeds Office guide range')
        E.SubElement(av,'{'+NS['a']+'}gd',name=key,fmla='val '+str(round(value)))

def _new_anchor(name,native_id,center,target_entry,meta,construction_version=5):
    node=E.Element('{'+NS['p']+'}sp')
    nv=E.SubElement(node,'{'+NS['p']+'}nvSpPr')
    E.SubElement(nv,'{'+NS['p']+'}cNvPr',id=str(native_id),name=name,descr=json.dumps(meta,sort_keys=True,separators=(',',':')))
    E.SubElement(nv,'{'+NS['p']+'}cNvSpPr');E.SubElement(nv,'{'+NS['p']+'}nvPr')
    props=E.SubElement(node,'{'+NS['p']+'}spPr');xf=E.SubElement(props,'{'+NS['a']+'}xfrm')
    parent=target_entry['parent_matrix'];local=np.linalg.inv(parent)@np.array([*center,1])
    delta=np.linalg.inv(parent)@np.array([.1,.1,0]);w,h=np.abs(delta[:2])
    E.SubElement(xf,'{'+NS['a']+'}off',x=str(round(local[0]-w/2)),y=str(round(local[1]-h/2)))
    cx,cy=max(1,round(w)),max(1,round(h))
    E.SubElement(xf,'{'+NS['a']+'}ext',cx=str(cx),cy=str(cy))
    geom=E.SubElement(props,'{'+NS['a']+'}custGeom')
    for key in ('avLst','gdLst','ahLst'):E.SubElement(geom,'{'+NS['a']+'}'+key)
    lst=E.SubElement(geom,'{'+NS['a']+'}cxnLst');site=E.SubElement(lst,'{'+NS['a']+'}cxn',ang='0')
    E.SubElement(site,'{'+NS['a']+'}pos',x=str(round(cx/2)) if construction_version>=6 else '50000',y=str(round(cy/2)) if construction_version>=6 else '50000')
    E.SubElement(geom,'{'+NS['a']+'}rect',l='0',t='0',r=str(cx) if construction_version>=6 else '100000',b=str(cy) if construction_version>=6 else '100000')
    paths=E.SubElement(geom,'{'+NS['a']+'}pathLst');path=E.SubElement(paths,'{'+NS['a']+'}path',w='100000',h='100000')
    move=E.SubElement(path,'{'+NS['a']+'}moveTo');E.SubElement(move,'{'+NS['a']+'}pt',x='0',y='0')
    for x,y in [('100000','0'),('100000','100000'),('0','100000')]:
        op=E.SubElement(path,'{'+NS['a']+'}lnTo');E.SubElement(op,'{'+NS['a']+'}pt',x=x,y=y)
    E.SubElement(path,'{'+NS['a']+'}close')
    E.SubElement(props,'{'+NS['a']+'}noFill');ln=E.SubElement(props,'{'+NS['a']+'}ln');E.SubElement(ln,'{'+NS['a']+'}noFill')
    return node

def _intersection(points,index,domain,size,construction_version=2):
    from shapely.geometry import LineString,Point
    origin=points[1-index];wanted=points[index];d=wanted-origin;length=np.linalg.norm(d)
    if length<.001:raise ValueError('Zero terminal docking direction')
    d/=length;hit=LineString([origin,origin+d*(length+max(size)*2)]).intersection(domain.boundary)
    found=list(hit.geoms) if hasattr(hit,'geoms') else [hit]
    found=[p for p in found if p.geom_type=='Point']
    if not found:raise ValueError('Selected physical port is not intersected by original-supported direction')
    if construction_version==1:chosen=min(found,key=lambda p:p.distance(Point(wanted)))
    else:
        nearest=min(p.distance(Point(wanted)) for p in found)
        tied=[p for p in found if p.distance(Point(wanted))<=nearest+1e-7]
        chosen=min(tied,key=lambda p:p.distance(Point(origin)))
    return np.array(chosen.coords[0]),d

def _gap_point(points,index,domain,interval,size):
    from shapely.geometry import Point
    point=points[index];gap=Point(point).distance(domain)
    if not domain.contains(Point(point)) and interval[0]<=gap<=interval[1]:return point.copy()
    goal=sum(interval)/2;axis=point-points[1-index];axis/=np.linalg.norm(axis)
    # An intentional gap need not point through the object's contour. Search
    # along the fixed source axis; do not invent a boundary intersection.
    steps=np.linspace(-max(size)*2,max(size)*2,1025);values=[Point(point+axis*t).distance(domain)-goal for t in steps]
    brackets=[(steps[i],steps[i+1]) for i in range(len(steps)-1) if values[i]*values[i+1]<=0]
    if not brackets:raise ValueError('Original axis cannot preserve the declared intentional gap')
    roots=[]
    for lo,hi in brackets:
        f=Point(point+axis*lo).distance(domain)-goal
        for _ in range(48):
            mid=(lo+hi)/2;fm=Point(point+axis*mid).distance(domain)-goal
            if f*fm<=0:hi=mid
            else:lo=mid;f=fm
        roots.append((lo+hi)/2)
    return point+axis*min(roots,key=abs)

def construct(task,state,baseline,contract,rows,output,construction_version=5):
    from . import connection_geometry as cg
    from .boundary_geometry import saved_nodes
    from .inspect import xml,inventory
    from shapely.geometry import Point
    file=safe_path(task,baseline['pptx']['path']);tree=xml(file);native,_=inventory(tree)
    nodes=saved_nodes(file,state['source_size']);next_id=max(int(v['id']) for v in native.values())+1
    changes=[];anchors=[];allowed=set()
    for row in rows:
        if row['mode'] not in ('independent','same_straight'):raise ValueError('Select a registered curve/branch constructor; straight operator cannot substitute')
        kinds={n:cg.line(nodes[n],row.get('terminal_sites',{}).get(n))['path_kind'] for n in row['objects']}
        source_segments=row.get('canonical_curve',{}).get('segments',[])
        source_curve=len(source_segments)==1 and len(source_segments[0]) in (3,4)
        filled=all(k=='filled_arrow' for k in kinds.values())
        if filled and (len(row['objects'])!=1 or any(p['profile']!='free' for p in row['ports'])):raise ValueError('Filled-arrow attached ports require a specific native polygon/path constructor')
        if source_curve:
            if len(row['objects'])!=1 or row['mode']!='independent':raise ValueError('Independent finite source curve required')
        elif not filled and any(nodes[n]['tag']!='cxnSp' or kinds[n] not in ('straight','polyline') for n in row['objects']):raise ValueError('Registered straight/polyline or finite preset filled-arrow constructor required')
        path={name:np.array(row['source_paths'][name],float) for name in row['objects']}
        if source_curve:path[row['objects'][0]]=np.array(source_segments[0],float)
        for name,kind in kinds.items():
            if kind=='polyline':
                if len(row['objects'])!=1 or row['mode']!='independent':raise ValueError('Polyline continuation needs its registered common-path constructor')
                segments=row.get('canonical_curve',{}).get('segments',[])
                if not segments or any(len(p)!=2 for p in segments):raise ValueError('Observed straight bend segments required')
                if any(np.linalg.norm(np.array(a[-1])-np.array(b[0]))>.01 for a,b in zip(segments,segments[1:])):raise ValueError('Discontinuous source polyline')
                path[name]=np.array([segments[0][0]]+[p[-1] for p in segments],float)
        if row.get('axis_policy')=='between_physical_ports':
            if len(row['objects'])!=1 or len(row['ports'])!=2 or any(p['profile'] not in ('boundary_touch','marker_center_on_boundary') for p in row['ports']):raise ValueError('Between-port axis requires one straight semantic edge with two observed contact owners')
            ports=sorted(row['ports'],key=lambda p:p['end'])
            path[row['objects'][0]]=np.array([cg._boundary(nodes[p['target']]).centroid.coords[0] for p in ports])
        if row['mode']=='same_straight':
            start,end=np.array(row['canonical_points']);d=end-start;d/=np.linalg.norm(d)
            for name,points in path.items():path[name]=np.array([start+np.dot(p-start,d)*d for p in points])
        # A source-fitted common axis is fixed. Only true endpoints dock;
        # occlusion cuts are trimmed against the actual opaque text box.
        for port in row['ports']:
            name,index=port['object'],port['end'];full=path[name]
            points=full if len(full)==2 else full[:2] if index==0 else full[-2:]
            if port['profile']=='occlusion_cut':
                domain=cg._boundary(nodes[port['occluder']]);dock,d=_intersection(points,index,domain,state['source_size'],construction_version)
                points[index]=dock;continue
            if port['profile']=='free':continue
            domain=cg._boundary(nodes[port['target']])
            if port['profile']=='intentional_gap':dock=_gap_point(points,index,domain,port['gap_interval'],state['source_size'])
            else:
                try:dock,d=_intersection(points,index,domain,state['source_size'],construction_version)
                except ValueError as error:raise ValueError(str(error)+' '+name+':'+str(index)+' '+port['target']+' points='+str(points.tolist())) from error
            if port['profile']=='inside_port':dock+=d*sum(port['depth_interval'])/2
            elif port['profile']=='circle_half_embedded':
                center,radius=cg._circle_marker(nodes[port['marker_object']],port['radius_px']);lo,hi=-radius,radius
                for _ in range(40):
                    mid=(lo+hi)/2;disk=Point(dock+d*mid).buffer(radius,resolution=256);ratio=disk.intersection(domain).area/disk.area
                    if ratio<.5:lo=mid
                    else:hi=mid
                dock+=d*(lo+hi)/2
                marker=port['marker_object'];xf=native[marker]['node'].find('p:spPr/a:xfrm',NS);off=xf.find('a:off',NS)
                delta=np.linalg.inv(nodes[marker]['parent_matrix'])@np.array([*(dock-center),0])
                for axis,amount in zip(('x','y'),delta[:2]):off.set(axis,str(round(int(off.get(axis))+amount)))
                allowed.add(marker);changes.append({'object':marker,'kind':'circle_marker','before':center.tolist(),'after':dock.tolist()})
            points[index]=dock
            name_anchor=anchor_name(row['id'],port);target=port['target'];parent_name=nodes[target]['parent_name']
            meta={'kind':'program_connection_port','connection':row['id'],'object':name,'end':index,
                'target':target,'semantic_owner':port['semantic_owner'],'profile':port['profile'],
                'source_hash':state['source']['sha256'],'source_graph':contract['source_graph']['sha256']}
            if name_anchor in native:
                prior=native[name_anchor]['node'];prior.getparent().remove(prior);native_id=int(native[name_anchor]['id'])
            else:native_id=next_id;next_id+=1
            node=_new_anchor(name_anchor,native_id,dock,nodes[target],meta,construction_version)
            parent=native[parent_name]['node'] if parent_name else tree.find('p:cSld/p:spTree',NS)
            parent.append(node)
            nv=native[name]['node'].find('p:nvCxnSpPr/p:cNvCxnSpPr',NS);key='stCxn' if index==0 else 'endCxn'
            if nv is not None:
                existing=nv.find('a:'+key,NS)
                if existing is not None:nv.remove(existing)
                E.SubElement(nv,'{'+NS['a']+'}'+key,id=str(native_id),idx='0')
            anchors.append({'object':name_anchor,'parent':parent_name,'center':dock.tolist(),'meta':meta});allowed.add(name_anchor)
        for name,points in path.items():
            actual=cg.line(nodes[name],row.get('terminal_sites',{}).get(name));node=native[name]['node']
            if filled:_set_filled(node,nodes[name],points)
            else:
                if source_curve:_set_curve(node,nodes[name],points)
                elif kinds[name]=='polyline':_set_polyline(node,nodes[name],points)
                else:_set_points(node,nodes[name],points)
                ln=node.find('p:spPr/a:ln',NS)
                for key,marker in row['expected_markers'][name].items():
                    el=ln.find('a:'+key,NS)
                    if el is None:el=E.SubElement(ln,'{'+NS['a']+'}'+key)
                    el.set('type',marker)
            # Remove a binding only for a source-confirmed free end or cut.
            for port in [p for p in row['ports'] if p['object']==name and p['profile'] in ('free','occlusion_cut')]:
                nv=node.find('p:nvCxnSpPr/p:cNvCxnSpPr',NS);el=nv.find('a:'+('stCxn' if port['end']==0 else 'endCxn'),NS) if nv is not None else None
                if nv is not None and el is not None:nv.remove(el)
            changes.append({'object':name,'before':actual['points'],'after':[points[0].tolist(),points[-1].tolist()],
                'path_vertices':points.tolist(),'markers':row['expected_markers'][name]});allowed.add(name)
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(file) as old,ZipFile(output,'w',ZIP_DEFLATED) as new:
        for part in old.namelist():new.writestr(part,E.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True) if part=='ppt/slides/slide1.xml' else old.read(part))
    # Semantic parent frame and every unmodified leaf retain exact XML.
    before,_=inventory(xml(file));after,_=inventory(xml(output))
    new_names=set(after)-set(before)
    if not new_names<=allowed or set(before)-set(after):raise ValueError('Unplanned native object change')
    def own(node):
        c=copy.deepcopy(node)
        if E.QName(c).localname=='grpSp':
            for child in list(c):
                if E.QName(child).localname in ('sp','cxnSp','pic','grpSp','graphicFrame'):c.remove(child)
        return E.tostring(c,method='c14n')
    for name in set(before)-allowed:
        if before[name]['parent']!=after[name]['parent'] or own(before[name]['node'])!=own(after[name]['node']):raise ValueError('Protected native XML changed: '+name)
    with ZipFile(file) as a,ZipFile(output) as b:
        if a.namelist()!=b.namelist() or any(a.read(p)!=b.read(p) for p in a.namelist() if p!='ppt/slides/slide1.xml'):raise ValueError('Protected package resources changed')
    return {'changes':changes,'anchors':anchors,'allowed':sorted(allowed),'protected_native_xml':True,'protected_resources':True}

def execute(task,request):
    from . import agent_runtime as a
    task,state=a._state(task);baseline=state.get('active_candidate') or state['selected']
    if request.get('source_hash')!=state['source']['sha256'] or request.get('expected_baseline_sha256')!=baseline['pptx']['sha256'] or not baseline.get('render'):raise ValueError('Exact rendered baseline required')
    from .connection_geometry import _load_contract
    contract=_load_contract(task,state);wanted=set(request.get('connections',[]));rows=[r for r in contract['items'] if r['id'] in wanted]
    if not rows or len(rows)!=len(wanted):raise ValueError('Bounded known logical connection set required')
    directory=task/'versions'/('connection-'+identity([baseline['pptx'],state['connection_contract'],sorted(wanted),6])[:18])
    output=directory/'drawing.pptx';proof=construct(task,state,baseline,contract,rows,output,construction_version=6)
    from .boundary_geometry import saved_nodes
    saved=saved_nodes(output,state['source_size'])
    scene=read_json(safe_path(task,baseline['scene']['path']));by_id={o['id']:o for o in scene['objects']}
    from .native_snapshot import normalize_compound_hints
    normalize_compound_hints(scene,saved)
    for change in proof['changes']:
        obj=by_id[change['object']];obj['content'].pop('native_snapshot',None)
        if change.get('kind')=='circle_marker':obj['bbox'][:2]=(np.array(obj['bbox'][:2])+np.array(change['after'])-np.array(change['before'])).tolist()
        else:
            obj['content']['points']=change['after'];obj['content']['start_marker']=change['markers']['headEnd'];obj['content']['end_marker']=change['markers']['tailEnd']
            obj['bbox']=saved[change['object']]['frame']
            if obj['render_type']=='connector':
                for key in ('source','target','source_site','target_site'):obj['content'].pop(key,None)
                obj['content']['source_semantic_bindings']=[p for r in rows for p in r['ports'] if p['object']==obj['id']]
    for anchor in proof['anchors']:
        x,y=anchor['center'];obj={'id':anchor['object'],'semantic_type':'program_connection_port','render_type':'shape',
            'parent':anchor['parent'],'bbox':[x-.05,y-.05,.1,.1],'layer':999,'content':{'preset':'rect','fill':None,'stroke':None},
            'style':{'fill':None,'line':None,'rotation':0},'versions':copy.deepcopy(scene['objects'][0]['versions']),
            'locks':{k:False for k in ('content','structure','style','placement')},'evidence_status':'observed'}
        if obj['id'] in by_id:by_id[obj['id']].update(obj)
        else:scene['objects'].append(obj)
    from .native_snapshot import snapshot
    scene=snapshot(task,state,output,scene)
    scene_file=directory/'scene.json';write_json(scene_file,scene)
    candidate=copy.deepcopy(baseline)
    for key in ('preview','render','preview_pdf','font_delivery'):candidate.pop(key,None)
    candidate.update(pptx=a._file(task,output),scene=a._file(task,scene_file),allowed={n:['replace_component'] for n in proof['allowed']},reason={'kind':'connection_geometry','id':directory.name})
    from .connection_geometry import report
    measured=report(task,state,candidate)
    targeted=[r for r in measured.get('items',[]) if r['id'] in wanted]
    if len(targeted)!=len(wanted) or not all(r['passed'] for r in targeted):
        write_json(directory/'construction-check.json',measured)
        raise ValueError('Constructed connection geometry did not satisfy every targeted original obligation')
    from .semantic_composition import guard_saved
    candidate['semantic_composition_guard']=guard_saved(task,state,output)
    from .neighbor_capture import transport
    prior_mattes=copy.deepcopy(state.get('neighbor_mattes',{}))
    owner_transport=transport(task,state,candidate,baseline,prior_mattes)
    record={'candidate':candidate['pptx']['sha256'],'baseline':copy.deepcopy(baseline),'contract':state['connection_contract'],'construction_version':6,
            'baseline_mattes':prior_mattes,'owner_transport':owner_transport,
            'source_graph':state['source_connection_graph'],'connections':sorted(wanted),'proof':proof,'allowed':candidate['allowed']}
    with writer(task):
        state.setdefault('connection_attempts',[]).append(record);state['active_candidate']=candidate;state['scene']=candidate['scene'];state['stage']='host_render';state['packet']=None
        state.pop('acceptance',None);state.pop('quality_result',None);a._save(task,state)
    return {'status':'SAVED_REQUIRES_ACTUAL_RENDER','candidate':candidate['pptx'],'changes':proof['changes'],'native_ports':proof['anchors']}

def rollback_failed_export(task,failure_ref):
    """Restore the exact preceding rendered transaction on a bound host failure."""
    from . import agent_runtime as a
    from .execution_contract import resource
    task,state=a._state(task);candidate=state.get('active_candidate')
    failure=read_json(resource(task,failure_ref))
    record=next((r for r in reversed(state.get('connection_attempts',[])) if r['candidate']==candidate['pptx']['sha256']),None)
    if (not record or failure.get('input_pptx_hash')!=candidate['pptx']['sha256'] or
            failure.get('exit_code',0)==0 or failure.get('status')!='FAILED'):
        raise ValueError('A failed actual host receipt must bind this exact finite connection transaction')
    before=record['baseline'];receipt=read_json(resource(task,before['render']))
    if receipt.get('pptx_hash')!=before['pptx']['sha256'] or receipt.get('status')!='PASS':raise ValueError('Preceding transaction lacks a verified actual render')
    resource(task,before['pptx'])
    with writer(task):
        record['rejection']={'status':'REJECTED_ACTUAL_EXPORT','failure':failure_ref,'restored':before['pptx']}
        state['active_candidate']=copy.deepcopy(before);state['scene']=before['scene'];state['stage']='review';state['packet']=None
        if 'baseline_mattes' in record:state['neighbor_mattes']=copy.deepcopy(record['baseline_mattes'])
        state.pop('acceptance',None);state.pop('quality_result',None);a._save(task,state)
    return {'status':'EXACT_PRECEDING_RENDERED_TRANSACTION_RESTORED','candidate':before['pptx']}

def replay(task,state,candidate,record):
    from .connection_geometry import _load_contract
    # Replay historical construction against its own sealed original facts;
    # current connection quality remains a separate mandatory report.
    contract=_load_contract(task,state,historical_ref=record['contract'])
    if record.get('source_graph')!=contract.get('source_graph'):return False
    rows=[r for r in contract['items'] if r['id'] in record['connections']]
    output=task/'audits/connection-replay'/(identity(record)+'.pptx')
    construct(task,state,record['baseline'],contract,rows,output,record.get('construction_version',1))
    with ZipFile(output) as a,ZipFile(safe_path(task,candidate['pptx']['path'])) as b:
        return a.namelist()==b.namelist() and all(a.read(p)==b.read(p) for p in a.namelist())
