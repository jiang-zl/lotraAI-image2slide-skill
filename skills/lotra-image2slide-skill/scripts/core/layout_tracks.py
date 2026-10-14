"""Original sibling text lanes, shared native slots and contextual checks."""
import statistics,re
from .common import identity
from .mathml import NS

def compile_tracks(containers,elements,source_owners,native=None):
    owners={r['object']:r for r in source_owners};result=[]
    for c in containers.values():
        groups={}
        for mid in c['members']:
            if mid not in elements:continue
            e=elements[mid];names=[e['mathematical_owner']] if e.get('mathematical_owner') else e['objects']
            if len(names)!=1 or names[0] not in owners:continue
            r=owners[names[0]];prefix=''.join(s.get('text','') for p in r['paragraphs'] for s in p)
            prefix=re.sub(r'\s*[0-9]+\s*$','',prefix).strip()
            if len(prefix)<4:continue
            groups.setdefault(prefix,[]).append((mid,names[0],e['source_bbox']))
        for prefix,rows in groups.items():
            if len(rows)<2:continue
            rows.sort(key=lambda v:v[2][1]);width=max(v[2][2] for v in rows)
            lefts=[v[2][0] for v in rows];ends=[v[2][0]+v[2][2] for v in rows]
            if max(lefts)-min(lefts)>max(2.,width*.15) or max(ends)-min(ends)>max(2.,width*.15):continue
            if any(a[2][1]+a[2][3]>b[2][1] for a,b in zip(rows,rows[1:])):continue
            typography=None
            if native is not None:
                styles=[style(native[v[1]]['node']) for v in rows]
                families={s['font'] for s in styles}
                sizes=[float(s['properties']['sz'])/100 for s in styles if s['properties'] and s['properties'].get('sz')]
                if len(families)!=1 or None in families or len(sizes)!=len(rows):raise ValueError('Resolve original repeated-role typography before freezing a lane')
                typography={'font_size_pt':statistics.median(sizes),'font_family':styles[0]['font'],
                    'basis':'authorized shared-role normalization; median initial font estimate, not an exact source point-size claim'}
            result.append({'id':'text-lane:'+identity([c['id'],prefix])[:16],'container':c['id'],
                'members':[v[0] for v in rows],'objects':[v[1] for v in rows],
                'source_prefix':prefix,'source_slot':[statistics.median(lefts),width],
                'tolerance_px':max(.75,min(1.5,width*.01)),
                'source_evidence':'Repeated original prose role in distinct rows of one direct semantic parent; equal slot width and left paragraph anchor',
                'context_members':list(c['members']),'typography':typography})
    return result

def target(track,containers,native):
    c=containers[track['container']];d=c['domain']
    if d['kind'] not in ('native_body','native_table'):raise ValueError('Text lane requires a measured physical parent frame')
    x,y,w,h=native[d['object']]['frame'];sx,sy,sw,sh=c['source_bbox'];scale=w/sw
    left,width=track['source_slot'];left=statistics.median(native[n]['frame'][0] for n in track['objects'])
    return left,width*scale

def style(node):
    run=node.find('.//a:r/a:rPr',NS)
    if run is None:run=node.find('.//a:pPr/a:defRPr',NS)
    return {'properties':{k:run.get(k,'0') for k in ('sz','b','i','spc')} if run is not None else None,
        'font':run.find('a:latin',NS).get('typeface') if run is not None and run.find('a:latin',NS) is not None else None}

def report(tracks,containers,native,paint):
    results=[]
    for tr in tracks:
        row={**tr,'passed':False}
        try:
            left,width=target(tr,containers,native);tol=tr['tolerance_px'];items=[];glyphs=[];styles=[]
            for name in tr['objects']:
                n=native[name];x,y,w,h=n['frame'];node=n['node'];p=node.find('.//a:pPr',NS)
                if name not in paint or paint[name]['method']!='ACTUAL_HOST_OWNER_MATTE':raise ValueError('Contextual lane needs actual visible owner glyphs: '+name)
                g=paint[name]['geometry'];glyphs.append(g.bounds[0]);styles.append(style(node))
                items.append({'object':name,'left_error_px':x-left,'right_error_px':x+w-left-width,
                    'paragraph_alignment':p.get('algn','l') if p is not None else 'l',
                    'passed':max(abs(x-left),abs(x+w-left-width))<=tol and (p is None or p.get('algn','l')=='l')})
            uniform=all(v==styles[0] for v in styles)
            if tr.get('typography'):
                uniform &= all(s['font']==tr['typography']['font_family'] and s['properties']['sz']==str(round(tr['typography']['font_size_pt']*100)) for s in styles)
            row.update(items=items,glyph_start_spread_px=max(glyphs)-min(glyphs),uniform_prose_typography=uniform,
                passed=all(v['passed'] for v in items) and max(glyphs)-min(glyphs)<=tol and uniform,
                status='MEASURED',context_review_required=True)
        except (ValueError,KeyError,TypeError) as e:row.update(status='required_unmeasured',reason=str(e))
        results.append(row)
    return {'passed':all(r['passed'] for r in results),'items':results,'scope':'Every original repeated prose lane, native slot endpoints and actual glyph starts; independent context view'}

def repair_plan(task,state,candidate,request,contract,native):
    from .recursive_containment import VERSION
    selected=request.get('tracks');tracks={t['id']:t for t in contract['alignment_tracks']}
    if not selected or len(set(selected))!=len(selected) or not set(selected)<=set(tracks):raise ValueError('Known source text lane identities required')
    cs={c['id']:c for c in contract['containers']};sizes={};alignment={};writes={};typography={}
    for key in selected:
        row=tracks[key];left,width=target(row,cs,native)
        for name in row['objects']:
            x,y,w,h=native[name]['frame']
            if max(abs(left-x),abs(width-w))>request.get('max_translation_px',0):raise ValueError('Source lane correction exceeds frozen explicit change bound')
            required={'position.x','geometry.width','text_alignment'}|({'font_size'} if row.get('typography') else set())
            if not required<=set(request.get('write_set',{}).get(name,[])):raise ValueError('Narrow native frame and alignment grant required')
            sizes[name]=[left,y,width,h];alignment[name]='l';writes[name]=sorted(required)
            if row.get('typography'):typography[name]=row['typography']
    return {'kind':VERSION,'source_contract':state['recursive_containment'],'alignment_tracks':selected,
        'translations':{},'body_sizes':sizes,'paragraph_alignment':alignment,'lane_typography':typography,'write_set':writes,
        'check_set':[c['id'] for c in contract['containers']],'protected_set':sorted(set(native)-set(sizes)),
        'solver':'Original sibling lanes to shared native text slots; no content/font changes',
        'next':'Actual PowerPoint render, visible glyph starts, complete relation checks and original/current contextual enlarged views'}
