"""Compile host judgments into finite policies covering the complete result."""
import copy,math
from .common import ROOT,digest,identity,read_json,write_json,safe_path,writer

VERSION='quality-intent-1'
PURPOSES={'illustrative','decorative','scientific','photo_identity','structure','text','formula','relation'}
REPRESENTATIONS={'native','svg','raster','mixed','group','native_math','native_table'}
RELIABILITY={'observed','approximate','inferred','unresolved'}

def _bounds(rows):
    known={'ssim','boundary_f1','clarity_second','clarity_ratio','color_histogram_tv','mean_absolute_rgb_error'}
    if not isinstance(rows,list) or not rows:raise ValueError('Explicit bounded image constraints required')
    for row in rows:
        if not isinstance(row,dict) or row.get('id') not in known or set(row)-{'id','min','max'} or not any(k in row for k in ('min','max')):
            raise ValueError('Use a finite supported fixed-frame metric bound')
        if any(type(row[k]) not in (int,float) or not math.isfinite(row[k]) for k in ('min','max') if k in row):
            raise ValueError('Metric bounds must be finite numbers')
        if 'min' in row and 'max' in row and row['min']>row['max']:raise ValueError('Metric interval is empty')

def _clarity_band(value):
    if not isinstance(value,list) or len(value)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in value) or not 0<value[0]<=value[1]:
        raise ValueError('Freeze a positive finite actual-size clarity band before construction')

def profiles():
    value=read_json(ROOT/'config/quality-intents.json')
    metrics={'source_ssim','source_boundary','approved_clarity','approved_style','native_construction',
             'source_color','source_texture','layout_integrity','content_fidelity','relation_integrity'}
    if set(value['profiles'])!=PURPOSES:raise ValueError('Every finite purpose needs a profile')
    for weights in value['profiles'].values():
        if not weights or set(weights)-metrics or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in weights.values()) or abs(sum(weights.values())-1)>1e-9:
            raise ValueError('Profile weights must be known, finite, positive and sum to one')
    return value

def source_declaration(value,profile):
    if not isinstance(value,dict) or value.get('purpose') not in PURPOSES or value.get('appearance_target') not in ('source','design','approved'):
        raise ValueError('Classify source purpose and appearance target before constructing a new part')
    if profile in ('text','formula','relation') and value['purpose']!=profile:
        raise ValueError('Critical content/relationship purpose cannot be classified as an illustration')
    if not value.get('basis') or not value.get('source_reliability') or any(v not in RELIABILITY for v in value['source_reliability'].values()):
        raise ValueError('Source classification needs a semantic basis and per-property reliability')
    goal=value['appearance_target']
    if goal=='source' and not value.get('source_constraints'):
        raise ValueError('Freeze explicit source correspondence bounds before construction')
    if goal=='design' and not value.get('design_contract',{}).get('constraints'):
        raise ValueError('Freeze the design constraints before construction')
    if goal=='approved' and not value.get('approved_reference'):
        raise ValueError('Freeze the already approved artifact identity before construction')
    if goal=='source':_bounds(value['source_constraints'])
    if goal=='design':_bounds(value['design_contract']['constraints'])
    if goal!='approved' and value['purpose'] in ('illustrative','decorative','text','formula'):
        _clarity_band(value.get('design_contract',{}).get('clarity_band'))
    return copy.deepcopy(value)

def discover(task,state,candidate):
    from .execution_contract import inventory
    inv,_,_=inventory(task,state,candidate)
    return {'schema':VERSION,'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],
        'native_names':inv['native_names'],'inventory_hash':identity(inv['native_names']),'groups':inv['groups'],'parents':inv['parents'],
        'units':[{'id':u['id'],'profile':u['profile'],'objects':u.get('objects',[]),'roi':u['roi'],
                  'source_view':source_view(task,state,u['roi']),
                  'quality_intent':copy.deepcopy(u.get('quality_intent')),
                  'source_properties':[{'id':f['id'],'category':f['category'],'status':f['status'],'expected':f['expected']} for f in u['features']]}
                 for u in state.get('quality',{}).get('units',{}).values()],
        'purposes':sorted(PURPOSES),'profiles_hash':identity(profiles()),
        'instruction':'The host classifies purpose/representation/reliability and source meaning. The compiler validates whole coverage; write scope never limits this inventory.'}

def _ref(task,ref):
    file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Frozen quality-policy resource changed: '+ref['path'])
    return file

def source_view(task,state,roi,scale=2):
    from PIL import Image
    from .source_quality import source_pixel_box
    x,y,w,h=roi;size=state['source_size']
    box=(max(0,math.floor(x)),max(0,math.floor(y)),min(size[0],math.ceil(x+w)),min(size[1],math.ceil(y+h)))
    if box[2]<=box[0] or box[3]<=box[1]:raise ValueError('Empty original semantic view')
    if type(scale) is not int or not 1<=scale<=4:raise ValueError('Bounded original semantic view scale required')
    key=identity({'source':state['source'],'box':box,'scale':scale});path=task/'source/intent-views'/(key+'.png')
    if not path.is_file():
        path.parent.mkdir(parents=True,exist_ok=True)
        from .resource_facts import image_region
        with image_region(_ref(task,state['source']),[('crop',box),('convert','RGB'),
            ('resize',((box[2]-box[0])*scale,(box[3]-box[1])*scale),Image.Resampling.LANCZOS)],state['source']['sha256'],mode=None) as crop:
            crop.save(path)
    return {'path':path.relative_to(task).as_posix(),'sha256':digest(path),'source_hash':state['source']['sha256'],
            'roi':[box[0],box[1],box[2]-box[0],box[3]-box[1]],'scale':scale}

def compile_plan(task,state,candidate,request):
    from .execution_contract import inventory
    inv,_,nodes=inventory(task,state,candidate);units=state.get('quality',{}).get('units',{})
    if request.get('schema')!=VERSION or request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('A quality intent needs a current source-bound schema')
    if request.get('inventory_hash')!=identity(inv['native_names']):raise ValueError('Quality intent must cover the actual complete saved inventory')
    authority=request.get('authority')
    if not authority or not request.get('reason'):raise ValueError('Freeze the actual user goal/authority and explain policy changes')
    _ref(task,authority)
    approved=request.get('approved')
    if approved:
        for key in ('pptx','preview','render'):_ref(task,approved[key])
        render=read_json(_ref(task,approved['render']))
        if render.get('pptx_hash')!=approved['pptx']['sha256'] or render.get('preview_hash')!=approved['preview']['sha256']:
            raise ValueError('Approved appearance must have an exact actual render')
        if approved.get('source_hash')!=state['source']['sha256'] or not approved.get('approval_basis'):
            raise ValueError('Approved appearance needs source identity and precise user approval scope')
    items=request.get('items',[])
    if not items or len({r.get('id') for r in items})!=len(items):raise ValueError('Unique policy item identifiers required')
    source_coverage=set();native_coverage=set();compiled=[];configuration=profiles()
    for row in items:
        if row.get('purpose') not in PURPOSES or row.get('representation') not in REPRESENTATIONS:
            raise ValueError('Use a declared semantic purpose and representation')
        names=row.get('objects',[]);uids=row.get('quality_units',[])
        if not names or len(set(names))!=len(names) or not set(names)<=set(nodes):
            raise ValueError('Bind exact unique current native objects: '+str(row.get('id')))
        if not set(uids)<=set(units):raise ValueError('Unknown source quality unit')
        if not row.get('source_evidence') or not row.get('source_facts'):
            raise ValueError('Every policy needs original source evidence and meaningful semantic facts')
        view=row['source_view'];_ref(task,view)
        if view.get('source_hash')!=state['source']['sha256'] or source_view(task,state,view['roi'],view['scale'])!=view:
            raise ValueError('Policy source view belongs to another image')
        reliability=row.get('source_reliability',{})
        if not reliability or any(v not in RELIABILITY for v in reliability.values()):
            raise ValueError('Declare source reliability per property')
        if 'unresolved' in reliability.values():raise ValueError('Resolve important source uncertainty before freezing a policy')
        for uid in uids:
            profile=units[uid]['profile']
            if profile in ('text','formula','relation') and row['purpose']!=profile:
                raise ValueError('Text, formulas and scientific relationships cannot inherit an aesthetic exemption')
            declaration=units[uid].get('quality_intent')
            if declaration:
                if declaration.get('purpose')!=row['purpose']:
                    raise ValueError('Final purpose contradicts the frozen pre-construction declaration; revise source evidence explicitly')
                declared_goal=declaration['appearance_target'];actual_goal=row.get('appearance_target')
                if actual_goal=='baseline':actual_goal='approved'
                correction=row.get('source_content_correction',{})
                source_repair=(actual_goal=='source_content' and row['purpose']=='text' and correction.get('unit')==uid
                    and correction.get('inherited_appearance_target')==declared_goal)
                if actual_goal!=declared_goal and not source_repair:
                    raise ValueError('Final appearance authority contradicts the pre-construction declaration; use an evidence-preserving source correction')
                if any(row.get('source_reliability',{}).get(k)!=v for k,v in declaration['source_reliability'].items()):
                    raise ValueError('Final source reliability contradicts the frozen original interpretation')
                for key in ('design_contract','source_constraints'):
                    if key in declaration and identity(declaration[key])!=identity(row.get(key)):
                        raise ValueError('Final '+key+' differs from the frozen pre-construction bounds; a candidate cannot redefine its target')
                if declaration.get('approved_reference'):
                    ref=declaration['approved_reference']
                    if any(ref.get(k)!=(approved or {}).get(k,{}).get('sha256') for k in ('pptx','preview')):
                        raise ValueError('Final approved style is not the immutable pre-construction reference')
        goal=row.get('appearance_target')
        if goal not in ('approved','baseline','source','design','source_content'):raise ValueError('Choose a frozen appearance target')
        if goal in ('approved','baseline') and not approved:raise ValueError('Approved/protected appearance needs its immutable actual artifact')
        if goal=='source_content':
            from .source_text_actions import runs
            correction=row.get('source_content_correction',{});uid=correction.get('unit')
            reading=state.get('source_readings',{}).get('records',{}).get(uid)
            if not approved or row['purpose']!='text' or not reading or correction.get('reading_hash')!=identity(reading):
                raise ValueError('Source text correction needs the immutable earlier artifact and independent current source reading')
            runs(reading['formatted_runs'])
            if names!=units[uid]['objects'] or len(names)!=1:raise ValueError('Exactly one independently read source text owner required')
        if row['purpose'] in ('scientific','photo_identity') and goal!='source':
            raise ValueError('Scientific/identity images retain their source fidelity target')
        if row['purpose'] in ('illustrative','decorative') and goal in ('approved','baseline','design') and row.get('raw_pixel_gate'):
            raise ValueError('EVALUATION_POLICY_MISMATCH: enhancement cannot be vetoed by blurry source pixel matching')
        if goal=='design' and not row.get('design_contract'):
            raise ValueError('A new design needs explicit pre-candidate appearance/construction bounds')
        if goal=='source':_bounds(row.get('source_constraints'))
        if goal=='design':_bounds(row['design_contract'].get('constraints'))
        if not approved and row['purpose'] in ('illustrative','decorative','text','formula'):
            band=row.get('design_contract',{}).get('clarity_band')
            _clarity_band(band)
        if row.get('scope') not in (None,'whole_item'):
            raise ValueError('A local edit/check selection cannot shrink policy coverage')
        native_coverage.update(names);source_coverage.update(uids)
        compiled.append({**copy.deepcopy(row),'weights':configuration['profiles'][row['purpose']],
            'hard_gates':configuration['hard_gates'],'legacy_targets':{uid:copy.deepcopy(units[uid]['metrics']) for uid in uids},
            'policy_note':'Legacy source values remain measured diagnostics. Active gates follow this versioned purpose, invariants and appearance authority.'})
    missing_native=set(inv['native_names'])-native_coverage;missing_source=set(units)-source_coverage
    if missing_native or missing_source:raise ValueError('Whole policy coverage missing: native='+str(sorted(missing_native)[:12])+' source='+str(sorted(missing_source)[:12]))
    by_id={r['id']:r for r in compiled}
    for row in compiled:
        parent=row.get('semantic_parent')
        if parent:
            ancestor=by_id.get(parent)
            if not ancestor or ancestor.get('semantic_parent') or parent==row['id'] or not set(row['objects'])<=set(ancestor['objects']):
                raise ValueError('A semantic review may inherit only from one complete direct reviewed root covering all of its actual owners')
            row['semantic_review_scope']='Named child reviewed in the complete source-bound root; all numeric/content/construction checks remain individual'
    return {**copy.deepcopy(request),'items':compiled,'profile_configuration':configuration,
            'compiled_hash':identity(compiled),'native_count':len(inv['native_names']),'unit_count':len(units)}

def bind(task,request):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected')
    if not candidate or not candidate.get('render'):raise ValueError('Freeze policies against a complete saved actual render')
    value=compile_plan(task,state,candidate,request)
    previous=state.get('quality_intent')
    if previous and previous.get('compiled_hash')!=value['compiled_hash']:
        if request.get('prior_hash')!=identity(previous) or not request.get('revision_reason'):
            raise ValueError('Retain prior policy and explain an explicit policy revision; do not tune weights after measurement')
        state.setdefault('quality_intent_history',[]).append(previous)
    with writer(task):
        state['objectives']['whole_quality_intent']=True
        state['quality_intent']=value;state.pop('quality_result',None);state.pop('acceptance',None)
        a._event(task,'whole_quality_intent_compiled',{'items':len(value['items']),'native_count':value['native_count'],
            'legacy_units':value['unit_count'],'policy':value['compiled_hash'],'drawing_gain':False})
        a._save(task,state)
    return {'status':'WHOLE_QUALITY_INTENT_BOUND','policy_items':len(value['items']),
            'native_count':value['native_count'],'source_units':value['unit_count'],'profile_hash':identity(profiles())}

def validate(task,state,candidate):
    value=state.get('quality_intent')
    if not value:raise ValueError('Whole quality intent is required')
    request=copy.deepcopy(value)
    for row in request['items']:
        for k in ('weights','hard_gates','legacy_targets','policy_note','semantic_review_scope'):row.pop(k,None)
    for k in ('compiled_hash','native_count','unit_count','profile_configuration'):request.pop(k,None)
    current=compile_plan(task,state,candidate,request)
    if current['compiled_hash']!=value['compiled_hash'] or current['profile_configuration']!=value['profile_configuration']:
        raise ValueError('Quality policy is stale or its frozen profile configuration changed')
    return value
