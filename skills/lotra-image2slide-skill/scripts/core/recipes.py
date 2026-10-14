"""Small native CS component recipes with natural editable parts.

Recipes are geometric priors, not substitutes for observing the source. Every
instance owns independent coordinates/styles. Parameters describe measured form.
"""
import copy
import math

VERSION='native-recipes-1.2.0'


def node(id,kind,bbox,content=None,parent=None,semantic=None,**style):
    if style.get('stroke') is None and style.get('line_width') == 0:
        style.pop('line_width')
    return {'id':id,'render_type':kind,'semantic_type':semantic or kind,'parent':parent,
            'bbox':list(bbox),'content':content or {},'style':style,
            'versions':dict.fromkeys(('content','structure','style','placement'),0),
            'locks':dict.fromkeys(('content','structure','style','placement'),False),
            'evidence_status':'inferred'}


def path(id,points,parent,stroke='000000',fill=None,width=1,closed=False,semantic=None):
    if semantic=='terminal_glass' and closed:
        from .semantic_curves import smooth_outline,contour_node
        return contour_node(id,smooth_outline(points,True),parent,stroke,fill,width,semantic,True)
    xs,ys=zip(*points);x,y=min(xs),min(ys);w,h=max(max(xs)-x,.001),max(max(ys)-y,.001)
    return node(id,'path',[x,y,w,h],{'contours':[{'points':[[ (px-x)/w,(py-y)/h ] for px,py in points],
                'closed':closed}]},parent,semantic,stroke=stroke,fill=fill,line_width=width)


def arc_shape(id,center,radii,start,end,parent,stroke,width,semantic,rotation=0):
    from .semantic_curves import arc,contour_node
    return contour_node(id,arc(center,radii,start,end,rotation),parent,stroke,None,width,semantic)


def _ellipse(cx,cy,rx,ry,rotation=0,steps=48):
    r=math.radians(rotation);c,s=math.cos(r),math.sin(r)
    return [[cx+rx*math.cos(t)*c-ry*math.sin(t)*s,cy+rx*math.cos(t)*s+ry*math.sin(t)*c]
            for t in [i*2*math.pi/steps for i in range(steps)]]


def radio(parameters):
    p={'radii':[9,16,23],'start_degrees':110,'end_degrees':250,'center':[50,50],
       'stroke':'3333FF','line_width':1,'mast':True,**parameters}
    radii=p['radii']
    if not radii or any(r<=0 for r in radii) or radii!=sorted(set(radii)):
        raise ValueError('Radio radii must be positive, distinct and ordered')
    start,end=p['start_degrees'],p['end_degrees']
    if not 0<abs(end-start)<=360:raise ValueError('Invalid measured radio arc range')
    cx,cy=p['center'];out=[node('root','group',[0,0,100,100],semantic='wireless_signal')]
    for i,r in enumerate(radii):
        out.append(arc_shape('arc_'+str(i),[cx,cy],[r,r],start,end,'root',p['stroke'],p['line_width'],'signal_arc'))
    if p['mast']:
        out.append(path('mast',[[cx,cy],[cx-6,cy+31],[cx+6,cy+31]],'root',p['stroke'],
                        p.get('mast_fill','FFFFFF'),p['line_width'],True,'antenna_mast'))
        for i,f in enumerate(p.get('mast_bars',[])):
            if not 0<f<1:raise ValueError('Mast bar must lie inside antenna frame')
            out.append(path('mast_bar_'+str(i),[[cx-6*f,cy+31*f],[cx+6*f,cy+31*f]],'root',p['stroke'],width=p['line_width'],semantic='antenna_brace'))
        if p.get('emitter_radius'):
            r=p['emitter_radius']
            out.append(node('emitter','shape',[cx-r,cy-r,2*r,2*r],{'preset':'ellipse'},'root','emitter',fill=p['stroke'],stroke=None))
    return out


def document_model(parameters):
    p={'fold':21,'stroke':'000000','fill':'FFFFFF','line_width':1.5,'motif':'atom','rule_count':3,**parameters}
    f=p['fold'];stroke=p['stroke'];width=p['line_width']
    if not 0<f<40 or not 0<=p['rule_count']<=8:raise ValueError('Invalid document parameters')
    out=[node('root','group',[0,0,80,110],semantic='model_document')]
    out.append(path('paper',[[0,0],[80-f,0],[80,f],[80,110],[0,110]],'root',stroke,p['fill'],width,True,'paper'))
    out.append(path('fold',[[80-f,0],[80-f,f],[80,f]],'root',stroke,width=width,semantic='fold'))
    if p['motif']=='atom':
        out.append(node('symbol','group',[13,25,54,49],parent='root',semantic='model_symbol'))
        for i,rotation in enumerate(p.get('orbit_angles',(30,90,150))):
            out.append(path('orbit_'+str(i),_ellipse(40,53,p.get('orbit_rx',26),p.get('orbit_ry',13),rotation),'symbol',stroke,width=width,closed=True,semantic='orbit'))
        for i,(x,y,r) in enumerate(p.get('motif_nodes',[])):
            out.append(node('motif_node_'+str(i),'shape',[x-r,y-r,2*r,2*r],{'preset':'ellipse'},'symbol','model_graph_node',fill='FFFFFF',stroke=stroke,line_width=width))
    elif p['motif']!='none':raise ValueError('Unknown document motif; observe source instead of guessing')
    for i in range(p['rule_count']):
        out.append(path('rule_'+str(i),[[12,84+i*8],[67,84+i*8]],'root',stroke,width=width,semantic='text_rule'))
    if p.get('pencil'):
        pencil=pencil_mark({'stroke':stroke,'line_width':width})
        for item in pencil:
            old=item['id'];item['id']='pencil' if old=='root' else 'pencil_'+old
            item['parent']='root' if old=='root' else 'pencil'
            item['bbox'][1]+=117
        out.extend(pencil)
    return out


def pencil_mark(parameters):
    p={'stroke':'000000','line_width':.7,**parameters}
    out=[node('root','group',[0,0,80,9],semantic='pencil')]
    # One uninterrupted outer silhouette; the white tip/cap are natural parts.
    pts=[[0,4.5],[9,0],[75,0],[79,1],[80,3],[80,6],[79,8],[75,9],[9,9]]
    out.append(path('outline',pts,'root',p['stroke'],p['stroke'],p['line_width'],True,'pencil_body'))
    out.append(path('tip',[[3,4.5],[10,1.4],[10,7.6]],'root',None,'FFFFFF',0,True,'pencil_tip'))
    out.append(node('cap','shape',[73,1.3,4.4,6.4],{'preset':'roundRect','adjustments':[.25]},'root','pencil_cap',fill='FFFFFF',stroke=None))
    return out


def server_rack(parameters):
    p={'units':3,'fill':'33A6C8','stroke':'266071','line_width':1,'lights':3,'vents':5,**parameters}
    if not 1<=p['units']<=16 or not 0<=p['lights']<=8 or not 0<=p['vents']<=16:raise ValueError('Unbounded rack geometry')
    out=[node('root','group',[0,0,100,p['units']*28],semantic='server_rack')]
    for i in range(p['units']):
        unit='unit_'+str(i);y=i*28
        out.append(node(unit,'group',[0,y,100,22],parent='root',semantic='server_unit'))
        out.append(node(unit+'_body','shape',[0,y,100,22],{'preset':'rect'},unit,'case',fill=p['fill'],stroke=p['stroke'],line_width=p['line_width']))
        for j in range(p['lights']):
            out.append(node(unit+'_light_'+str(j),'shape',[7+j*6,y+7,3,4],{'preset':'ellipse'},unit,'status_light',fill=p['stroke'],stroke=None))
        for j in range(p['vents']):
            out.append(path(unit+'_vent_'+str(j),[[64+j*5,y+5],[64+j*5,y+17]],unit,p['stroke'],width=.7,semantic='vent'))
    if p.get('separators'):
        for i in range(p['units']-1):
            y=25+i*28
            out.append(path('separator_'+str(i),[[p.get('separator_inset',7),y],
                [100-p.get('separator_inset',7),y]],'root',p['stroke'],
                width=p.get('separator_width',p['line_width']),semantic='tier_separator'))
    return out


def perspective_server(parameters):
    """A measured three-face server with separately editable semantic marks.

    Coordinates are local to the component.  Shared vertices are validated so
    the caller cannot produce three unrelated polygons and call them a case.
    """
    defaults={
        'front':[[15,20],[60,35],[60,95],[15,80]],
        'side':[[60,35],[88,15],[88,75],[60,95]],
        'top':[[15,20],[43,0],[88,15],[60,35]],
        'front_fill':'F6F3E7','side_fill':'AA9978','top_fill':'FFFCF3',
        'stroke':'4F4B40','line_width':1.5,'vent_count':3,
        'light_count':1,'drive_count':2,
    }
    p={**defaults,**parameters}
    faces=[p['front'],p['side'],p['top']]
    if any(len(face)!=4 or any(len(vertex)!=2 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in vertex) for vertex in face) for face in faces):
        raise ValueError('Server faces require four finite measured vertices each')
    front,side,top=faces
    if front[1]!=side[0] or front[2]!=side[3] or top[0]!=front[0] or top[3]!=front[1] or top[2]!=side[1]:
        raise ValueError('Server faces must share their observed corner vertices')
    if any(type(p[key]) is not int or not 0<=p[key]<=12 for key in ('vent_count','light_count','drive_count')):
        raise ValueError('Server mark counts must be bounded integers')
    def at(u,v):
        # Bilinear interpolation keeps slots and indicators on the perspective face.
        return [(1-u)*(1-v)*front[0][i]+u*(1-v)*front[1][i]+u*v*front[2][i]+(1-u)*v*front[3][i] for i in (0,1)]
    stroke,width=p['stroke'],p['line_width']
    out=[node('root','group',[0,0,100,100],semantic='perspective_server')]
    out.extend([path('side_face',side,'root',stroke,p['side_fill'],width,True,'server_side'),
                path('front_face',front,'root',stroke,p['front_fill'],width,True,'server_front'),
                path('top_face',top,'root',stroke,p['top_fill'],width,True,'server_top')])
    for i in range(p['drive_count']):
        v=.20+i*.16
        out.append(path('drive_'+str(i),[at(.14,v),at(.62,v)],'root',stroke,width=max(.8,width*.8),semantic='server_drive_slot'))
    for i in range(p['vent_count']):
        v=.67+i*.055
        out.append(path('vent_'+str(i),[at(.13,v),at(.72,v)],'root',stroke,width=max(.55,width*.55),semantic='server_vent'))
    for i in range(p['light_count']):
        x,y=at(.20+i*.15,.53)
        radius=max(.7,width*.9)
        out.append(node('indicator_'+str(i),'shape',[x-radius,y-radius,2*radius,2*radius],
                        {'preset':'ellipse'},'root','server_indicator',fill=p.get('light_fill','597E83'),stroke=None))
    return out


def native_template(parameters):
    """Bounded data-only native parts; learning can add a new component class.

    This deliberately has no resource loader, executable expression, image,
    trace, or arbitrary metadata channel. Text is literal slide content.
    """
    from .common import canonical
    from .scene import validate
    if set(parameters)!={'objects'}:raise ValueError('Native template only accepts objects')
    raw=parameters['objects']
    if not isinstance(raw,list) or not 2<=len(raw)<=128 or len(canonical(raw))>28000:
        raise ValueError('Native template exceeds bounded part budget')
    content_keys={
        'group':set(),'shape':{'preset','adjustments','connection_sites'},
        'path':{'contours','connection_sites','arrow','start_arrow'},'text':{'text','runs','paragraphs','inline_math'},
        'equation':{'ast','render_mode'},
        'connector':{'points','source','target','source_site','target_site','source_anchor',
                     'target_anchor','source_anchor_object','target_anchor_object','arrow','tail_arrow'},
    }
    out=[]
    allowed_fields={'id','render_type','semantic_type','parent','bbox','content','style'}
    for part in raw:
        if not isinstance(part,dict) or set(part)-allowed_fields:raise ValueError('Unsupported native template metadata')
        kind=part.get('render_type');content=part.get('content',{})
        if kind not in content_keys or set(content)-content_keys[kind]:
            raise ValueError('Template requires self-contained native geometry')
        out.append(node(part['id'],kind,part['bbox'],copy.deepcopy(content),part.get('parent'),
                        part.get('semantic_type'),**copy.deepcopy(part.get('style',{}))))
    roots=[p for p in out if not p['parent']]
    if len(roots)!=1 or roots[0]['id']!='root' or roots[0]['render_type']!='group':
        raise ValueError('Native template needs exactly one root group')
    # Reuse the production geometry, hierarchy, math, and connector validators.
    resource={'path':'unused','sha256':'0'*64}
    validate({'schema_version':'0.1','revision':0,'canvas':{'width':100,'height':100,'unit':'px','target_width_inches':1},
              'source':resource,'evidence':resource,'profile':resource,'objects':out,'relations':[],'prototypes':[]},
             verify_resources=False)
    # A depth-first stable order is unnecessary; build restores the authored
    # paint order. The root itself must precede its descendants for fitting.
    return [roots[0]]+[o for o in out if o['id']!='root']


def wireless_terminal(parameters):
    """Complete terminal and measured paired radio bands, before instance pose."""
    p={'body':'168C96','screen':'124B58','signal':'F39A43','stroke':'284F52',
       'line_width':1,'bands':3,**parameters}
    if not 1<=p['bands']<=5:raise ValueError('Bounded signal band count required')
    out=[node('root','group',[0,0,100,110],semantic='wireless_terminal')]
    for side in (-1,1):
        for i in range(p['bands']):
            r=34+i*7;start,end=(145,215) if side<0 else (-35,35)
            if p.get('filled_bands'):
                radii=p.get('radii',[35+10*j for j in range(p['bands'])])
                if len(radii)!=p['bands']:raise ValueError('Source radii must match its observed bands')
                r=radii[i];thickness=p.get('band_thickness',7)
                palette=p.get('band_colors',[p['body'],p['signal']])
                from .semantic_curves import annular_band,contour_node
                out.append(contour_node('signal_'+str(side)+'_'+str(i),annular_band([50,55],r,thickness,start,end),
                    'root',p['stroke'],palette[i%len(palette)],p.get('band_outline_width',1.8),'radio_band',True))
            else:
                out.append(arc_shape('signal_border_'+str(side)+'_'+str(i),[50,55],[r,r],start,end,'root',p['stroke'],p.get('signal_width',2.6)*2.2,'radio_band_outline'))
                out.append(arc_shape('signal_'+str(side)+'_'+str(i),[50,55],[r,r],start,end,'root',p['signal'],p.get('signal_width',2.6),'radio_band'))
    if p.get('source_body'):
        # One continuous black chassis, not several protruding generic caps.
        out.append(node('body','shape',[27,12,46,85],{'preset':'roundRect','adjustments':[.28]},
                        'root','terminal_body',fill=p['stroke'],stroke=p['stroke'],line_width=p['line_width']))
        top=[[31,29],[31,21],[33,17],[38,14],[62,14],[67,17],[69,22],[69,31],
             [65,35],[58,37],[42,37],[35,35]]
        bottom=[[x,110-y] for x,y in reversed(top)]
        for name,points in (('cap_top',top),('cap_bottom',bottom)):
            out.append(path(name,points,'root',None,p['body'],.1,True,'terminal_glass'))
        out.append(node('screen','shape',[35,43,30,27],{'preset':'roundRect','adjustments':[.23]},
                        'root','terminal_screen',fill=p['screen'],stroke=None))
        for name,y in (('top',38),('bottom',73)):
            out.append(path(name+'_mark',[[34,y],[66,y]],'root',p['stroke'],width=.5,semantic='glass_frame'))
    else:
        out.append(node('body','shape',[27,22,46,66],{'preset':'roundRect','adjustments':[.24]},'root','terminal_body',
                        fill=p['body'],stroke=p['stroke'],line_width=p['line_width']))
        for name,y in (('cap_top',14),('cap_bottom',82)):
            out.append(node(name,'shape',[32,y,36,15],{'preset':'roundRect','adjustments':[.3]},'root','terminal_cap',fill=p['body'],stroke=p['stroke'],line_width=p['line_width']))
        out.append(node('screen','shape',[35,33,30,42],{'preset':'roundRect','adjustments':[.15]},'root','terminal_screen',
                        fill=p['screen'],stroke=p['stroke'],line_width=p['line_width']))
        for name,y in (('top',21),('bottom',82)):
            out.append(path(name+'_mark',[[41,y],[59,y]],'root',p.get('mark','1A5760'),width=1,semantic='terminal_mark'))
    return out


def smartphone(parameters):
    p={'fill':'FAA466','stroke':'232C28','line_width':1.2,**parameters}
    out=[node('root','group',[0,0,46,90],semantic='smartphone')]
    out.append(node('case','shape',[0,0,46,90],{'preset':'roundRect','adjustments':[.18]},'root','phone_case',fill=p['stroke'],stroke=p['stroke'],line_width=p['line_width']))
    out.append(node('screen','shape',[5,5,36,72],{'preset':'roundRect','adjustments':[.12]},'root','phone_screen',fill=p['fill'],stroke=None))
    out.append(path('glint',[[6,7],[24,7],[7,46]],'root',None,p.get('highlight','FFD18D'),closed=True,semantic='screen_reflection'))
    out.append(node('button','shape',[20,81,6,6],{'preset':'ellipse'},'root','home_button',fill='C0C3B4',stroke=None))
    return out


def display_monitor(parameters):
    p={'mode':'terminal','fill':'32A9D3','stroke':'46575B','line_width':1,**parameters}
    out=[node('root','group',[0,0,100,118],semantic='display_monitor')]
    out.append(node('case','shape',[0,0,100,61],{'preset':'rect'},'root','monitor_case',fill=p['fill'],stroke=p['stroke'],line_width=p['line_width']))
    if p['mode']=='terminal':
        out.append(path('prompt',[[8,9],[17,14],[8,19]],'root',p['stroke'],width=1,semantic='terminal_prompt'))
        out.append(path('cursor',[[19,22],[28,22]],'root',p['stroke'],width=.7,semantic='terminal_cursor'))
        out.append(path('bezel',[[0,70],[100,70]],'root',p['stroke'],width=1,semantic='monitor_bezel'))
        out.append(node('keyboard','shape',[0,79,100,22],{'preset':'rect'},'root','keyboard',fill=p.get('keyboard','FFD38B'),stroke=p['stroke'],line_width=1))
        for i in range(3):
            out.append(node('key_'+str(i),'shape',[8+i*8,87,2.8,2.8],{'preset':'ellipse'},'root','key',fill=p['stroke'],stroke=None))
        for i in range(5):
            out.append(path('vent_'+str(i),[[64+i*7,83],[65+i*7,96]],'root',p['stroke'],width=.8,semantic='keyboard_mark'))
        out.append(node('stand','shape',[43,105,14,13],{'preset':'rect'},'root','monitor_stand',fill=p['fill'],stroke=p['stroke'],line_width=.8))
        out.append(path('base',[[0,117],[100,117]],'root',p['stroke'],width=1,semantic='monitor_base'))
    elif p['mode']=='signal':
        out[1]['style'].update(fill='8F9486',stroke='151A17')
        out.append(node('screen','shape',[8,7,84,46],{'preset':'rect'},'root','signal_screen',fill=p.get('signal_fill','EE5D90'),stroke='151A17',line_width=1))
        out.append(path('wave',[[10,34],[25,34],[32,17],[38,45],[47,12],[52,34],[67,34],[72,22],[82,34],[91,34]],'root','111111',width=1.3,semantic='signal_wave'))
        out.append(node('stem','shape',[46,61,8,12],{'preset':'rect'},'root','monitor_stand',fill='8F9486',stroke='151A17',line_width=.8))
        out.append(path('base',[[27,74],[74,74]],'root','151A17',width=1,semantic='monitor_base'))
    else:raise ValueError('Observe monitor mode before choosing its recipe')
    return out


def warning_symbol(parameters):
    p={'fill':'F13955','stroke':'FFFFFF','line_width':1.4,**parameters}
    return [node('root','group',[0,0,100,100],semantic='warning_symbol'),
            node('disk','shape',[0,0,100,100],{'preset':'ellipse'},'root','warning_disk',fill=p['fill'],stroke=None),
            path('outline',[[50,17],[20,72],[80,72]],'root',p['stroke'],None,p['line_width'],True,'warning_triangle'),
            path('stem',[[50,38],[50,55]],'root',p['stroke'],width=2,semantic='warning_mark'),
            node('dot','shape',[47.5,61,5,5],{'preset':'ellipse'},'root','warning_dot',fill=p['stroke'],stroke=None)]


def neural_network(parameters):
    p={'layers':[2,3,2],'colors':['CB6BB0','A273B2','915E95'],'line_width':.55,**parameters}
    if p.get('orientation') not in ('horizontal','vertical'):
        raise ValueError('Neural-network orientation must be observed and supplied explicitly')
    counts=p['layers']
    if not 2<=len(counts)<=8 or any(type(n) is not int or not 1<=n<=16 for n in counts):
        raise ValueError('Bounded observed neural layers required')
    colours=p['colors'];out=[node('root','group',[0,0,100,100],semantic='neural_network')];positions=[]
    span=p.get('layer_span',70);step=span/max(1,max(counts)-1)
    radius=min(9,step*.42)
    for layer,count in enumerate(counts):
        xx=12+76*layer/(len(counts)-1)
        points=[(xx,50+(j-(count-1)/2)*step) for j in range(count)]
        if p['orientation']=='vertical':points=[(yy,xx) for xx,yy in points]
        positions.append(points)
    for layer in range(len(counts)-1):
        for i,a in enumerate(positions[layer]):
            for j,b in enumerate(positions[layer+1]):
                out.append(node('edge_'+str(layer)+'_'+str(i)+'_'+str(j),'connector',
                    [min(a[0],b[0]),min(a[1],b[1]),max(.001,abs(b[0]-a[0])),max(.001,abs(b[1]-a[1]))],
                    {'source':'n_'+str(layer)+'_'+str(i),'target':'n_'+str(layer+1)+'_'+str(j),
                     'points':[a,b],'arrow':p.get('edge_arrow','none'),'source_site':2 if p['orientation']=='vertical' else 3,
                     'target_site':0 if p['orientation']=='vertical' else 1},'root','neural_edge',
                    stroke=p.get('edge_color',colours[layer%len(colours)]),line_width=p['line_width']))
    for layer,points in enumerate(positions):
        for j,(xx,yy) in enumerate(points):
            out.append(node('n_'+str(layer)+'_'+str(j),'shape',[xx-radius,yy-radius,2*radius,2*radius],{'preset':'ellipse'},'root','neuron',
                        fill=colours[layer%len(colours)],stroke=p.get('node_stroke'),line_width=p.get('node_width',.55)))
    return out


def cloud_upload(parameters):
    p={'stroke':'328AC8','accent':'E8B43A','line_width':1.5,**parameters}
    out=[node('root','group',[0,0,100,100],semantic='edge_cloud')]
    contour={'commands':[{'op':'moveTo','points':[[.23,.58]]},
      {'op':'cubicBezTo','points':[[.03,.58],[.02,.40],[.18,.38]]},
      {'op':'cubicBezTo','points':[[.12,.20],[.40,.15],[.49,.34]]},
      {'op':'cubicBezTo','points':[[.73,.31],[.83,.58],[.61,.58]]},
      {'op':'lnTo','points':[[.23,.58]]},{'op':'close','points':[]}]}
    out.append(node('cloud','path',[11,22,87,73],{'contours':[contour]},'root','cloud_outline',fill=None,stroke=p['stroke'],line_width=p['line_width']))
    out.append(path('upload',[[50,54],[50,34],[42,42],[50,34],[58,42]],'root',p['accent'],width=p['line_width']))
    out.append(path('upload_base',[[42,58],[58,58]],'root',p['accent'],width=p['line_width']))
    for i,(start,end) in enumerate(((152,302),(-25,117))):
        pts=[[50+44*math.cos(math.radians(start+(end-start)*j/48)),50+44*math.sin(math.radians(start+(end-start)*j/48))] for j in range(49)]
        out.append(path('ring_'+str(i),pts,'root',p['stroke'],width=p['line_width']))
        xx,yy=pts[-1];out.append(node('ring_dot_'+str(i),'shape',[xx-4,yy-4,8,8],{'preset':'ellipse'},'root',fill='FFFFFF',stroke=p['stroke'],line_width=p['line_width']))
    return out


def antenna_tower(parameters):
    p={'stroke':'233C4B','radio':'2495D2','line_width':1.0,'signal_width':.8,**parameters}
    out=[node('root','group',[0,0,100,100])]
    half=float(p.get('mast_half_width',14))
    if not 4<=half<=25:raise ValueError('Measured tower mast half-width must be between 4 and 25')
    out.append(path('frame',[[50,25],[50-half,94],[50+half,94],[50,25]],'root',p['stroke'],width=p['line_width'],semantic='tower_truss'))
    for i,(a,b) in enumerate([([50-half*.58,65],[50+half*.58,65]),([50-half*.75,77],[50+half*.75,77]),([50-half*.75,77],[50+half*.58,65]),([50-half*.58,65],[50+half*.94,90])]):
        out.append(path('brace_'+str(i),[a,b],'root',p['stroke'],width=p['line_width']*.7))
    for side in (-1,1):
        for i,r in enumerate((10,18,26)):
            start,end=(-math.degrees(1),math.degrees(1)) if side==1 else (180+math.degrees(1),180-math.degrees(1))
            out.append(arc_shape('signal_'+str(side)+'_'+str(i),[50,22],[r,r],start,end,'root',p['radio'],p['signal_width'],'radio_arc'))
    return out


def sensing_camera(parameters):
    p={'mode':'security_camera','tone':'grey','line_width':.7,'radio':'168EF2',**parameters}
    if p['mode'] not in ('security_camera','ptz_sensor'):raise ValueError('Observed camera mode required')
    out=[node('root','group',[0,0,100,100],semantic='sensing_camera')];line=p['line_width']
    def e(id,box,fill,stroke=None,semantic='camera_part'):
        out.append(node(id,'shape',box,{'preset':'ellipse'},'root',semantic,fill=fill,stroke=stroke,line_width=line))
    if p['mode']=='security_camera':
        blue=p['tone']=='blue';body='45A8C5' if blue else 'ABB8BF'
        out.append(path('housing',[[25,17],[74,19],[78,47],[32,58],[25,17]],'root',None,body,closed=True,semantic='camera_housing'))
        out.append(path('hood',[[12,15],[72,13],[80,24],[20,30]],'root',None,'CBD3D7',closed=True,semantic='camera_hood'))
        e('front_lens_rim',[7,20,35,40],'CAD5D8','697A83','lens_rim')
        e('front_lens_glass',[14,28,19,23],'263C4A','63717B','lens_glass')
        if not blue:
            for i in range(12):
                a=i*math.tau/12;e('IR_LED_'+str(i),[24+13*math.cos(a)-1.6,40+15*math.sin(a)-1.6,3.2,3.2],'D9E3E5',None,'infrared_LED')
        e('lens_highlight',[18,31,4,5],'75A9CC',None,'lens_highlight')
        out.append(path('support_arm',[[50,54],[64,50],[64,73],[54,78],[50,54]],'root',None,'7C919B',closed=True,semantic='camera_support'))
        out.append(node('mount','shape',[48,76,24,10],{'preset':'rect'},'root','camera_mount',fill='8C9DA4',stroke=None))
    else:
        contour=[[18,46],[78,46]]+[[48+30*math.cos(a),46+37*math.sin(a)] for a in [i*math.pi/48 for i in range(49)]]
        out.append(path('chassis',contour,'root','263B49','D1D8DF',line,True,'ptz_chassis'))
        e('upper_sensor',[29,12,38,34],'5BACE5','263B49','sensor_lens');e('upper_glass',[39,21,18,17],'15384F',None,'sensor_glass');e('upper_reflection',[44,25,6,5],'80D9FA')
        e('lower_sensor',[30,50,36,30],'4E81A8','263B49','sensor_lens');e('lower_glass',[39,56,18,17],'163546');e('lower_reflection',[44,59,6,5],'67D1F2')
        out.append(path('chassis_divider',[[18,46],[78,46]],'root','263B49',width=line))
    out.append(path('radio_mast',[[90,39],[90,70]],'root',p['radio'],width=line,semantic='radio_mast'))
    for side in (-1,1):
        for i,r in enumerate((6,10,14)):
            start,end=(-math.degrees(1.1),math.degrees(1.1)) if side==1 else (180+math.degrees(1.1),180-math.degrees(1.1))
            out.append(arc_shape('radio_'+str(side)+'_'+str(i),[90,28],[r,r],start,end,'root',p['radio'],line,'radio_arc'))
    e('radio_emitter',[88,26,4,4],p['radio'],None,'radio_emitter')
    return out


from .native_icons import network_device,health_hospital,multirotor,isometric_building,landscape_tree,sensor_instrument

from .source_solid import building as source_building
from .semantic_icons import wireless_vehicle, natural_icon

RECIPES={'wireless_vehicle':wireless_vehicle,'natural_icon':natural_icon,'pencil_mark':pencil_mark,'source_building':source_building,'multirotor':multirotor,'isometric_building':isometric_building,'landscape_tree':landscape_tree,'sensor_instrument':sensor_instrument,'network_device':network_device,'health_hospital':health_hospital,'neural_network':neural_network,'cloud_upload':cloud_upload,'antenna_tower':antenna_tower,'wireless_terminal':wireless_terminal,'smartphone':smartphone,'sensing_camera':sensing_camera,
         'display_monitor':display_monitor,'warning_symbol':warning_symbol,
         'wireless_signal':radio,'model_document':document_model,'server_rack':server_rack,
          'perspective_server':perspective_server,
         'native_template':native_template}


def instantiate(recipe,parameters,instance_id,bbox,parent=None,*,evidence_status='inferred',local_objects=None):
    from .source_contract import finite
    finite(parameters, 'recipe.parameters')
    if local_objects is not None:finite(local_objects, 'recipe.local_objects')
    if recipe not in RECIPES:raise ValueError('Unknown native recipe')
    if not instance_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in instance_id):
        raise ValueError('Unsafe component instance id')
    if len(bbox)!=4 or any(not math.isfinite(v) for v in bbox) or min(bbox[2:])<=0:raise ValueError('Invalid instance box')
    target_bbox=list(bbox)
    pose=parameters.get('pose_degrees')
    natural=recipe in ('wireless_vehicle','natural_icon')
    if natural and not parameters.get('model') and local_objects is None:
        from .natural_catalog import parameters as catalog_parameters
        parameters=catalog_parameters(parameters)
    out=copy.deepcopy(local_objects if local_objects is not None else RECIPES[recipe](parameters))
    if natural:
        from .semantic_icons import bake_pose,native_ink_extent
        out=bake_pose(out,pose or 0)
        factor=1 if parameters.get('stroke_units')=='local_pixels' else 96/72
        x0,y0,width,height=native_ink_extent(out,factor)
    else:
        all_boxes=[o['bbox'] for o in out[1:]]
        x0=min(b[0] for b in all_boxes);y0=min(b[1] for b in all_boxes)
        width=max(b[0]+b[2] for b in all_boxes)-x0;height=max(b[1]+b[3] for b in all_boxes)-y0
    if parameters.get('fit')=='contain' or pose is not None:
        angle=math.radians(0 if natural else pose or 0)
        rotated_width=abs(width*math.cos(angle))+abs(height*math.sin(angle))
        rotated_height=abs(width*math.sin(angle))+abs(height*math.cos(angle))
        scale=min(bbox[2]/rotated_width,bbox[3]/rotated_height)
        bbox=[bbox[0]+(bbox[2]-width*scale)/2,bbox[1]+(bbox[3]-height*scale)/2,width*scale,height*scale]
    # Fit geometry to the observed extent; path coordinates remain local.
    id_map={o['id']:instance_id if o['id']=='root' else instance_id+'__'+o['id'] for o in out}
    def point(p):return [bbox[0]+(p[0]-x0)/width*bbox[2],bbox[1]+(p[1]-y0)/height*bbox[3]]
    for o in out:
        root=o['id']=='root'
        o['id']=instance_id if root else instance_id+'__'+o['id']
        o['parent']=parent if root else instance_id if o['parent']=='root' else instance_id+'__'+o['parent']
        old=o['bbox'];o['bbox']=list(bbox) if root else [bbox[0]+(old[0]-x0)/width*bbox[2],bbox[1]+(old[1]-y0)/height*bbox[3],old[2]/width*bbox[2],old[3]/height*bbox[3]]
        o['evidence_status']=evidence_status
        if o['render_type']=='connector':
            c=o['content']
            if 'points' in c:c['points']=[point(p) for p in c['points']]
            for field in ('source','target','source_anchor_object','target_anchor_object'):
                if c.get(field):c[field]=id_map[c[field]]
        if recipe=='native_template':
            for key in ('font_size','line_width'):
                if o['style'].get(key):o['style'][key]*=math.sqrt(bbox[2]/width*bbox[3]/height)
        if parameters.get('stroke_units')=='local_pixels' and recipe!='native_template':
            if o['style'].get('line_width'):
                o['style']['line_width']*=math.sqrt(bbox[2]/width*bbox[3]/height)*72/96
        elif parameters.get('stroke_units') not in (None,'points','local_pixels'):
            raise ValueError('Declare stroke units as points or local_pixels')
        if root:
            o['component']=True
            if pose is not None and not natural:o['style']['rotation']=pose
    if natural:
        from .semantic_icons import fit_native_ink
        out=fit_native_ink(out,target_bbox,parameters.get('source_container'),parameters.get('source_anchor'))
    return out


def clip_convex_polygon(subject,boundary):
    """Sutherland-Hodgman for native closed polygons, no raster clip shortcut."""
    if len(subject)<3 or len(boundary)<3:raise ValueError('Polygon needs at least three vertices')
    signed=sum(boundary[i][0]*boundary[(i+1)%len(boundary)][1]-boundary[(i+1)%len(boundary)][0]*boundary[i][1] for i in range(len(boundary)))
    if abs(signed)<1e-12:raise ValueError('Degenerate clipping boundary')
    orientation=1 if signed>0 else -1
    def cross(a,b,p):return orientation*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
    if any(cross(boundary[i],boundary[(i+1)%len(boundary)],boundary[(i+2)%len(boundary)]) < -1e-8 for i in range(len(boundary))):
        raise ValueError('Clipping boundary must be convex')
    result=[list(p) for p in subject]
    for i,a in enumerate(boundary):
        b=boundary[(i+1)%len(boundary)];points=result;result=[]
        if not points:break
        previous=points[-1];dp=cross(a,b,previous)
        for point in points:
            dc=cross(a,b,point)
            if (dc>=0)!=(dp>=0):
                t=dp/(dp-dc);result.append([previous[0]+t*(point[0]-previous[0]),previous[1]+t*(point[1]-previous[1])])
            if dc>=0:result.append(point)
            previous,dp=point,dc
    return result


def clip_native_contour(contour,bbox,boundary,segments=32):
    """Complete native fill within a semantic boundary, never a bitmap mask.

    Curves are sampled at bounded fidelity before polygon intersection. Keep
    the unclipped complete component separately when it is a reusable icon.
    """
    from .geometry import path_operations
    if not 8<=segments<=256:raise ValueError('Bounded curve sampling required')
    points=[];current=None
    for op,values in path_operations(contour):
        if op in ('moveTo','lnTo'):
            current=values[0];points.append(current)
        elif op in ('cubicBezTo','quadBezTo'):
            controls=[current]+values
            if current is None:raise ValueError('Curve needs a preceding move')
            for step in range(1,segments+1):
                t=step/segments;degree=len(controls)-1
                points.append([sum(math.comb(degree,i)*(1-t)**(degree-i)*t**i*controls[i][axis]
                                   for i in range(degree+1)) for axis in (0,1)])
            current=values[-1]
    x,y,w,h=bbox
    return clip_convex_polygon([[x+u*w,y+v*h] for u,v in points],boundary)
