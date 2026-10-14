"""Native presets with explicitly supported adjustment ranges."""
from pptx.enum.shapes import MSO_SHAPE

DEFINITIONS={
 'rect':('RECTANGLE',[]),'ellipse':('OVAL',[]),'cube':('CUBE',[(0,.5)]),
 'roundRect':('ROUNDED_RECTANGLE',[(0,.5)]),'rightArrow':('RIGHT_ARROW',[(0,1),(0,1)]),
 'triangle':('ISOSCELES_TRIANGLE',[(0,1)]),'diamond':('DIAMOND',[]),
 'pentagon':('PENTAGON',[]),'star5':('STAR_5_POINT',[(0,.5)]),
 'hexagon':('HEXAGON',[(0,.5),(1.1547,1.1547)]),'parallelogram':('PARALLELOGRAM',[(0,.5)]),
 'trapezoid':('TRAPEZOID',[(0,.5)]),'can':('CAN',[(0,.5)]),'cloud':('CLOUD',[]),
 'chevron':('CHEVRON',[(0,1)]),'leftRightArrow':('LEFT_RIGHT_ARROW',[(0,1),(0,.5)]),
 'leftArrow':('LEFT_ARROW',[(0,1),(0,1)]),'upArrow':('UP_ARROW',[(0,1),(0,1)]),'downArrow':('DOWN_ARROW',[(0,1),(0,1)]),
 'rightBrace':('RIGHT_BRACE',[]),'leftBrace':('LEFT_BRACE',[]),
 'wedgeRoundRectCallout':('ROUNDED_RECTANGULAR_CALLOUT',[(-1,1),(-1,1),(0,.5)])}
PRESETS={key:getattr(MSO_SHAPE,value[0]) for key,value in DEFINITIONS.items()}


def validate(preset,values):
    import math
    if preset not in PRESETS:raise ValueError('Unsupported native preset: '+str(preset))
    ranges=DEFINITIONS[preset][1]
    if len(values)>len(ranges):raise ValueError('Unsupported preset adjustment count')
    for value,(lo,hi) in zip(values,ranges):
        if not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('Preset adjustment outside supported native range')


def guides(preset,values):
    from pptx import Presentation
    p=Presentation();s=p.slides.add_slide(p.slide_layouts[6]).shapes.add_shape(PRESETS[preset],0,0,914400,914400)
    for index,value in enumerate(values):s.adjustments[index]=value
    return [(g.get('name'),g.get('fmla')) for g in s._element.spPr.prstGeom.avLst]
