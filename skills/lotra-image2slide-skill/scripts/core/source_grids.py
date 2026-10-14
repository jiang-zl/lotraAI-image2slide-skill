"""Compile source matrix counts, atomic image bindings and shared frames."""
import math

CLASSES={'image_grid','photo_grid','scientific_image_grid','experimental_image_grid'}

def declaration(component):
    if component.get('semantic_class') not in CLASSES:return None
    return {'required':'source_spec.source_grid{rows,columns,cells:[source part IDs in row-major order],roi,source_note}',
        'binding':'Each cell is a distinct source quality part and binds one distinct photo/svg owner. One collage cannot replace independent cells.',
        'execution':'A matching frame-plan grid supplies shared tracks and cover content windows for every cell.'}

def validate_source(state,component,spec):
    grid=spec.get('source_grid')
    if grid is None:
        if declaration(component):raise ValueError('A source image grid requires counted source_grid rows, columns and independent cells')
        return
    if not isinstance(grid,dict):raise ValueError('Typed source_grid required')
    if set(grid)-{'rows','columns','cells','roi','source_note'}:raise ValueError('Unregistered source_grid fields')
    rows,columns=grid.get('rows'),grid.get('columns');cells=grid.get('cells',[])
    if (type(rows) is not int or type(columns) is not int or not 1<=rows<=128 or not 1<=columns<=128
            or rows*columns>1024 or not isinstance(cells,list) or len(cells)!=rows*columns
            or any(not isinstance(name,str) or not name for name in cells) or len(set(cells))!=len(cells)):
        raise ValueError('source_grid needs bounded rows/columns and one unique independent part per cell')
    parts={p['id']:p for p in spec.get('parts',[])}
    if not set(cells)<=set(parts) or any(parts[name].get('profile') in ('text','formula','relation') for name in cells):
        raise ValueError('source_grid cells need their own visual source quality parts')
    roi=grid.get('roi',[])
    if (not isinstance(roi,list) or len(roi)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in roi)
            or min(roi[2:])<=0 or not isinstance(grid.get('source_note'),str) or not grid['source_note']):
        raise ValueError('A finite source_grid ROI and observed source structure note are required')
    x,y,w,h=roi;ox,oy,ow,oh=component['roi']
    if x<ox or y<oy or x+w>ox+ow+.001 or y+h>oy+oh+.001:
        raise ValueError('source_grid ROI must belong to its current source owner')

def descriptors(state):
    quality=state.get('quality',{});units=quality.get('units',{});result=[]
    for owner,spec in quality.get('specifications',{}).items():
        grid=spec.get('source_grid')
        if not grid:continue
        objects=[]
        for part in grid['cells']:
            names=units.get(owner+':'+part,{}).get('objects',[])
            if len(names)!=1:raise ValueError('Each source_grid cell must bind one atomic photo/svg owner: '+owner+':'+part)
            objects.append(names[0])
        if len(set(objects))!=len(objects):raise ValueError('Source grid cells require distinct atomic images; a collage cannot cover multiple cells')
        result.append({'owner':owner,'rows':grid['rows'],'columns':grid['columns'],'roi':grid['roi'],
                       'parts':grid['cells'],'objects':objects,'source_note':grid['source_note']})
    return result

def validate_bound(state,owner,built):
    if not state.get('quality',{}).get('specifications',{}).get(owner,{}).get('source_grid'):return
    # Other owners may still be waiting for their construction packet.
    scoped={**state,'quality':{**state['quality'],'specifications':{owner:state['quality']['specifications'][owner]}}}
    nodes={o['id']:o for o in built['objects']}
    for grid in descriptors(scoped):
        if any(nodes.get(name,{}).get('render_type') not in ('photo','svg') for name in grid['objects']):
            raise ValueError('Each source_grid cell requires its own actual photo/svg object')

def validate_frames(state,scene,frames):
    nodes={o['id']:o for o in scene['objects']}
    for grid in descriptors(state):
        owners=set(grid['objects'])
        matches=[f for f in frames if f.get('kind')=='grid' and {m['object'] for m in f.get('members',[])}==owners
                 and f.get('rows')==grid['rows'] and f.get('columns')==grid['columns']]
        if len(matches)!=1:raise ValueError('A frozen source_grid needs one matching shared frame for all cells: '+grid['owner'])
        members={m['object']:m for m in matches[0]['members']}
        frame=matches[0]
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=2 for v in frame.get('gap',[0,0])):
            raise ValueError('Source image grids use compact shared gaps of at most two source pixels')
        for field in ('row_weights','column_weights'):
            weights=frame.get(field,[])
            if weights and max(weights)-min(weights)>1e-6:
                raise ValueError('Source image grid rows and columns use equal shared track sizes')
        for index,name in enumerate(grid['objects']):
            row=members[name]
            if (nodes.get(name,{}).get('render_type') not in ('photo','svg') or row.get('operation')!='cover'
                    or row.get('row')!=index//grid['columns'] or row.get('column')!=index%grid['columns']):
                raise ValueError('Source grid cells retain their original order and fill the shared content frame')
