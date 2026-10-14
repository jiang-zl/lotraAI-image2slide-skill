"""Small complete editable symbols; variants reflect the observed device kind."""
import math
from .recipes import node,path


def network_device(p):
    mode=p.get('mode')
    if mode not in ('router','gateway','firewall','datacenter'):
        raise ValueError('Choose the observed network-device type explicitly')
    lw=p.get('line_width',.6);out=[node('root','group',[0,0,100,100],semantic='network_'+mode)]
    def shape(id,box,preset,fill,stroke='354D5A'):
        out.append(node(id,'shape',box,{'preset':preset},'root',mode,fill=fill,stroke=stroke,line_width=lw))
    if mode in ('router','gateway'):
        fill=p.get('fill','278DB9' if mode=='router' else 'F9FAF7')
        shape('chassis',[9,31,82,54],'can',fill)
        shape('upper_surface',[9,23,82,31],'ellipse',fill)
        color='FFFFFF' if mode=='router' else 'DC252C'
        for i,angle in enumerate((0,90,180,270)):
            r=math.radians(angle);u=[math.cos(r),math.sin(r)];v=[-u[1],u[0]]
            pts=[[50+u[0]*a+v[0]*b,39+u[1]*a+v[1]*b] for a,b in [(6,-2),(22,-2),(22,-6),(32,0),(22,6),(22,2),(6,2)]]
            out.append(path('direction_'+str(i),pts,'root',color,color,lw*.4,True,'router_direction_mark'))
    elif mode=='firewall':
        shape('brick_body',[3,16,94,69],'rect',p.get('fill','C36B24'),'795223')
        for i,y in enumerate((39,62)):
            out.append(path('horizontal_'+str(i),[[3,y],[97,y]],'root','EEC397',None,lw))
        for i,(x,y,z) in enumerate([(32,16,39),(65,16,39),(17,39,62),(49,39,62),(81,39,62),(32,62,85),(65,62,85)]):
            out.append(path('brick_joint_'+str(i),[[x,y],[x,z]],'root','EEC397',None,lw))
    else:
        for rack in range(3):
            x=5+rack*29
            out.append(path('side_'+str(rack),[[x+21,20],[x+28,12],[x+28,83],[x+21,94]],'root','434A4E','848A8D',lw,True))
            out.append(path('top_'+str(rack),[[x,20],[x+7,12],[x+28,12],[x+21,20]],'root','434A4E','BEC3C5',lw,True))
            shape('front_'+str(rack),[x,20,21,74],'rect','596164')
            for row in range(5):
                shape('slot_'+str(rack)+'_'+str(row),[x+3,25+row*12,15,8],'rect','303A3F')
                shape('led_'+str(rack)+'_'+str(row),[x+4,28+row*12,2,2],'ellipse','C7E8CE',None)
    return out


def health_hospital(p):
    out=[node('root','group',[0,0,200,220],semantic='health_hospital')]
    def shape(id,box,fill,stroke=None,preset='rect',width=1):
        out.append(node(id,'shape',box,{'preset':preset},'root',id,fill=fill,stroke=stroke,line_width=width))
    shape('main_wall',[18,51,111,155],'C8CAC8');shape('side_wall',[126,118,60,88],'C2C8C4')
    shape('main_roof',[7,33,136,29],'EE6469',preset='roundRect');shape('cross_panel',[51,18,47,32],'EE6469',preset='roundRect')
    out.append(path('hospital_cross',[[67,25],[80,25],[80,34],[88,34],[88,45],[80,45],[80,53],[67,53],[67,45],[59,45],[59,34],[67,34]],'root',None,'FFFFFF',1,True,'medical_cross'))
    shape('side_roof',[129,106,70,20],'EF686D',preset='roundRect')
    for i,y in enumerate((75,111,147)):
        shape('window_frame_'+str(i),[28,y,90,26],'438AB6');shape('window_dark_'+str(i),[35,y+6,77,14],'263744')
        for j in range(2):shape('window_pane_'+str(i)+'_'+str(j),[39+j*37,y+7,31,9],'FCFCFB')
    shape('side_window_frame',[136,133,46,24],'438AB6');shape('side_window_dark',[142,139,34,12],'263744')
    for j in range(2):shape('side_window_pane_'+str(j),[145+j*15,141,12,7],'FFFFFF')
    shape('entry_frame',[50,181,47,25],'438AB6');shape('entry',[59,185,29,21],'FFFFFF');shape('entry_divider',[73,185,3,21],'8E9296')
    shape('side_entry',[154,181,28,28],'53B893',preset='ellipse');shape('base',[0,205,199,10],'777E80')
    return out

def multirotor(p):
    if 'rotors' not in p:raise ValueError('Declare the actually observed rotor count')
    count=p['rotors']
    if count not in (4,6):raise ValueError('Choose the observed four/six-rotor device')
    color=p.get('fill','202622');lw=p.get('line_width',.7)
    rgb=[int(color[i:i+2],16) for i in (0,2,4)]
    def shade(target,amount):return ''.join(f'{round(v*(1-amount)+target*amount):02X}' for v in rgb)
    out=[node('root','group',[0,0,100,70],semantic='multirotor')]
    hubs=[(20,17),(80,17),(16,52),(84,52)] if count==4 else [(20,15),(80,15),(9,37),(91,37),(20,58),(80,58)]
    for i,(x,y) in enumerate(hubs):
        out.append(path('arm_'+str(i),[[50,36],[x,y]],'root',color,width=p.get('arm_width',lw*3),semantic='rotor_arm'))
        out.append(node('hub_'+str(i),'shape',[x-2,y-3,4,8],{'preset':'ellipse'},'root','rotor_hub',fill=color,stroke=None))
        out.append(node('propeller_'+str(i),'shape',[x-13,y-2,26,4],{'preset':'ellipse'},'root','propeller',fill=color,stroke=None))
    out.append(node('hull','shape',[34,29,32,17],{'preset':'roundRect','adjustments':[.18]},'root','hull',fill=color,stroke=None,gradient=p.get('hull_gradient',[color,shade(0,.3)]),gradient_angle=90))
    if p.get('body_view','rounded')=='rounded':
        out.append(node('hull_top','shape',[34,23,32,12],{'preset':'ellipse'},'root','rounded_hull_top',fill=color,stroke=None,gradient=p.get('top_gradient',[shade(255,.3),color]),gradient_angle=90))
    out.append(path('leg_left',[[40,44],[33,61],[28,62]],'root',color,width=p.get('leg_width',lw*2),semantic='landing_gear'))
    out.append(path('leg_right',[[60,44],[68,61],[74,62]],'root',color,width=p.get('leg_width',lw*2),semantic='landing_gear'))
    if p.get('payload_camera'):
        out.append(node('payload_camera','shape',[44,44,12,14],{'preset':'roundRect','adjustments':[.3]},'root','underbody_payload',fill=color,stroke=None,gradient=[color,shade(0,.3)],gradient_angle=90))
    return out


def isometric_building(p):
    rows=p.get('rows',7);columns=p.get('columns',3)
    if type(rows) is not int or type(columns) is not int or not 1<=rows<=12 or not 1<=columns<=5:
        raise ValueError('Observed bounded building-window grid required')
    front=[[5,30],[65,45],[65,100],[5,85]];side=[[65,45],[98,25],[98,80],[65,100]];top=[[5,30],[38,10],[98,25],[65,45]]
    out=[node('root','group',[0,0,100,100],semantic='isometric_building')]
    stroke=p.get('stroke','607473');lw=p.get('line_width',.4)
    for name,face,fill in [('side',side,p.get('side_fill','65857F')),('front',front,p.get('front_fill','8DA6A2')),('roof',top,p.get('roof_fill','B9C3B7'))]:
        out.append(path(name,face,'root',stroke,fill,lw,True,'building_'+name))
    def at(face,u,v):return [(1-u)*(1-v)*face[0][a]+u*(1-v)*face[1][a]+u*v*face[2][a]+(1-u)*v*face[3][a] for a in (0,1)]
    for f,face in [('front',front),('side',side)]:
        for row in range(rows):
            for col in range(columns):
                u=(col+.2)/columns;v=(row+.2)/rows;du=.62/columns;dv=.56/rows
                points=[at(face,u,v),at(face,u+du,v),at(face,u+du,v+dv),at(face,u,v+dv)]
                out.append(path('window_'+f+'_'+str(row)+'_'+str(col),points,'root',None,p.get('window_fill','375B5D'),.1,True,'window'))
    return out


def landscape_tree(p):
    fill=p.get('fill','718748');lw=p.get('line_width',.3)
    out=[node('root','group',[0,0,100,100],semantic='landscape_tree')]
    out.append(node('trunk','shape',[46,57,12,40],{'preset':'rect'},'root','trunk',fill=p.get('trunk','6B6950'),stroke=None))
    curve={'commands':[{'op':'moveTo','points':[[.5,.98]]},
      {'op':'cubicBezTo','points':[[.10,1.04],[-.04,.82],[.13,.60]]},
      {'op':'cubicBezTo','points':[[-.04,.40],[.15,.18],[.35,.25]]},
      {'op':'cubicBezTo','points':[[.23,.02],[.70,-.08],[.73,.22]]},
      {'op':'cubicBezTo','points':[[1.04,.22],[1.05,.57],[.86,.64]]},
      {'op':'cubicBezTo','points':[[1.01,.84],[.74,1.06],[.5,.98]]},{'op':'close','points':[]}]}
    out.append(node('crown','path',[2,2,94,73],{'contours':[curve]},'root','single_crown_outline',fill=fill,stroke=None,line_width=lw))
    out.append(node('crown_light','shape',[30,19,37,42],{'preset':'ellipse'},'root','foliage_shading',fill=p.get('highlight','A1AF62'),stroke=None,fill_alpha=.5))
    return out


def sensor_instrument(p):
    mode=p.get('mode');lw=p.get('line_width',.6)
    if mode not in ('anemometer','gnss','camera','lidar'):raise ValueError('Choose the observed sensing-instrument type')
    out=[node('root','group',[0,0,100,100],semantic=mode)]
    def shape(id,box,preset,fill,stroke=None):out.append(node(id,'shape',box,{'preset':preset},'root',id,fill=fill,stroke=stroke,line_width=lw))
    if mode=='anemometer':
        shape('stem',[45,34,10,51],'roundRect','7C847F','343B36');shape('base',[31,81,38,11],'ellipse','262F29','171E1A')
        out.append(path('shaft',[[21,24],[78,24]],'root','272E2A',width=2))
        for i,box in enumerate([[9,14,23,23],[68,14,23,23],[44,19,12,12]]):
            shape('cup_'+str(i),box,'ellipse','242C27','1F2522');shape('glint_'+str(i),[box[0]+box[2]*.2,box[1]+box[3]*.15,box[2]*.24,box[3]*.25],'ellipse','7E8681')
    elif mode=='gnss':
        shape('base_stem',[35,51,32,39],'can','242C26');shape('housing',[15,35,70,27],'can','424B42','263029');shape('antenna_cap',[15,22,70,29],'ellipse','F0F2EF','69726B')
        for i in range(3):shape('status_'+str(i),[31+12*i,53,4,4],'ellipse','91B739')
    elif mode=='camera':
        shape('case',[11,29,79,53],'roundRect','212A23','161E19');shape('top_housing',[38,20,25,13],'roundRect','252E28')
        shape('lens_outer',[32,33,47,47],'ellipse','3F4E46','111A14');shape('lens_inner',[38,39,35,35],'ellipse','192C34','627A7A');shape('lens_glass',[45,45,21,21],'ellipse','0A1922')
        shape('lens_glint',[48,47,6,8],'ellipse','6FACCC');shape('power_led',[81,33,3,3],'ellipse','A4C47B')
    else:
        shape('housing',[33,29,35,50],'rect','131C15');shape('cap',[24,23,52,12],'ellipse','656F69','212B24');shape('blue_window',[38,39,11,32],'rect','2688A8');shape('base',[23,77,55,12],'ellipse','142219','101912')
    return out
