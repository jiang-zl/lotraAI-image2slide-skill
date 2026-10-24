"""Native table cells, true rectangular merges and bounded dimensions."""
import copy


def normalize(content):
    """An omitted cell style matrix has one canonical empty style per cell."""
    rows=validate(content)
    result=copy.deepcopy(content)
    if result.get('cell_styles') is None:
        result['cell_styles']=[[{} for _ in row] for row in rows]
    return result


def normalize_node(node):
    result=copy.deepcopy(node)
    if result.get('render_type')=='table':result['content']=normalize(result['content'])
    return result


def normalize_scene(scene):
    result=copy.deepcopy(scene)
    result['objects']=[normalize_node(node) for node in result['objects']]
    return result

def validate(content):
    import math
    rows=content.get('rows')
    if not rows or not rows[0] or len({len(r) for r in rows})!=1 or any(not isinstance(c,str) for r in rows for c in r):raise ValueError('Table needs a rectangular string matrix')
    height,width=len(rows),len(rows[0]);occupied=set()
    styles=content.get('cell_styles')
    if styles is not None:
        allowed={'font','font_size','bold','italic','color','align','valign','fill','padding','line_width','stroke','font_faces',
                 'native_bold','native_italic','native_script_styles'}
        if len(styles)!=height or any(len(row)!=width for row in styles):raise ValueError('Cell formatting needs the exact source table grid')
        for row in styles:
            for style in row:
                if not isinstance(style,dict) or set(style)-allowed:raise ValueError('Unknown source cell formatting field')
                # Font compilation retains logical emphasis while selecting
                # the physical regular/bold/italic slot for each script. The
                # compiled cell still passes this same saved-native schema.
                for flag in ('native_bold','native_italic'):
                    if flag in style and type(style[flag]) is not bool:raise ValueError('Native cell emphasis must be boolean')
                physical=style.get('native_script_styles',{})
                if (not isinstance(physical,dict) or set(physical)-{'latin','ea','cs'} or
                        any(not isinstance(flags,dict) or set(flags)!={'bold','italic'} or
                            any(type(v) is not bool for v in flags.values()) for flags in physical.values())):
                    raise ValueError('Native cell script styles need exact boolean physical slots')
                if style.get('align','left') not in ('left','center','right') or style.get('valign','middle') not in ('top','middle','bottom'):raise ValueError('Explicit source cell alignment required')
                for key in ('font_size','padding','line_width'):
                    if key in style and (not isinstance(style[key],(int,float)) or not math.isfinite(style[key]) or style[key]<0):raise ValueError('Finite bounded cell typography required')
    for key,limit in [('row_heights',height),('column_widths',width)]:
        if key in content and (len(content[key])!=limit or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in content[key])):raise ValueError('Invalid native table dimensions')
    for merge in content.get('merges',[]):
        if len(merge)!=4 or any(type(v) is not int for v in merge):raise ValueError('Merge must be row, column, row_span, column_span')
        r,c,rs,cs=merge
        if min(r,c)<0 or min(rs,cs)<1 or rs*cs<2 or r+rs>height or c+cs>width:raise ValueError('Invalid merge rectangle')
        cells={(i,j) for i in range(r,r+rs) for j in range(c,c+cs)}
        if occupied & cells:raise ValueError('Overlapping table merges')
        if any(rows[i][j] for i,j in cells-{(r,c)}):raise ValueError('Merged covered cells must be explicitly empty; never discard source content')
        occupied|=cells
    return rows


def apply(table,content,total_width,total_height):
    rows=validate(content)
    for key,collection,total in [('column_widths',table.columns,total_width),('row_heights',table.rows,total_height)]:
        if key not in content:continue
        values=content[key];denom=sum(values);used=0
        for i,value in enumerate(values):
            size=total-used if i==len(values)-1 else round(total*value/denom);used+=size
            if key=='column_widths':collection[i].width=size
            else:collection[i].height=size
    for r,c,rs,cs in content.get('merges',[]):table.cell(r,c).merge(table.cell(r+rs-1,c+cs-1))
    return rows


def saved_merges(node,ns):
    result=[]
    for r,row in enumerate(node.findall('a:graphic/a:graphicData/a:tbl/a:tr',ns)):
        for c,cell in enumerate(row.findall('a:tc',ns)):
            if cell.get('hMerge') in ('1','true') or cell.get('vMerge') in ('1','true'):continue
            rs,cs=int(cell.get('rowSpan','1')),int(cell.get('gridSpan','1'))
            if rs>1 or cs>1:result.append([r,c,rs,cs])
    return result



def propose_source_formats(task,request):
    """Compile exact source-guided cell styles; never infer a blanket table style."""
    import copy
    from . import agent_runtime as a,source_quality as q
    from .common import read_json
    from .source_ocr import actual_cell,source_literal
    task,state=a._state(task);candidate=state.get('selected')
    if not candidate or request.get('baseline_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Bind actual selected native table before source formatting')
    targets=request.get('units',[])
    if not 1<=len(targets)<=36 or len(set(targets))!=len(targets):raise ValueError('Use distinct source-guided native cells')
    units=[q.unit(state,uid) for uid in targets]
    if any(not u or u['profile']!='text' or len(u['objects'])!=1 or u['protocol'].get('table_cell') is None for u in units):
        raise ValueError('Every target needs an independently source-confirmed cell')
    ids={u['objects'][0] for u in units}
    if len(ids)!=1:raise ValueError('One existing native table per bounded format action')
    name=next(iter(ids));old=next(o for o in read_json(task/candidate['scene']['path'])['objects'] if o['id']==name)
    if old['render_type']!='table':raise ValueError('Retain the original native table')
    revised=copy.deepcopy(old);rows=revised['content']['rows'];styles=revised['content'].setdefault('cell_styles',[[{} for _ in row] for row in rows]);fields=[];changed=[]
    for unit in units:
        expected=next((f['cell_format'] for f in unit['features'] if f.get('category')=='typography' and f.get('status')=='observed' and f.get('cell_format')),None)
        actual=actual_cell(task,candidate,unit)
        if expected is None or actual is None or source_literal(unit) is None:raise ValueError('Read original literal and explicit native cell alignment/weight before an action')
        if actual['text']!=source_literal(unit):raise ValueError('Cell content differs; a format-only action cannot replace scientific data')
        if all(actual['format'].get(k)==v for k,v in expected.items()):continue
        cell=unit['protocol']['table_cell'];row,column=cell['row'],cell['column'];styles[row][column].update(expected);fields.append('table_cell_format.'+str(row)+'.'+str(column));changed.append(unit['id'])
    if not fields:return {'status':'SOURCE_NATIVE_CELL_FORMAT_ALREADY_MATCHED','baseline_hash':candidate['pptx']['sha256'],'source_hash':state['source']['sha256'],'units':targets,'limits':'No drawing or new quality claim; actual source-guided native format already matches.'}
    validate(revised['content'])
    return {'status':'SOURCE_NATIVE_CELL_FORMAT_PROPOSAL','baseline_hash':candidate['pptx']['sha256'],'source_hash':state['source']['sha256'],'object':revised,'allowed_changes':{name:fields},'units':changed,'limits':'Format-only source action; exact table data/grid/merges/extent and every other cell remain protected. Observe actual native cell content/format and source-relative glyph result independently.'}
