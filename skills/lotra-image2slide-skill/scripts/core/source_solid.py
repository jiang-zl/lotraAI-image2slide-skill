"""Source-conditioned orthographic faces; height does not distort the roof."""
from .recipes import node,path

def building(parameters):
    p=parameters;w,h=p.get('source_size',[100,100])
    if min(w,h)<=0:raise ValueError('Positive observed building dimensions required')
    # Two projected footprint vectors and one vertical vector share vertices.
    # Projection comes from the source; no physical camera is inferred.
    d1,d2=p.get('roof_slopes',[.20,.12])
    y1,y2=100*w/h*d1,100*w/h*d2
    if y1+y2>=85:raise ValueError('Footprint projection leaves no building height')
    top=[[5,y1],[38,0],[98,y2],[65,y1+y2]]
    front=[top[0],top[3],[65,100],[5,100-y2]]
    side=[top[3],top[2],[98,100-y1],[65,100]]
    rows=p.get('rows',7);cols=p.get('columns',3)
    if not 1<=rows<=12 or not 1<=cols<=5:raise ValueError('Bounded source window grid required')
    out=[node('root','group',[0,0,100,100],semantic='isometric_building')]
    fills={'front':p.get('front_fill','8DA6A2'),'side':p.get('side_fill','65857F'),'roof':p.get('roof_fill','B9C3B7')}
    for name,face in [('side',side),('front',front),('roof',top)]:
        obj=path(name,face,'root',p.get('stroke','607473'),fills[name],p.get('line_width',.35),True,'building_'+name)
        obj['style']['gradient']=[fills[name],p.get(name+'_shadow',fills[name])]
        obj['style']['gradient_angle']=90;out.append(obj)
    def at(face,u,v):return [(1-u)*(1-v)*face[0][i]+u*(1-v)*face[1][i]+u*v*face[2][i]+(1-u)*v*face[3][i] for i in (0,1)]
    for name,face in [('front',front),('side',side)]:
        for row in range(rows):
            for col in range(cols):
                u,v=(col+.2)/cols,(row+.2)/rows;du,dv=.62/cols,.56/rows
                out.append(path('window_'+name+'_'+str(row)+'_'+str(col),[at(face,u,v),at(face,u+du,v),at(face,u+du,v+dv),at(face,u,v+dv)],'root',None,p.get('window_fill','375B5D'),.1,True,'window'))
    return out
