"""Versioned, local, data-only CS recipe memory with evidence-based promotion.

Library entries never execute code or become instructions. User source images
stay in their task; only authorized reusable geometry/parameters are retained.
"""
import copy
from pathlib import Path
from .common import identity, canonical, safe_path, digest, read_json, write_json, writer
from .recipes import RECIPES, instantiate
from .source_analysis import postorder

VERSION='cs-knowledge-1.0.0'
SCOPES={'task_local','library_local','distributable'}


def library_path(explicit=None,project=None):
    """Resolve a persistent task/project store without scanning other projects.

    Resolution is read-only. Entries, use feedback and promotion still require
    their explicit commands and evidence. Never mutate an installed runtime.
    """
    from .common import ROOT
    if explicit is not None and project is not None:
        raise ValueError('Choose an explicit library or a project, not both')
    location=Path(explicit).expanduser().resolve() if explicit is not None else (Path(project or Path.cwd()).expanduser().resolve()/'.lotraAI-build/library')
    if location==ROOT.resolve() or location.is_relative_to(ROOT.resolve()):
        raise ValueError('Knowledge belongs outside the installed skill; provide --project or --library')
    return location


def template_from_scene(scene,root_id,*,include_text=False):
    """Extract one owned native subtree, with no external task dependencies.

    This creates a candidate only. License review and positive/negative/reuse
    promotion are still required before retrieval can offer the component.
    """
    objects={o['id']:o for o in scene['objects']}
    if root_id not in objects or objects[root_id]['render_type']!='group':
        raise ValueError('Learned native component must have a group owner')
    selected={root_id}
    while True:
        expanded=selected|{o['id'] for o in objects.values() if o.get('parent') in selected}
        if expanded==selected:break
        selected=expanded
    mapping={key:'root' if key==root_id else 'part_'+str(i) for i,key in enumerate(sorted(selected))}
    parts=[]
    for original in scene['objects']:
        if original['id'] not in selected:continue
        if original['render_type'] in ('text','equation') and not include_text:
            raise ValueError('Literal text/math retention requires include_text')
        part={k:copy.deepcopy(original[k]) for k in ('id','render_type','semantic_type','bbox','content','style')}
        part['id']=mapping[original['id']]
        part['parent']=mapping.get(original.get('parent'))
        for field in ('source','target','source_anchor_object','target_anchor_object'):
            if part['content'].get(field):
                if part['content'][field] not in mapping:raise ValueError('Component contains an external connector dependency')
                part['content'][field]=mapping[part['content'][field]]
        parts.append(part)
    recipe={'name':'native_template','parameters':{'objects':parts}}
    instantiate(recipe['name'],recipe['parameters'],'validation',[0,0,100,100])
    return recipe


def validate_entry(entry):
    if entry.get('version')!='knowledge-entry-1':raise ValueError('Unknown knowledge entry')
    for field in ('name','semantic_class','view','style_tags','parts','edit_operations','limitations','provenance'):
        if not entry.get(field):raise ValueError('Missing knowledge field: '+field)
    if entry.get('scope') not in SCOPES:raise ValueError('Unknown knowledge retention scope')
    recipe=entry.get('recipe',{})
    if recipe.get('name') not in RECIPES:raise ValueError('Knowledge must use a registered deterministic recipe')
    if not isinstance(recipe.get('parameters'),dict):raise ValueError('Recipe parameters must be data')
    instantiate(recipe['name'],recipe['parameters'],'probe',[0,0,100,100])
    provenance=entry['provenance']
    if provenance.get('origin') not in ('original_geometry','task_observation','licensed_external'):
        raise ValueError('Unknown knowledge origin')
    if entry['scope']=='distributable' and (provenance.get('license') not in ('CC0-1.0','MIT','Apache-2.0','project-original') or
       not provenance.get('redistribution_authorized')):
        raise ValueError('Public recipe needs explicit redistribution provenance')
    if not isinstance(entry.get('evidence_refs'),list) or not entry['evidence_refs']:
        raise ValueError('Knowledge without task evidence cannot be learned')
    # Knowledge is a compact recipe, never a whole source image/scene/prompt log.
    if len(canonical(entry))>32768:raise ValueError('Knowledge entry exceeds compact data budget')
    return identity(entry)


def _generic_constructor(entry):
    """The legacy JSON menu may share geometry, never another task's facts."""
    if entry.get('scope') not in ('library_local','distributable'):return False
    blocked={'source_hash','source_roi','source_image','source_path','source_facts','original','pptx','preview','task_id','evidence_refs'}
    def pure(value):
        if isinstance(value,dict):
            if blocked&set(value) or value.get('render_type') in ('text','equation','image','raster'):return False
            return all(pure(x) for x in value.values())
        if isinstance(value,list):return all(pure(x) for x in value)
        if isinstance(value,str):
            import re
            return not ('.lotraAI-build' in value or '/home/' in value or value.startswith('\\\\') or
                        re.search(r'[A-Za-z]:[\\/]|data:image|<image\b|\.(?:pptx|png|jpe?g|pdf)(?:$|[?#])',value,re.I))
        return True
    return pure(entry.get('recipe',{}))


def _retrieval_metadata(entry,path):
    return {'schema':'generic-knowledge-menu-1','entry_sha256':digest(path),
            'generic_constructor':_generic_constructor(entry),'scope':entry['scope'],
            **{key:copy.deepcopy(entry[key]) for key in ('semantic_class','view','parts','style_tags','edit_operations')}}


def capture(entry,library):
    key=validate_entry(entry);library=Path(library)
    with writer(library):
        path=library/'entries'/key/'entry.json'
        if path.exists():
            if read_json(path)!=entry:raise ValueError('Content-addressed knowledge collision')
        else:
            write_json(path,entry)
            write_json(path.with_name('state.json'),{'status':'candidate','uses':0,'successes':0,'failures':0,'history':[],
                       'retrieval_metadata':_retrieval_metadata(entry,path)})
    from .knowledge_flow import sync_legacy
    sync_legacy(library,key)
    return {'id':key,'status':read_json(path.with_name('state.json'))['status'],'path':str(path)}


def promote(library,key,evaluations,base):
    library=Path(library);folder=safe_path(library,'entries/'+key)
    entry=read_json(folder/'entry.json');validate_entry(entry)
    observed=set();records=[]
    for ref in evaluations:
        path=safe_path(base,ref['path'])
        if digest(path)!=ref['sha256']:raise ValueError('Knowledge evaluation changed')
        report=read_json(path)
        if report.get('version')!='knowledge-evaluation-1' or report.get('entry_hash')!=key:
            raise ValueError('Evaluation targets another recipe')
        kind=report.get('kind')
        if kind not in ('positive','counterexample','reuse'):raise ValueError('Unknown knowledge evaluation role')
        checks=report.get('checks',[])
        if not checks:raise ValueError('Empty validation is not evidence')
        for check in checks:
            if not check.get('name') or check.get('actual') not in ('PASS','FAIL') or check.get('actual')!=check.get('expected'):
                raise ValueError('Knowledge regression did not meet its expected outcome')
        if kind=='counterexample' and not any(c['actual']=='FAIL' for c in checks):
            raise ValueError('Counterexample must demonstrate rejection')
        if kind!='counterexample' and any(c['actual']!='PASS' for c in checks):raise ValueError('Positive/reuse must pass')
        artifacts=report.get('artifacts',[])
        if not artifacts:raise ValueError('Evaluation must bind actual artifacts')
        for artifact in artifacts:
            if digest(safe_path(base,artifact['path']))!=artifact['sha256']:raise ValueError('Knowledge evaluation artifact changed')
        observed.add(kind);records.append({'kind':kind,'evaluation_hash':digest(path)})
    if observed!={'positive','counterexample','reuse'}:raise ValueError('Promotion requires positive, negative and reuse checks')
    with writer(library):
        state=read_json(folder/'state.json')
        if state['status'] in ('quarantined','revoked'):
            raise ValueError('Quarantined/revoked knowledge requires a repaired new entry identity')
        state['status']='promoted';state['history'].append({'action':'promote','evaluations':records})
        state['retrieval_metadata']=_retrieval_metadata(entry,folder/'entry.json')
        write_json(folder/'state.json',state)
    from .knowledge_flow import sync_legacy
    sync_legacy(library,key)
    return {'id':key,'status':'promoted','scope':entry['scope'],'evidence':records}


def record_use(library,key,*,success,evidence_hash):
    if type(success) is not bool or not isinstance(evidence_hash,str) or len(evidence_hash)!=64:
        raise ValueError('Knowledge use needs measured outcome and evidence identity')
    library=Path(library);folder=safe_path(library,'entries/'+key)
    with writer(library):
        state=read_json(folder/'state.json')
        token=identity({'success':success,'evidence':evidence_hash})
        if token in state.get('use_tokens',[]):return {'id':key,'status':state['status'],'uses':state['uses'],'changed':False}
        state.setdefault('use_tokens',[]).append(token);state['uses']+=1
        state['successes' if success else 'failures']+=1
        state['history'].append({'action':'use','success':success,'evidence_hash':evidence_hash})
        if not success and state['status']!='revoked':state['status']='quarantined'
        write_json(folder/'state.json',state)
    from .knowledge_flow import sync_legacy
    sync_legacy(library,key)
    return {'id':key,'status':state['status'],'uses':state['uses'],'changed':True,'history_reference':str(folder/'state.json')}


def revoke(library,key,reason):
    if not reason:raise ValueError('Revocation needs a reason')
    library=Path(library);folder=safe_path(library,'entries/'+key)
    with writer(library):
        state=read_json(folder/'state.json');state['status']='revoked'
        state['history'].append({'action':'revoke','reason':reason});write_json(folder/'state.json',state)
    from .knowledge_flow import sync_legacy
    sync_legacy(library,key)
    return {'id':key,'status':state['status'],'changed':True,'history_reference':str(folder/'state.json')}


def retrieve(library,query,*,limit=3,max_chars=2400,public_only=False):
    from .knowledge_flow import find
    return find(library,{**query,'public_only':public_only},limit=limit,max_chars=min(12000,max_chars))


def task_suggestions(library,analysis,*,base=None,max_entries=8,max_chars=6000):
    if base is not None:
        from .source_analysis import validate
        validate(analysis,base)
    if not 1<=max_entries<=40 or max_chars<256:raise ValueError('Bounded suggestion menu required')
    nodes={n['id']:n for n in analysis.get('nodes',[])};entries={};bindings=[];memo={};used=0
    for node_id in postorder(analysis):
        n=nodes[node_id]
        if n.get('status')=='unresolved':continue
        query={'semantic_class':n['semantic_class'],'view':n['view'],'style_tags':n.get('style_tags',[]),
               'edit_operations':n.get('edit_targets',[]),'required_parts':[c['semantic_class'] for c in nodes.values() if c.get('parent')==node_id]}
        qid=identity(query)
        if qid not in memo:memo[qid]=retrieve(library,query,limit=2,max_chars=min(2400,max_chars))
        for item in memo[qid]['entries']:
            size=len(canonical(item).decode()) if item['id'] not in entries else 0
            if used+size>max_chars or item['id'] not in entries and len(entries)>=max_entries:continue
            entries[item['id']]=item;used+=size
            binding={'object_id':node_id,'knowledge_id':item['id']}
            if used+len(canonical(binding))<=max_chars:bindings.append(binding);used+=len(canonical(binding))
    return {'schema_version':'task-knowledge-suggestions-2','analysis_hash':identity(analysis),
            'entries':list(entries.values()),'bindings':bindings,'characters':used,'recipes_in_context':False}


def record_use_from_utility(library, utility_file):
    """Feed a measured comparison back to the selected recipe's local state.

    Neutral, tradeoff and unmeasured outcomes cannot be compressed into a
    success/failure label; retain the report without altering recipe ranking.
    """
    utility_file = Path(utility_file)
    report = read_json(utility_file)
    key = report.get('knowledge_id')
    result = report.get('measurements', {}).get('result')
    if not isinstance(key, str) or not key:
        raise ValueError('Utility report is not bound to a knowledge entry')
    if result not in ('helped', 'harmful'):
        return {'id': key, 'status': 'OUTCOME_RETAINED_UNRANKED',
                'outcome': result, 'evidence_hash': digest(utility_file)}
    state = record_use(library, key, success=result == 'helped',
                       evidence_hash=digest(utility_file))
    return {'id': key, 'status': state['status'], 'outcome': result,
            'evidence_hash': digest(utility_file), 'uses': state['uses']}
