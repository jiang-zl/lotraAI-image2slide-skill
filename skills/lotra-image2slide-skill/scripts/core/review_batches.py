"""Independent enlarged source/result tiles, batched without averaged scores."""
import math
from pathlib import Path
from PIL import Image,ImageDraw
from .common import digest,read_json,write_json,canonical


def prepare(task,request):
    from . import agent_runtime as a,source_quality as q
    task,state=a._state(task)
    targets=request.get('targets',[])
    if not 1<=len(targets)<=8 or len(set(targets))!=len(targets):
        raise ValueError('Batch at most eight independent located requirements')
    candidate=state.get('selected')
    if not candidate or request.get('baseline_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Batch must bind the saved selected result')
    units=[]
    for target in targets:
        value=q.unit(state,target)
        if not value or value['status']=='minimum_met':
            raise ValueError('Only unresolved source-part requirements belong in a review batch')
        units.append(value)
    def context_window(value):
        x,y,w,h=value['roi']
        margin=min(12,max(3,round(min(w,h)*.12)))
        return (max(0,math.floor(x)-margin),max(0,math.floor(y)-margin),
                min(state['source_size'][0],math.ceil(x+w)+margin),
                min(state['source_size'][1],math.ceil(y+h)+margin))
    windows=[context_window(u) for u in units]
    boxes=[[b[0],b[1],b[2]-b[0],b[3]-b[1]] for b in windows]
    left=min(b[0] for b in boxes);top=min(b[1] for b in boxes)
    right=max(b[0]+b[2] for b in boxes);bottom=max(b[1]+b[3] for b in boxes)
    # Existing revisit handles selected hashes, pending writes and observation
    # debt. It retires an unexecuted repair rather than bypassing its protection.
    for target in targets:
        if target not in state.get('review_queue',[]):state.setdefault('review_queue',[]).append(target)
    a._save(task,state)
    response=a.revisit(task,{'baseline_hash':request['baseline_hash'],
        'roi':[left,top,right-left,bottom-top],
        'reason':request.get('reason','Observe independent enlarged source/result parts and their frozen obligations.')})
    task,state=a._state(task);packet=state['packet'];directory=task/'views'/packet['packet_id'];directory.mkdir()
    source=Image.open(task/state['source']['path']).convert('RGB')
    actual=Image.open(task/candidate['preview']['path']).convert('RGB')
    part_views=[];records=[];rows=[]
    for value,target,box in zip(units,targets,windows):
        x,y,w,h=value['roi']
        # Tiny parts still receive a large magnification; an already large
        # natural surface is bounded by the display width instead of rejected.
        # Make a small natural icon large enough to inspect without spending
        # most of the board on blank columns. Both roles keep the exact same
        # original window and scale; no per-result registration is introduced.
        window_width,window_height=box[2]-box[0],box[3]-box[1]
        factor=min(max(3,300/max(w,h),72/h),720/window_width,420/window_height)
        if h*factor<36:
            raise ValueError('Narrow a long thin source requirement into meaningful endpoints/detail units first')
        size=(max(1,round((box[2]-box[0])*factor)),max(36,round((box[3]-box[1])*factor)))
        pair=[]
        for role,image in (('source',source),('current',actual)):
            sx,sy=image.width/state['source_size'][0],image.height/state['source_size'][1]
            native_box=(box[0]*sx,box[1]*sy,box[2]*sx,box[3]*sy)
            crop=image.resize(size,Image.Resampling.LANCZOS,box=native_box)
            path=directory/(value['id'].replace(':','-')+'-'+role+'.png');crop.save(path)
            part_views.append({'unit':target,'role':role,'roi':value['roi'],'display_size':list(size),
                               'source_pixel_window':list(box),'context_roi':[box[0],box[1],box[2]-box[0],box[3]-box[1]],
                               'metric_scope':'independent original roi remains fixed; exterior context discovers clipping/relations, not score compensation',
                               'mapping':'one fixed source window; one native sampling; no local registration',
                               'path':path.relative_to(task).as_posix(),'sha256':digest(path)})
            pair.append(crop)
        rows.append((target,pair))
        diagnostic=q.evaluate(task,state,candidate,value)
        records.append({'target':target,'required_observations':q.observation_contract(value),
            'diagnostic':diagnostic,'source_trace':{'objects':value['objects'],'roi':value['roi']}})
    column_width=max(360,max(pair[0].width for _,pair in rows)+12)
    board=Image.new('RGB',(2*column_width,sum(max(pair[0].height,72)+40 for _,pair in rows)),'white');d=ImageDraw.Draw(board);yy=0
    for target,pair in rows:
        d.text((5,yy+5),target+' SOURCE + BOUNDED CONTEXT',fill='black');d.text((column_width+5,yy+5),target+' ACTUAL SAVED PPTX + SAME CONTEXT',fill='black')
        for col,crop in enumerate(pair):board.paste(crop,(col*column_width+5,yy+28))
        yy+=max(pair[0].height,72)+40
    board_path=directory/'paired-parts.png';board.save(board_path)
    records_path=directory/'obligations.json';write_json(records_path,records)
    packet['views'].append({'role':'paired-board','roi':[left,top,right-left,bottom-top],
        'path':board_path.relative_to(task).as_posix(),'sha256':digest(board_path),
        'meaning':'Each labelled row has its own fixed source ROI and enlarged actual saved-result view; no batch score'})
    packet['part_views']=part_views
    packet['batch']={'targets':targets,'obligations':a._file(task,records_path),
        'return':'coverage[{target,observations with each exact requirement ID/expected/actual/outcome}], findings located by owner and quality_unit; no blanket matched'}
    state['packet']=packet;a._save(task,state);write_json(task/'current-packet.json',packet)
    return {'status':'WORK_PACKET','task':str(task),'packet':packet}
