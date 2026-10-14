"""Frozen multi-version baselines and noncompensating release comparisons."""
from pathlib import Path
import shutil
from .common import digest,identity,read_json,write_json,writer
from .typed_metrics import dominance

VERSION='baseline-protocol-1.1.0'


def freeze(cases,output):
    if not cases or len({c['id'] for c in cases})!=len(cases):raise ValueError('Empty/duplicate case set')
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    records=[]
    with writer(output):
        for case in cases:
            files=[]
            for role,paths in [('source',[case['source']]),('baseline',case.get('baselines',[]))]:
                for value in paths:
                    p=Path(value);h=digest(p);target=output/'files'/h/p.name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if not target.exists():shutil.copyfile(p,target)
                    if digest(target)!=h:raise ValueError('Frozen copy differs')
                    files.append({'role':role,'name':p.name,'sha256':h,'path':target.relative_to(output).as_posix()})
            records.append({'id':case['id'],'files':files,'baseline_status':'FROZEN' if case.get('baselines') else 'NO_HISTORICAL_BASELINE'})
        manifest={'version':VERSION,'cases':records};manifest['manifest_hash']=identity(manifest)
        write_json(output/'manifest.json',manifest)
    return manifest


def environment_identity(render,preview=None):
    pixels=render.get('preview_pixels')
    if preview is not None:
        from PIL import Image
        if digest(preview)!=render.get('preview_hash'):raise ValueError('Render preview changed before environment comparison')
        with Image.open(preview) as image:actual=list(image.size)
        if pixels is not None and pixels!=actual:raise ValueError('Declared render dimensions differ from actual image')
        pixels=actual
    env=render.get('current_environment',{})
    result={'backend':render.get('backend') or render.get('renderer') or render.get('method'),
            'version':render.get('backend_version') or env.get('backend_version'),
            'build':render.get('office_build') or env.get('office_build'),
            'platform':render.get('platform') or env.get('platform'),
            'font_hash':render.get('font_inventory_hash') or env.get('font_inventory_hash'),
            'render_pixels':pixels}
    required=('backend','version','platform','font_hash','render_pixels')
    return {'identity':identity(result),'details':result,'complete':all(result.get(k) for k in required)}


def compare_case(baselines,candidate,directions,required_gates):
    """Every historical candidate participates; mean wins never hide a failure."""
    if not directions or not required_gates:raise ValueError('Comparison needs fixed metrics and hard gates')
    missing=[k for k in required_gates if candidate.get('gates',{}).get(k)!='PASS']
    comparisons=[]
    for old in baselines:
        keys=('source_hash','plan_hash','metric_version','environment_hash','implementation_hash')
        comparable=all(old.get(k) is not None and old.get(k)==candidate.get(k) for k in keys)
        result=dominance(old.get('vector',{}),candidate.get('vector',{}),directions) if comparable else {'result':'unmeasured','reason':'Frozen evaluation identity mismatch'}
        regressions=[k for k,v in old.get('gates',{}).items() if v=='PASS' and candidate.get('gates',{}).get(k)!='PASS']
        gate_improvements=[k for k,v in candidate.get('gates',{}).items() if v=='PASS' and old.get('gates',{}).get(k)=='FAIL']
        comparisons.append({'baseline_hash':old['pptx_hash'],'measurements':result,'gate_regressions':regressions,'gate_improvements':gate_improvements})
    if missing:status='NOT_ACCEPTED'
    elif not baselines:status='PASSED_WITHOUT_HISTORICAL_BASELINE'
    elif any(c['gate_regressions'] or c['measurements']['result'] in ('harmful','tradeoff','unmeasured') for c in comparisons):status='NOT_PROVEN_SUPERIOR'
    elif all(c['measurements']['result']=='helped' or c['gate_improvements'] for c in comparisons):status='VERIFIED_SUPERIOR'
    else:status='NONREGRESSING_WITH_TIES'
    return {'version':VERSION,'candidate_hash':candidate['pptx_hash'],'status':status,'unmet_gates':missing,'comparisons':comparisons,
            'scope':'All supplied historical baselines; applies only to frozen metrics and verified gate evidence'}


def release_gate(manifest,case_reports):
    expected={c['id'] for c in manifest['cases']};actual={c['case'] for c in case_reports}
    if not expected or actual!=expected or len(actual)!=len(case_reports):
        return {'status':'NOT_ACCEPTED','reason':'Incomplete, extra or duplicate cases','missing':sorted(expected-actual)}
    accepted={'VERIFIED_SUPERIOR','PASSED_WITHOUT_HISTORICAL_BASELINE'}
    failures=[c['case'] for c in case_reports if c['status'] not in accepted]
    return {'status':'ACCEPTED_BENCHMARK' if not failures else 'NOT_ACCEPTED','unmet_cases':failures,
            'scope':'Benchmark only; package/installation/platform evidence remain required'}
