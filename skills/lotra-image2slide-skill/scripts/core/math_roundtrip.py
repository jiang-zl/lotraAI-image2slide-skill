"""Headless editable OMML probe with an actual Office save/reopen roundtrip.

This demonstrates native structural editing, not GUI editor interaction.
Only owned audit copies change. The candidate and all prose are protected.
"""
import copy
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import ROOT,identity,digest,read_json,write_json,safe_path
from .inspect import xml,inventory,parse_math_container
from .mathml import NS,canonical_ast

def evidence(pptx):
    from .native_task import canonical_math
    nodes,_=inventory(xml(pptx));rows={}
    for name,row in nodes.items():
        node=row['node'];zones=node.findall('.//m:oMath',NS)
        if E.QName(node).localname=='grpSp':continue
        rows[name]={'text':''.join(v.text or '' for v in node.findall('.//a:t',NS)),
            'math':canonical_math([parse_math_container(z) for z in zones]),'count':len(zones)}
    return rows

def verify(task,state,candidate,record,needed):
    from .execution_contract import resource,_implementation
    from .office_bridge import _local_path
    if record['pptx_hash']!=candidate['pptx']['sha256'] or record['implementation']!=_implementation():raise ValueError('Stale native math roundtrip')
    original=resource(task,candidate['pptx']);edited=resource(task,record['edited']);saved=resource(task,record['saved'])
    host=read_json(resource(task,record['render']));job=read_json(resource(task,record['job']))
    stage=_local_path(job['staging_directory']);execution=read_json(stage/'execute-status.json')
    host_ok=(host['backend']=='PowerPoint' and host['status']=='PASS' and host['pptx_hash']==digest(edited)
        and job['kind']=='render' and job['status']=='COMPLETED_REQUIRES_RESULT_REVIEW' and execution['status']=='COMPLETED'
        and job['input_pptx_hash']==digest(edited) and job['wrapper_hash']==digest(ROOT/'scripts/run_office_job.ps1')
        and host['renderer_script_hash']==digest(ROOT/'scripts/render_office.ps1')
        and digest(stage/'Input.pptx')==digest(edited) and digest(stage/'result/Native_roundtrip.pptx')==digest(saved))
    before=evidence(original);expected=evidence(edited);actual=evidence(saved);checks=[]
    if set(before)!=set(expected) or set(expected)!=set(actual):raise ValueError('Office roundtrip native ownership changed')
    for name,row in before.items():
        checks.append({'object':name,'prose_preserved':row['text']==expected[name]['text']==actual[name]['text'],
            'math_edit_preserved':expected[name]['math']==actual[name]['math'],
            'edit_observed':row['count']==0 or row['math']!=actual[name]['math'],'spans':actual[name]['count']})
    counts={name:actual[name]['count'] for name in needed}
    passed=host_ok and counts==needed and all(all(c[k] for k in ('prose_preserved','math_edit_preserved','edit_observed')) for c in checks)
    return {'passed':passed,'status':'MEASURED_PASS' if passed else 'MEASURED_FAIL','required':needed,'verified':counts,
        'actual_host_job_verified':host_ok,'checks':checks,'method':'program_AST_edit_with_Office_roundtrip',
        'scope':'Every native mathematical span edited on an owned copy and preserved through actual Office save/reopen; GUI editor interaction is not claimed'}

def probe(task,state,candidate,needed):
    from .execution_contract import resource,_implementation
    from .office_bridge import render,discover
    folder=task/'audits/math-roundtrip'/identity({'pptx':candidate['pptx'],'implementation':_implementation()});folder.mkdir(parents=True,exist_ok=True)
    original=resource(task,candidate['pptx']);edited=folder/'Edited-probe.pptx';tree=xml(original)
    for zone in tree.findall('.//m:oMath',NS):
        for value in ('+','1'):
            run=E.SubElement(zone,'{'+NS['m']+'}r');E.SubElement(run,'{'+NS['m']+'}t').text=value
    if not edited.exists():
        with ZipFile(original) as old,ZipFile(edited,'w',ZIP_DEFLATED) as new:
            for name in old.namelist():new.writestr(name,E.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True) if name=='ppt/slides/slide1.xml' else old.read(name))
    out=folder/'Office-roundtrip'
    if not out.exists():render(edited,out,discover(),width=900,save_native_copy=True)
    def ref(file):return {'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    record={'kind':'native_math_roundtrip_1','pptx_hash':candidate['pptx']['sha256'],'implementation':_implementation(),
        'edited':ref(edited),'saved':ref(out/'Native_roundtrip.pptx'),'render':ref(out/'render.json'),'job':ref(out/'job-receipt.json')}
    result=verify(task,state,candidate,record,needed);record['result']=result
    file=folder/'Receipt.json';write_json(file,record);state['office_math_behavior']=ref(file)
    return result
