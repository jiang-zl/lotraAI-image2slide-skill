"""Native table slots from actual grid, row heights, merges and world transform."""
from .mathml import NS
from .common import identity
import numpy as np


def slots(entry):
    node=entry['node']; table=node.find('.//a:tbl',NS)
    if table is None or entry.get('error') or not entry.get('axis_aligned'):
        raise ValueError('A supported actual native table is required; no screenshot grid inference')
    columns=[int(c.get('w')) for c in table.findall('a:tblGrid/a:gridCol',NS)]
    rows=table.findall('a:tr',NS); heights=[int(r.get('h')) for r in rows]
    if not columns or not heights or min(columns+heights)<=0:
        raise ValueError('Invalid native table tracks')
    if any(len(r.findall('a:tc',NS))!=len(columns) for r in rows):
        raise ValueError('Ambiguous native cell continuations; preserve as unmeasured')
    xx=np.cumsum([0]+columns)/sum(columns); yy=np.cumsum([0]+heights)/sum(heights)
    result={}; covered={}; layout=[]
    for r,row in enumerate(rows):
        for c,cell in enumerate(row.findall('a:tc',NS)):
            continuation=cell.get('hMerge') in ('1','true') or cell.get('vMerge') in ('1','true')
            if continuation:
                if (r,c) not in covered:
                    raise ValueError('Native merge continuation has no anchor')
                continue
            rs,cs=int(cell.get('rowSpan',1)),int(cell.get('gridSpan',1))
            if min(rs,cs)<1 or r+rs>len(rows) or c+cs>len(columns):
                raise ValueError('Native cell span exceeds the table')
            for rr in range(r,r+rs):
                for cc in range(c,c+cs):
                    if (rr,cc) in covered:raise ValueError('Overlapping native table merge anchors')
                    covered[rr,cc]=(r,c)
            lo=entry['matrix']@np.array([xx[c],yy[r],1.])
            hi=entry['matrix']@np.array([xx[c+cs],yy[r+rs],1.])
            box=[float(lo[0]),float(lo[1]),float(hi[0]-lo[0]),float(hi[1]-lo[1])]
            if min(box[2:])<=0:raise ValueError('Unsupported flipped table slot')
            key=f'{r}:{c}'
            result[key]={'row':r,'column':c,'row_span':rs,'column_span':cs,'bbox':box,
                         'text':''.join(cell.itertext())}
            layout.append([r,c,rs,cs])
    geometry={'columns':columns,'rows':heights,'merges':layout}
    return {'slots':result,'geometry':geometry,'geometry_sha256':identity(geometry),
            'frame':entry['frame'],'rows':len(rows),'columns':len(columns)}


def boxes(frame,nodes):
    if frame.get('table') not in nodes:raise ValueError('Missing saved table owner')
    table=slots(nodes[frame['table']])
    if table['geometry_sha256']!=frame.get('table_geometry_sha256'):
        raise ValueError('Actual table tracks/merges changed after the plan was frozen')
    if max(abs(a-b) for a,b in zip(table['frame'],frame['bbox']))>frame.get('tolerance_px',.01):
        raise ValueError('Actual table outer frame differs from the frozen target')
    roles={f"{v['row']}:{v['column']}":v['role'] for v in frame.get('cell_roles',[])}
    if len(roles)!=len(frame.get('cell_roles',[])) or set(roles)!=set(table['slots']):
        raise ValueError('Every actual native table slot needs one source role')
    members={f"{m['row']}:{m['column']}":m for m in frame.get('members',[])}
    if len(members)!=len(frame.get('members',[])) or set(members)!={k for k,v in roles.items() if v=='image'}:
        raise ValueError('All source image slots must bind one complete content member')
    return {m['object']:table['slots'][key]['bbox'] for key,m in members.items()}


def planned_boxes(frame):
    geometry=frame['table_geometry']
    if identity(geometry)!=frame['table_geometry_sha256']:
        raise ValueError('Frozen native table geometry identity mismatch')
    cols,rows=geometry['columns'],geometry['rows']
    xx=np.cumsum([0]+cols)/sum(cols);yy=np.cumsum([0]+rows)/sum(rows)
    merges={(r,c):(rs,cs) for r,c,rs,cs in geometry['merges']}
    x,y,w,h=frame['bbox']; result={}
    for m in frame['members']:
        r,c=m['row'],m['column'];rs,cs=merges[r,c]
        result[m['object']]=[x+w*xx[c],y+h*yy[r],w*(xx[c+cs]-xx[c]),h*(yy[r+rs]-yy[r])]
    return result


def picture_candidates(nodes):
    """Find every picture centered within a real cell. These are candidates,
    requiring source decisions; overlapping logos must be explained explicitly.
    """
    result=[]
    for table,entry in nodes.items():
        if entry['tag']!='graphicFrame' or entry['node'].find('.//a:tbl',NS) is None:continue
        try: actual=slots(entry)
        except ValueError as error:
            result.append({'table':table,'status':'unmeasured','reason':str(error)});continue
        for name,pic in nodes.items():
            if pic['tag']!='pic' or not pic.get('frame'):continue
            x,y,w,h=pic['frame']; center=(x+w/2,y+h/2)
            for key,slot in actual['slots'].items():
                a,b,c,d=slot['bbox']
                if a<=center[0]<=a+c and b<=center[1]<=b+d:
                    result.append({'table':table,'object':name,'row':slot['row'],'column':slot['column'],
                                   'slot':slot['bbox'],'picture':pic['frame'],'status':'requires_source_decision'})
    return result
