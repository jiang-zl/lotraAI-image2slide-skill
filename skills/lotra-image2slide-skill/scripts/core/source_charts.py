"""Native scientific bars from explicitly observed values and source positions.

No image-to-number inference is hidden in the compiler. Missing measurements
remain missing; the host supplies source-supported labels and measured bounds.
"""
import math
from .recipes import node,path


def grouped_bars(cid,spec):
    x,y,w,h=spec['plot'];maximum=spec['maximum'];step=spec['step']
    if maximum<=0 or step<=0 or not all(math.isfinite(v) for v in (x,y,w,h,maximum,step)):
        raise ValueError('Observed finite plot range and extent required')
    font=spec.get('font','Liberation Sans');unit=spec.get('points_per_source_pixel',.75)
    out=[node(cid,'group',spec['roi'],semantic='scientific_bar_chart')]
    def text(key,value,box,size=12,align='center',**style):
        out.append(node(cid+'__'+key,'text',box,{'text':str(value)},cid,'chart_label',
                        font=font,font_size=size*unit,color='222222',align=align,valign='middle',**style))
    out.extend([path(cid+'__axis_x',[[x,y+h],[x+w,y+h]],cid,'555555',width=.7),
                path(cid+'__axis_y',[[x,y],[x,y+h]],cid,'555555',width=.7)])
    for i in range(int(maximum/step)+1):
        value=i*step;yy=y+h*(1-value/maximum)
        text('tick_'+str(i),f'{value:.2f}',[x-42,yy-9,38,18],12,'right')
    text('unit',spec['y_label'],spec['y_label_box'],14,rotation=270)
    for si,series in enumerate(spec['series']):
        sx,sy=series['legend_position']
        out.append(node(cid+'__legend_swatch_'+str(si),'shape',[sx,sy+5,5,5],{'preset':'rect'},cid,
                        fill=series['color'],stroke='888888',line_width=.35))
        text('legend_'+str(si),series['label'],[sx+7,sy,series.get('legend_width',150),18],12,'left')
    for gi,group in enumerate(spec['groups']):
        if len(group['values'])!=len(spec['series']) or len(group['positions'])!=len(spec['series']):
            raise ValueError('Source category needs one position/value per series')
        for si,(label,bx) in enumerate(zip(group['values'],group['positions'])):
            value=float(label)
            if not 0<=value<=maximum:raise ValueError('Observed value outside plot range')
            height=h*value/maximum;by=y+h-height
            out.append(node(cid+'__bar_'+str(gi)+'_'+str(si),'shape',[bx,by,spec['bar_width'],max(.001,height)],
                            {'preset':'rect'},cid,'measured_bar',fill=spec['series'][si]['color'],stroke='777777',line_width=.45))
            text('value_'+str(gi)+'_'+str(si),label,[bx-8,by-20,spec['bar_width']+16,19],10)
        text('category_'+str(gi),group['label'],group['label_box'],14)
    return out
