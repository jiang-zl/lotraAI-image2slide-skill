"""Finite source-confirmed plain/rich-text repair on one saved native owner.

No coordinates, font substitution, arbitrary XML or executable payloads. The
same exact constructor independently verifies the saved result against the
immutable earlier owner and the source-only reading.
"""
import copy,math
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import digest,identity,read_json,write_json,safe_path,writer
from .mathml import NS

def runs(value):
    if not isinstance(value,list) or not 1<=len(value)<=32:raise ValueError('One bounded source paragraph is required')
    for row in value:
        if set(row)-{'text','baseline','font_scale','italic'} or not isinstance(row.get('text'),str) or '\n' in row['text']:
            raise ValueError('Only literal text and declared sub/superscript run properties are supported')
        if type(row.get('baseline',0)) is not int or not -35000<=row.get('baseline',0)<=35000:raise ValueError('Bounded script baseline required')
        scale=row.get('font_scale',1.)
        if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or not .6<=scale<=1.:
            raise ValueError('Bounded source script size required')
        if 'italic' in row and type(row['italic']) is not bool:raise ValueError('Literal italic flag required')
    return value

def expected_node(baseline,reading):
    declared=runs(reading['formatted_runs'])
    if ''.join(r['text'] for r in declared)!=reading['literal']:raise ValueError('Source runs must reproduce the exact independent literal')
    result=copy.deepcopy(baseline);body=result.find('p:txBody',NS)
    if body is None or len(body.findall('a:p',NS))!=1 or body.findall('.//m:oMath',NS):
        raise ValueError('This finite route handles one plain native paragraph, without math or layout changes')
    p=body.find('a:p',NS);original=p.findall('a:r',NS)
    if len(original)!=1 or len(original[0].findall('a:t',NS))!=1:raise ValueError('Unambiguous one-run baseline required')
    template=original[0];props=template.find('a:rPr',NS)
    if props is None or not props.get('sz'):raise ValueError('Explicit original run size required')
    anchor=list(p).index(template);p.remove(template)
    for offset,row in enumerate(declared):
        node=copy.deepcopy(template);rpr=node.find('a:rPr',NS);node.find('a:t',NS).text=row['text']
        rpr.set('sz',str(round(int(props.get('sz'))*row.get('font_scale',1.))))
        if row.get('baseline',0):rpr.set('baseline',str(row['baseline']))
        else:rpr.attrib.pop('baseline',None)
        if 'italic' in row:rpr.set('i','1' if row['italic'] else '0')
        p.insert(anchor+offset,node)
    return result

def guard(task,state,candidate,item,approved):
    from .inspect import xml,inventory
    correction=item['source_content_correction'];uid=correction['unit'];reading=state.get('source_readings',{}).get('records',{}).get(uid)
    if not reading or identity(reading)!=correction['reading_hash']:raise ValueError('Source text correction reading is stale')
    unit=state['quality']['units'][uid]
    if unit['profile']!='text' or len(unit['objects'])!=1 or item['objects']!=unit['objects']:
        raise ValueError('Source text correction must bind its one actual native owner')
    old,_=inventory(xml(safe_path(task,approved['pptx']['path'])));now,_=inventory(xml(safe_path(task,candidate['pptx']['path'])))
    name=unit['objects'][0];expected=expected_node(old[name]['node'],reading)
    # Compare the native payload, independent of unused namespace declarations
    # inherited from the containing slide after ZIP serialization/reopening.
    passed=E.tostring(expected,method='c14n',exclusive=True)==E.tostring(now[name]['node'],method='c14n',exclusive=True)
    return {'passed':passed,'method':'exact_source_confirmed_run_constructor','unit':uid,
            'reading_hash':identity(reading),'protected':'Every property outside the declared text and script runs remains identical'}

def execute(task,request):
    from . import agent_runtime as a
    from .inspect import xml,inventory
    task,state=a._state(task);before_state=identity(state);baseline=state.get('active_candidate') or state.get('selected')
    if request.get('expected_baseline_sha256')!=baseline['pptx']['sha256']:raise ValueError('Stale text repair baseline')
    uid=request['unit'];reading=state.get('source_readings',{}).get('records',{}).get(uid)
    if not reading or request.get('reading_hash')!=identity(reading):raise ValueError('Independent source reading required')
    unit=state['quality']['units'][uid];name=unit['objects'][0]
    policy=next((r for r in state['quality_intent']['items'] if r.get('appearance_target')=='source_content' and r.get('source_content_correction',{}).get('unit')==uid),None)
    if not policy:raise ValueError('Freeze the source content correction before execution')
    signatures=state.setdefault('source_text_attempts',[]);branch=identity({'source':state['source'],'unit':uid,'reading':reading,'operator':'exact_native_source_runs'})
    if any(r['branch']==branch and r['baseline']==baseline['pptx']['sha256'] for r in signatures):raise ValueError('Do not repeat an unchanged source text branch')
    if sum(r['branch']==branch for r in signatures)>=2:raise ValueError('Source text repair branch exhausted; revise source evidence or use another existing typed route')
    file=safe_path(task,baseline['pptx']['path'])
    if digest(file)!=baseline['pptx']['sha256']:raise ValueError('Native text repair input bytes changed')
    tree=xml(file);nodes,duplicates=inventory(tree)
    if name in duplicates:raise ValueError('Ambiguous native owner')
    old=nodes[name]['node'];replacement=expected_node(old,reading);old.getparent().replace(old,replacement)
    directory=task/'versions'/('text-'+identity({'branch':branch,'baseline':baseline['pptx']})[:16])
    output=directory/'drawing.pptx'
    recovered=None
    if directory.exists():
        # A process may have saved the protected native ZIP before failing to
        # commit its snapshot/state. Recover only the exact intended payload;
        # never delete, overwrite or rename an unrelated existing artifact.
        if not output.is_file():raise ValueError('Uncommitted repair directory has no recoverable native artifact')
        with ZipFile(file) as old_zip,ZipFile(output) as saved_zip:
            if sorted(old_zip.namelist())!=sorted(saved_zip.namelist()):raise ValueError('Uncommitted repair ZIP inventory differs')
            for member in old_zip.namelist():
                if member=='ppt/slides/slide1.xml':
                    if E.tostring(E.fromstring(saved_zip.read(member)),method='c14n')!=E.tostring(tree,method='c14n'):
                        raise ValueError('Uncommitted native text payload differs from the exact source constructor')
                elif saved_zip.read(member)!=old_zip.read(member):raise ValueError('Uncommitted repair changed a protected ZIP resource')
        recovered={'path':output.relative_to(task).as_posix(),'sha256':digest(output),'method':'exact ZIP payload and source-constructor recovery'}
    else:
        directory.mkdir()
        with ZipFile(file) as z,ZipFile(output,'x',ZIP_DEFLATED,compresslevel=9) as out:
            for info in z.infolist():out.writestr(info,E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True) if info.filename=='ppt/slides/slide1.xml' else z.read(info.filename))
    # Full inventory protection, with parent nodes compared without descendants.
    from .appearance_metrics import native_signatures
    previous=native_signatures(str(file),baseline['pptx']['sha256']);current=native_signatures(str(output),digest(output))
    unauthorized=[n for n in previous if n!=name and previous[n]!=current.get(n)]
    if unauthorized:raise ValueError('Unpermitted native source text change: '+str(unauthorized))
    scene=read_json(safe_path(task,baseline['scene']['path']))
    from .native_snapshot import snapshot
    scene=snapshot(task,state,output,scene)
    scene_path=directory/('scene-'+identity(scene)[:16]+'.json')
    if scene_path.exists() and read_json(scene_path)!=scene:raise ValueError('Immutable recovered native snapshot differs')
    if not scene_path.exists():write_json(scene_path,scene)
    candidate=copy.deepcopy(baseline);candidate.update(pptx={'path':output.relative_to(task).as_posix(),'sha256':digest(output)},scene={'path':scene_path.relative_to(task).as_posix(),'sha256':digest(scene_path)})
    candidate['prior_render']=candidate.pop('render');candidate.pop('preview',None)
    candidate['reason']={'kind':'independent_source_text_repair','unit':uid,'branch':branch};candidate['allowed']={name:['text']}
    receipt={'branch':branch,'baseline':baseline['pptx']['sha256'],'candidate':digest(output),'unit':uid,'non_target_native_changes':unauthorized,'status':'SAVED_REQUIRES_ACTUAL_RENDER'}
    if recovered:receipt['recovered_uncommitted_artifact']=recovered
    with writer(task):
        if identity(a._state(task)[1])!=before_state:raise ValueError('Task changed during native text construction; preserved uncommitted artifact for exact recovery')
        signatures.append(receipt);state['active_candidate']=candidate;state['scene']=candidate['scene'];state['stage']='host_render';state['packet']=None
        state.pop('quality_result',None);state.pop('acceptance',None)
        a._event(task,'source_confirmed_native_text_saved',receipt);a._save(task,state)
    return receipt
