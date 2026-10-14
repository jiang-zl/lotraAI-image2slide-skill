"""Absolute original anchors, independent of a candidate's group position.

An interface can remain internally correct after a whole icon is displaced.
These checks bind a saved native fill or a named root port to the original
canvas. A native group frame is used only as a coordinate transform, never as
an observed painted extent. Unsupported geometry has no box fallback.
"""
import math
import numpy as np
from .boundary_geometry import segments
from .semantic_interfaces import root_map
from .mathml import NS
from .native_paint import opaque_fill


def validate(anchor,size):
    if anchor.get('method') not in ('native_fill_center','native_painted_center','root_port_world'):
        raise ValueError('Use an explicit saved-fill or named root-port anchor')
    point=anchor.get('expected_source_px',[])
    if (len(point)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in point)
            or any(v<0 or v>limit for v,limit in zip(point,size))
            or type(anchor.get('tolerance_px')) not in (int,float)
            or not 0<=anchor['tolerance_px']<=2 or not anchor.get('threshold_basis')
            or not anchor.get('source_feature') or not anchor.get('object')):
        raise ValueError('Freeze a finite original anchor with bounded sampling uncertainty and a source feature')
    if anchor['method']=='root_port_world':
        port=anchor.get('port',[])
        if len(port)!=2 or not all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in port):
            raise ValueError('A named root port uses normalized child coordinates')
    return anchor


def contour_bounds(entry):
    """Exact line/quadratic/cubic extrema after every saved affine transform."""
    points=[]
    for curve in segments(entry):
        points.extend((curve[0],curve[-1]))
        for axis in (0,1):
            p=curve[:,axis]
            if len(p)==2:continue
            if len(p)==3:
                coefficients=[2*(p[0]-2*p[1]+p[2]),2*(p[1]-p[0])]
            else:
                coefficients=[3*(-p[0]+3*p[1]-3*p[2]+p[3]),6*(p[0]-2*p[1]+p[2]),3*(p[1]-p[0])]
            coefficients=np.trim_zeros(coefficients,'f')
            for t in np.roots(coefficients) if len(coefficients)>1 else []:
                if abs(t.imag)>1e-10 or not 0<t.real<1:continue
                t=float(t.real);q=curve.copy()
                while len(q)>1:q=(1-t)*q[:-1]+t*q[1:]
                points.append(q[0])
    if not points:raise ValueError('Empty saved fill has no actual anchor')
    points=np.array(points);lo,hi=points.min(0),points.max(0)
    return [*lo.tolist(),*(hi-lo).tolist()]


def evaluate(anchor,nodes,size,response=None):
    validate(anchor,size)
    try:
        entry=nodes[anchor['object']]
        if anchor['method']=='native_painted_center':
            if response is None:raise ValueError('A painted anchor requires its current actual host owner matte')
            sy,sx=size[1]/response.shape[0],size[0]/response.shape[1]
            if max(sx,sy)>.250001:raise ValueError('A painted anchor needs at least 4x native sampling')
            yy,xx=np.where(response<=2)
            if not len(xx):raise ValueError('A transparent/missing owner has no opaque painted anchor')
            bounds=[float(xx.min()*sx),float(yy.min()*sy),float((xx.max()+1-xx.min())*sx),float((yy.max()+1-yy.min())*sy)]
            point=np.array([bounds[0]+bounds[2]/2,bounds[1]+bounds[3]/2])
            domain={'actual_opaque_bounds':bounds,'sampling_error_px':math.hypot(sx,sy)/2}
        elif anchor['method']=='native_fill_center':
            opaque_fill(entry['node'].find('p:spPr',NS),gradient=True)
            preset=entry['node'].find('p:spPr/a:prstGeom',NS)
            if preset is not None and preset.get('prst') in ('rect','roundRect','ellipse'):
                if entry.get('error'):
                    raise ValueError('A symmetric fill anchor needs its actual supported filled geometry')
                point=(entry['matrix']@np.array([.5,.5,1.]))[:2]
                domain={'closed_symmetric_preset':preset.get('prst')}
            else:
                x,y,w,h=contour_bounds(entry);point=np.array([x+w/2,y+h/2])
                domain={'painted_fill_bounds':[x,y,w,h]}
        else:
            point=(root_map(entry)@np.array([*anchor['port'],1.]))[:2]
            domain={'named_port':anchor['port']}
        error=float(np.linalg.norm(point-np.array(anchor['expected_source_px'])))
        upper=error+domain.get('sampling_error_px',0.)+1e-6
        return {'status':'measured','passed':upper<=anchor['tolerance_px'],
            'values':{'actual_source_px':point.tolist(),'expected_source_px':anchor['expected_source_px'],
                'error_upper_px':upper,'tolerance_px':anchor['tolerance_px'],**domain}}
    except (ValueError,KeyError,TypeError,np.linalg.LinAlgError) as error:
        return {'status':'required_unmeasured','passed':False,'reason':str(error)}
