"""Native editable polylines/paths and declared connector anchors."""
from .mathml import el,child,NS
import copy
import json
import math

GEOMETRY_CONTRACT_VERSION = 'attachment-contract-0.1.0'


def _owned_by(objects, identity, owner):
    seen=set()
    while identity:
        if identity==owner:return True
        if identity in seen or identity not in objects:return False
        seen.add(identity);identity=objects[identity].get('parent')
    return False


def shared_prefix(routes,tolerance=.1):
    """Measure the common orthogonal prefix from actual directed routes.

    Returns the longest overlap of those first segments. It never supplies a
    missing route or widens the caller's geometric tolerance.
    """
    if len(routes)<2 or any(route is None or len(route)<2 for route in routes):
        raise ValueError('Shared trunk requires at least two measured routes')
    indices=[0]*len(routes);current=list(routes[0][0]);points=[current];spread=0.
    for route in routes:
        delta=max(abs(route[0][i]-current[i]) for i in (0,1));spread=max(spread,delta)
        if delta>=tolerance:raise ValueError('Routes do not share a directed trunk within tolerance')
    for _ in range(sum(len(route) for route in routes)):
        directions=[];lengths=[]
        for route,index in zip(routes,indices):
            if index+1>=len(route):return {'points':points,'max_spread_px':spread,'tolerance_px':tolerance}
            end=route[index+1];delta=[end[i]-current[i] for i in (0,1)]
            axis=0 if abs(delta[0])>abs(delta[1]) else 1
            if abs(delta[1-axis])>=tolerance or abs(delta[axis])<=tolerance:
                if len(points)>1:return {'points':points,'max_spread_px':spread,'tolerance_px':tolerance}
                raise ValueError('Shared trunk supports a nonempty orthogonal first segment')
            directions.append((axis,1 if delta[axis]>0 else -1));lengths.append(abs(delta[axis]))
            spread=max(spread,abs(delta[1-axis]))
        if len(set(directions))!=1:
            if len(points)==1:raise ValueError('Routes do not share a directed trunk within tolerance')
            break
        axis,direction=directions[0];length=min(lengths);stop=list(current);stop[axis]+=direction*length
        points.append(stop)
        advance=[abs(value-length)<tolerance for value in lengths]
        if not all(advance):break
        indices=[i+1 for i in indices];current=stop
    return {'points':points,'max_spread_px':spread,'tolerance_px':tolerance}


def add_connection_sites(geometry,sites):
    """Expose ports on this real custom geometry in shape-width/height units."""
    guides=geometry.find('a:gdLst',NS);connections=geometry.find('a:cxnLst',NS)
    if guides is None or connections is None or len(connections):raise ValueError('Custom port slots must be empty')
    for i,(u,v) in enumerate([(.5,0),(0,.5),(.5,1),(1,.5)]+sites):
        child(guides,'a:gd',name='portX'+str(i),fmla='*/ w '+str(round(u*100000))+' 100000')
        child(guides,'a:gd',name='portY'+str(i),fmla='*/ h '+str(round(v*100000))+' 100000')
        child(child(connections,'a:cxn',ang='0'),'a:pos',x='portX'+str(i),y='portY'+str(i))


def _on_polyline(point,points,tolerance=.00001):
    for a,b in zip(points,points[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length and abs((point[0]-a[0])*dy-(point[1]-a[1])*dx)/length<=tolerance:
            if min(a[0],b[0])-tolerance<=point[0]<=max(a[0],b[0])+tolerance and min(a[1],b[1])-tolerance<=point[1]<=max(a[1],b[1])+tolerance:return True
    return False


def validate_attachment_contracts(scene):
    objects={o['id']:o for o in scene['objects']}
    for obj in objects.values():
        c=obj['content'];contract=c.get('attachment_contract')
        if obj['render_type']=='path' and c.get('connection_sites'):
            contours=c.get('contours',[])
            if len(contours)!=1 or contours[0].get('closed'):
                raise ValueError('Path ports require one visible open polyline')
            if any(not _on_polyline(point,contours[0]['points']) for point in c['connection_sites']):
                raise ValueError('Path port must lie on the actual visible path, not a proxy location')
        if contract:
            owner=contract.get('owner_id')
            if (contract.get('kind')!='rigid_parent' or obj['render_type']!='path'
                    or owner not in objects or objects[owner]['render_type']!='group' or obj.get('parent')!=owner):
                raise ValueError('Rigid path requires its declared real parent group')
            if c.get('source_anchor') or c.get('target_anchor'):
                raise ValueError('Rigid path cannot claim ConnectorFormat endpoint anchoring')
            contours=c.get('contours',[])
            if len(contours)!=1 or contours[0].get('closed') or c.get('arrow','none')!='none' or c.get('start_arrow','none')!='none':
                raise ValueError('Rigid attachment supports one open arrowless path')
            x,y,w,h=obj['bbox'];points=[[x+u*w,y+v*h] for u,v in contours[0]['points']]
            for which,index in [('source',0),('target',-1)]:
                anchor=c.get(which+'_anchor_object',c.get(which))
                if not _owned_by(objects,anchor,owner):raise ValueError('Rigid endpoint is outside the owning group')
                wanted=endpoint(objects,c,which)
                if wanted is None or max(abs(a-b) for a,b in zip(points[index],wanted))>.00001:
                    raise ValueError('Rigid path endpoint does not meet its declared real port')
        trunk=c.get('shared_trunk')
        if trunk:
            members=trunk.get('members',[])
            if obj['render_type']!='group' or len(members)<2 or len(set(members))!=len(members):
                raise ValueError('Shared trunk requires a real group and distinct branches')
            actual_members={o['id'] for o in objects.values() if o.get('parent')==obj['id']}
            if actual_members!=set(members):raise ValueError('Shared trunk group membership changed')
            routes=[]
            for identity in members:
                branch=objects[identity];bc=branch['content']
                if (branch['render_type']!='connector' or bc.get('shared_trunk_member_of')!=obj['id']
                        or not bc.get('source') or not bc.get('target')
                        or not bc.get('source_anchor',True) or not bc.get('target_anchor',True)):
                    raise ValueError('Shared branch requires two real endpoint anchors')
                routes.append(connector_points(objects,branch))
            prefix=shared_prefix(routes)['points']
            expected=trunk.get('reference_points',[])
            if len(expected)!=len(prefix) or len(expected)<2 or max(abs(a-b) for p,q in zip(prefix,expected) for a,b in zip(p,q))>=.1:
                raise ValueError('Shared routes changed the declared visible trunk')
        if c.get('shared_route_prefix_with'):
            carrier=objects.get(c['shared_route_prefix_with'])
            if (obj['render_type']!='connector' or carrier is None or carrier['render_type']!='connector'
                    or not c.get('source_anchor',True) or not c.get('target_anchor',True)
                    or c.get('source_anchor_object',c.get('source'))!=carrier['content'].get('source_anchor_object',carrier['content'].get('source'))):
                raise ValueError('Shared branch carrier and real endpoint anchors are required')
            prefix=shared_prefix([connector_points(objects,carrier),connector_points(objects,obj)])['points']
            expected=c.get('reference_branch_start')
            if expected is None or max(abs(a-b) for a,b in zip(prefix[-1],expected))>=.1:
                raise ValueError('Shared carrier route changes the observed branch junction')


def mark_geometry_contract(shape,obj):
    trunk=obj['content'].get('shared_trunk')
    if trunk:
        props=shape._element.find('p:nvGrpSpPr/p:cNvPr',NS)
        props.set('descr',json.dumps({'sci_rebuild_geometry':{'kind':'shared_trunk','version':1,
                      'members':trunk['members']}},sort_keys=True,separators=(',',':')))
    elif obj['content'].get('shared_route_prefix_with'):
        props=shape._element.find('p:nvCxnSpPr/p:cNvPr',NS)
        props.set('descr',json.dumps({'sci_rebuild_geometry':{'kind':'shared_branch','version':1,
                      'carrier':obj['content']['shared_route_prefix_with']}},sort_keys=True,separators=(',',':')))


def attachment_repair_draft(scene,*,rigid_paths=(),shared_trunks=(),visible_ports=(),extended_branches=(),task_id='attachment-repair'):
    """Produce a versioned local patch/grant; never commit or alter reference.

    rigid_paths: [(connection_id, existing_owner_group_id)]
    shared_trunks: [(trunk_id, [outgoing_branch_ids])]
    """
    from .common import identity
    from .state import closure
    objects={o['id']:o for o in scene['objects']};operations=[]
    for key,owner in rigid_paths:
        obj=objects[key];c=copy.deepcopy(obj['content'])
        points=connector_points(objects,obj);x,y,w,h=obj['bbox']
        if obj['render_type']!='connector' or w<=0 or h<=0 or c.get('arrow','none')!='none':
            raise ValueError('Rigid conversion needs an arrowless connector with a positive path frame')
        c['contours']=[{'points':[[(px-x)/w,(py-y)/h] for px,py in points],'closed':False}]
        c.update(source_anchor=False,target_anchor=False,
                 attachment_contract={'kind':'rigid_parent','owner_id':owner,'version':1,
                                      'scope':'Owner translation; resizing or independent child edits require revalidation'})
        operations.extend([{'object_id':key,'field':'render_type','value':'path'},
                           {'object_id':key,'field':'parent','value':owner},
                           {'object_id':key,'field':'content','value':c}])
    for key,members in shared_trunks:
        trunk=objects[key];tc=trunk['content'];prefix=connector_points(objects,trunk)
        if len(prefix)!=2 or not tc.get('source') or not tc.get('source_anchor',True) or tc.get('arrow','none')!='none':
            raise ValueError('Shared trunk conversion needs one source-anchored arrowless straight segment')
        content={'shared_trunk':{'members':list(members),'reference_points':prefix,'version':1},
                 'source':tc['source'],'target':key,'geometry_contract':GEOMETRY_CONTRACT_VERSION}
        operations.extend([{'object_id':key,'field':'render_type','value':'group'},
                           {'object_id':key,'field':'content','value':content}])
        for member in members:
            obj=objects[member];c=copy.deepcopy(obj['content']);tail=connector_points(objects,obj)
            if obj['render_type']!='connector' or c.get('source')!=key or max(abs(a-b) for a,b in zip(prefix[-1],tail[0]))>=.1:
                raise ValueError('Branch does not begin at the observed trunk junction')
            c.update(points=prefix+tail[1:],coordinate_space='canvas',logical_source=key,
                     source=tc['source'],source_anchor=True,shared_trunk_member_of=key)
            for field in ('source_anchor_object','source_site'):
                if field in tc:c[field]=tc[field]
            c.pop('source_anchor_limit',None)
            operations.extend([{'object_id':member,'field':'parent','value':key},
                               {'object_id':member,'field':'content','value':c}])
    trial=copy.deepcopy(scene);changed={o['id']:o for o in trial['objects']}
    def append(key,field,value):
        operations.append({'object_id':key,'field':field,'value':value});changed[key][field]=copy.deepcopy(value)
    for operation in operations:changed[operation['object_id']][operation['field']]=copy.deepcopy(operation['value'])
    for key,which,semantic_owner,anchor_id in visible_ports:
        obj=changed[key];c=copy.deepcopy(obj['content']);point=connector_points(changed,obj)[0 if which=='source' else -1]
        anchor=changed[anchor_id];ac=copy.deepcopy(anchor['content']);x,y,w,h=anchor['bbox']
        uv=[(point[0]-x)/w,(point[1]-y)/h];sites=ac.setdefault('connection_sites',[])
        index=next((i for i,p in enumerate(sites) if max(abs(a-b) for a,b in zip(p,uv))<.0000001),None)
        if index is None:index=len(sites);sites.append(uv)
        append(anchor_id,'content',ac)
        c['logical_'+which]=c.get(which);c[which]=semantic_owner;c[which+'_anchor_object']=anchor_id
        c[which+'_site']=4+index;c[which+'_anchor']=True;c.pop(which+'_anchor_limit',None)
        append(key,'content',c)
    for key,carrier_id in extended_branches:
        obj=changed[key];c=copy.deepcopy(obj['content']);tail=connector_points(changed,obj)
        carrier=changed[carrier_id];cc=carrier['content'];route=connector_points(changed,carrier);prefix=None
        for i,(a,b) in enumerate(zip(route,route[1:])):
            if _on_polyline(tail[0],[a,b]):prefix=route[:i+1]+[tail[0]];break
        if prefix is None or not cc.get('source_anchor',True):raise ValueError('Visible branch does not meet a source-anchored carrier')
        c.update(points=prefix+tail[1:],coordinate_space='canvas',logical_source=c.get('source'),source=cc['source'],
                 source_anchor=True,shared_route_prefix_with=carrier_id,reference_branch_start=tail[0])
        for field in ('source_anchor_object','source_site'):
            if field in cc:c[field]=cc[field]
        c.pop('source_anchor_limit',None);append(key,'content',c)
    if not operations:raise ValueError('No attachment repairs requested')
    validate_attachment_contracts(trial)
    targets={op['object_id'] for op in operations}
    affected=closure(scene,targets)|closure(trial,targets)
    grant_ids=targets|{owner for _,owner in rigid_paths}
    patch={'task_id':task_id,'base_scene_revision':scene['revision'],'base_scene_hash':identity(scene),
           'expected_versions':{key:objects[key]['versions'] for key in affected if key in objects},'operations':operations}
    grant={'task_id':task_id,'object_ids':sorted(grant_ids),'allowed_fields':['render_type','parent','content'],'role':'geometry_worker'}
    return patch,grant


def path_operations(contour):
    if 'commands' not in contour:
        if len(contour.get('points',[]))<2 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in contour['points']):raise ValueError('Invalid native path points')
        operations=[('moveTo',[contour['points'][0]])]+[('lnTo',[p]) for p in contour['points'][1:]]
        if contour.get('closed'):operations.append(('close',[]))
        return operations
    sizes={'moveTo':1,'lnTo':1,'cubicBezTo':3,'quadBezTo':2,'close':0}
    operations=[]
    for item in contour['commands']:
        name=item['op'];points=item.get('points',[])
        if name not in sizes or len(points)!=sizes[name] or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):raise ValueError('Invalid native path command')
        operations.append((name,points))
    if not operations or operations[0][0]!='moveTo':raise ValueError('Contour requires an initial move')
    if sum(k=='moveTo' for k,_ in operations)!=1 and contour.get('compound') is not True:raise ValueError('Contour requires exactly one initial move')
    if contour.get('compound'):
        drawn=False
        for i,(op,_) in enumerate(operations):
            if op=='moveTo':
                if i and not drawn:raise ValueError('Compound subpath has no drawing operation')
                drawn=False
            elif op in ('lnTo','quadBezTo','cubicBezTo'):drawn=True
        if not drawn:raise ValueError('Compound final subpath has no drawing operation')
    return operations


def custom_geometry(shape, contours, *, fill=False, coordinate_size=100000,bulk=False):
    props=shape._element.spPr
    for name in ("prstGeom","custGeom"):
        previous=props.find("a:"+name,NS)
        if previous is not None:props.remove(previous)
    if bulk:
        # Native paint can contain many fine contours. Compile numeric-only
        # DrawingML in one parser call instead of millions of Python/lxml calls.
        # The same operation validator and coordinate rounding are reused.
        from pptx.oxml import parse_xml
        chunks=['<a:custGeom xmlns:a="'+NS['a']+'"><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>'
                '<a:rect l="0" t="0" r="r" b="b"/><a:pathLst>']
        path_tag='<a:path w="'+str(coordinate_size)+'" h="'+str(coordinate_size)+'" fill="'+('norm' if fill else 'none')+'">'
        if fill:chunks.append(path_tag)
        for contour in contours:
            if not fill:chunks.append(path_tag)
            for name,points in path_operations(contour):
                if not points:chunks.append('<a:'+name+'/>');continue
                chunks.append('<a:'+name+'>')
                for x,y in points:
                    chunks.append('<a:pt x="'+str(round(x*coordinate_size))+'" y="'+str(round(y*coordinate_size))+'"/>')
                chunks.append('</a:'+name+'>')
            if not fill:chunks.append('</a:path>')
        if fill:chunks.append('</a:path>')
        chunks.append('</a:pathLst></a:custGeom>')
        geometry=parse_xml(''.join(chunks).encode('utf-8'));props.insert(1,geometry)
        return geometry
    geometry=el("a:custGeom")
    props.insert(1,geometry)
    for tag in ("avLst","gdLst","ahLst","cxnLst"):
        child(geometry,"a:"+tag)
    child(geometry,"a:rect",l="0",t="0",r="r",b="b")
    paths=child(geometry,"a:pathLst")
    filled_path=child(paths,"a:path",w=coordinate_size,h=coordinate_size,fill="norm") if fill else None
    for contour in contours:
        path=filled_path if fill else child(paths,"a:path",w=coordinate_size,h=coordinate_size,fill="none")
        for name,points in path_operations(contour):
            command=child(path,'a:'+name)
            for x,y in points:child(command,'a:pt',x=round(x*coordinate_size),y=round(y*coordinate_size))
    return geometry


def endpoint(objects, content, which):
    identity=content.get(which+"_anchor_object",content.get(which))
    if not identity:return None
    x,y,w,h=objects[identity]['bbox']
    site=content.get(which+'_site',3 if which=='source' else 1)
    sites=[(.5,0),(0,.5),(.5,1),(1,.5)]+objects[identity]['content'].get('connection_sites',[])
    u,v=sites[site]
    return x+u*w,y+v*h


def ported_shape(shape,obj):
    """Real visible shape with genuine custom connection sites, no proxy anchors."""
    c=obj['content'];preset=c.get('preset','rect');w,h=obj['bbox'][2:]
    props=shape._element.spPr
    previous=props.find('a:prstGeom',NS)
    props.remove(previous)
    geom=el('a:custGeom');props.insert(1,geom)
    for tag in ('avLst','gdLst','ahLst'):child(geom,'a:'+tag)
    guides=geom.find('a:gdLst',NS)
    sites=child(geom,'a:cxnLst')
    for i,(u,v) in enumerate([(.5,0),(0,.5),(.5,1),(1,.5)]+c['connection_sites']):
        child(guides,'a:gd',name='portX'+str(i),fmla='*/ w '+str(round(u*100000))+' 100000')
        child(guides,'a:gd',name='portY'+str(i),fmla='*/ h '+str(round(v*100000))+' 100000')
        site=child(sites,'a:cxn',ang='0')
        child(site,'a:pos',x='portX'+str(i),y='portY'+str(i))
    child(geom,'a:rect',l='0',t='0',r='r',b='b')
    path=child(child(geom,'a:pathLst'),'a:path',w=100000,h=100000)
    def point(parent,u,v):child(parent,'a:pt',x=round(u*100000),y=round(v*100000))
    def move(u,v):point(child(path,'a:moveTo'),u,v)
    def line(u,v):point(child(path,'a:lnTo'),u,v)
    def curve(*pts):
        node=child(path,'a:cubicBezTo')
        for u,v in pts:point(node,u,v)
    if preset=='rect':
        move(0,0);line(1,0);line(1,1);line(0,1)
    elif preset=='roundRect':
        radius=c.get('radius_px',min(w,h)*c.get('adjustments',[.16667])[0]);rx,ry=radius/w,radius/h;k=.552284749831
        move(rx,0);line(1-rx,0);curve((1-rx+k*rx,0),(1,ry-k*ry),(1,ry))
        line(1,1-ry);curve((1,1-ry+k*ry),(1-rx+k*rx,1),(1-rx,1))
        line(rx,1);curve((rx-k*rx,1),(0,1-ry+k*ry),(0,1-ry))
        line(0,ry);curve((0,ry-k*ry),(rx-k*rx,0),(rx,0))
    elif preset=='ellipse':
        k=.2761423749155;move(.5,0)
        curve((.5+k,0),(1,.5-k),(1,.5));curve((1,.5+k),(.5+k,1),(.5,1))
        curve((.5-k,1),(0,.5+k),(0,.5));curve((0,.5-k),(.5-k,0),(.5,0))
    else:raise ValueError('Custom port geometry supported for rect/roundRect/ellipse only')
    child(path,'a:close')
    return geom


def connector_points(objects, obj):
    c=obj['content']
    if c.get('points'):
        points=[list(p) for p in c['points']]
        if c.get('coordinate_space','canvas')=='normalized':
            x,y,w,h=obj['bbox']
            points=[[x+a*w,y+b*h] for a,b in points]
    else:
        points=[endpoint(objects,c,'source'),endpoint(objects,c,'target')]
    if len(points)<2 or any(p is None for p in points):raise ValueError('Connector needs endpoints or explicit route')
    authored=[list(p) for p in points]
    # Exact side-center anchoring only. Free source/target coordinates remain explicit.
    for which,index in [('source',0),('target',-1)]:
        if c.get(which) and c.get(which+'_anchor',True):
            points[index]=list(endpoint(objects,c,which))
    # A source-grounded node fit can move a port by a fraction of a pixel.
    # Preserve the authored first/last orthogonal directions by moving their
    # adjacent bends; never detach the endpoint or invent a hidden anchor.
    if len(points)>2:
        for index,near in ((0,1),(-1,-2)):
            if points[index]==authored[index]:continue
            a,b=authored[index],authored[near]
            if abs(a[0]-b[0])<1e-7:points[near][0]=points[index][0]
            elif abs(a[1]-b[1])<1e-7:points[near][1]=points[index][1]
    return points


def bounds(points):
    x0=min(p[0] for p in points);y0=min(p[1] for p in points)
    x1=max(p[0] for p in points);y1=max(p[1] for p in points)
    return [x0,y0,x1-x0,y1-y0]


def native_route_spec(points,scale):
    p=[]
    for point in points:
        if not p or point!=p[-1]:p.append(list(point))
    if not 2<=len(p)<=4096:raise ValueError('Bounded nonempty native route required')
    horizontal=abs(p[1][1]-p[0][1])<1e-7
    orthogonal=len(p)<=6 and all((abs(a[1]-b[1])<1e-7 if horizontal==(i%2==0) else abs(a[0]-b[0])<1e-7) for i,(a,b) in enumerate(zip(p,p[1:])))
    if len(p)>2 and not orthogonal:
        xs,ys=zip(*p);x,y=min(xs),min(ys);w,h=max(max(xs)-x,.001),max(max(ys)-y,.001)
        return {'preset':'nativeFreeform','off':[round(x*scale),round(y*scale)],
            'ext':[max(1,round(w*scale)),max(1,round(h*scale))],'rot':0,'flipH':False,'flipV':False,
            'guides':[],'points':[[round((px-x)/w*100000),round((py-y)/h*100000)] for px,py in p],
            'endpoint_quantization_px':[abs(round(w*scale)/scale-w),abs(round(h*scale)/scale-h)]}
    return _preset_route_spec(p,scale)


def freeform_route_exact(node,spec):
    from lxml import etree as E
    paths=node.findall('p:spPr/a:custGeom/a:pathLst/a:path',NS)
    if len(paths)!=1 or node.tag!='{'+NS['p']+'}sp' or node.find('p:spPr/a:noFill',NS) is None:return False
    path=paths[0]
    if path.get('fill')!='none' or path.get('w')!='100000' or path.get('h')!='100000':return False
    if [E.QName(n).localname for n in path]!=['moveTo']+['lnTo']*(len(spec['points'])-1):return False
    actual=[[int(p.get('x')),int(p.get('y'))] for p in path.findall('*/a:pt',NS)]
    return actual==spec['points']


def _preset_route_spec(points,scale):
    """Encode orthogonal routes as PowerPoint's supported bentConnector presets.

    A collinear U-route uses the smallest nonzero EMU extent that keeps guide
    values in the signed integer range. The resulting subpixel endpoint
    quantization is reported, never hidden with a changed reference.
    """
    import math
    p=[]
    for point in points:
        if not p or point!=p[-1]:p.append(list(point))
    i=1
    while i<len(p)-1:
        if (p[i-1][0]==p[i][0]==p[i+1][0]) or (p[i-1][1]==p[i][1]==p[i+1][1]):p.pop(i)
        else:i+=1
    if len(p)<2 or len(p)>6:raise ValueError('Native routed connectors support 1–5 segments')
    swap=len(p)>2 and abs(p[1][0]-p[0][0])<1e-8
    q=[[y,x] for x,y in p] if swap else p
    if len(q)>2:
        for i,(a,b) in enumerate(zip(q,q[1:])):
            if abs(a[1]-b[1])>1e-7 if i%2==0 else abs(a[0]-b[0])>1e-7:
                raise ValueError('Routed native connector needs alternating orthogonal segments')
    sx,sy=q[0];ex,ey=q[-1];dx=ex-sx;dy=ey-sy
    we=round(abs(dx)*scale);he=round(abs(dy)*scale)
    if len(q)>2:
        if we==0:we=max(1,math.ceil(max(abs(x-sx) for x,y in q)*scale/10000))
        if he==0:he=max(1,math.ceil(max(abs(y-sy) for x,y in q)*scale/10000))
    effective_dx=(we/scale)*(-1 if dx<0 else 1)
    effective_dy=(he/scale)*(-1 if dy<0 else 1)
    cx=(sx+sx+effective_dx)/2;cy=(sy+sy+effective_dy)/2
    world_center=(cy,cx) if swap else (cx,cy)
    off=[round(world_center[0]*scale-we/2),round(world_center[1]*scale-he/2)]
    guides=[]
    if len(q)>=4:guides.append(round((q[1][0]-sx)/(effective_dx or 1)*100000))
    if len(q)>=5:guides.append(round((q[2][1]-sy)/(effective_dy or 1)*100000))
    if len(q)>=6:guides.append(round((q[3][0]-sx)/(effective_dx or 1)*100000))
    return {'preset':'line' if len(q)==2 else 'bentConnector'+str(len(q)-1),'off':off,'ext':[we,he],
            'rot':5400000 if swap else 0,'flipH':dx<0,'flipV':not(dy<0) if swap else dy<0,'guides':guides,
            'endpoint_quantization_px':[abs(effective_dx-dx),abs(effective_dy-dy)]}


def set_native_route(shape,points,scale):
    # Scientific diagrams also contain curved/diagonal multi-segment paths.
    # Keep a single native connector contour and its native arrow/ports;
    # do not force these routes into an unrelated orthogonal preset.
    if len(points)>2:
        p=[]
        for point in points:
            if not p or point!=p[-1]:p.append(list(point))
        horizontal_first=abs(p[1][1]-p[0][1])<1e-7 if len(p)>1 else True
        orthogonal=len(p)<=6 and all((abs(a[1]-b[1])<1e-7 if horizontal_first==(i%2==0) else abs(a[0]-b[0])<1e-7) for i,(a,b) in enumerate(zip(p,p[1:])))
        if not orthogonal:
            if not 2<=len(p)<=4096:raise ValueError('Bounded native connector contour required')
            from .office_compatibility import freeform_route
            freeform_route(shape)
            xs,ys=zip(*p);x,y=min(xs),min(ys);w,h=max(max(xs)-x,.001),max(max(ys)-y,.001)
            xf=shape._element.spPr.xfrm
            for key in ('rot','flipH','flipV'):xf.attrib.pop(key,None)
            for element,attrs in [('off',{'x':round(x*scale),'y':round(y*scale)}),('ext',{'cx':max(1,round(w*scale)),'cy':max(1,round(h*scale))})]:
                for key,value in attrs.items():xf.find('a:'+element,NS).set(key,str(value))
            custom_geometry(shape,[{'points':[[(px-x)/w,(py-y)/h] for px,py in p],'closed':False}],fill=False)
            return {'preset':'nativeFreeform','scope':'explicit_source_route','automatic_rerouting':'not_promised'}
    spec=native_route_spec(points,scale);props=shape._element.spPr
    xfrm=props.xfrm
    xfrm.find('a:off',NS).set('x',str(spec['off'][0]));xfrm.find('a:off',NS).set('y',str(spec['off'][1]))
    xfrm.find('a:ext',NS).set('cx',str(spec['ext'][0]));xfrm.find('a:ext',NS).set('cy',str(spec['ext'][1]))
    for key in ('rot','flipH','flipV'):
        if spec[key]:xfrm.set(key,str(int(spec[key])))
        else:xfrm.attrib.pop(key,None)
    for name in ('prstGeom','custGeom'):
        old=props.find('a:'+name,NS)
        if old is not None:props.remove(old)
    geom=el('a:prstGeom',prst=spec['preset']);props.insert(1,geom);av=child(geom,'a:avLst')
    for i,value in enumerate(spec['guides'],1):child(av,'a:gd',name='adj'+str(i),fmla='val '+str(value))
    return spec
