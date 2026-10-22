"""Compare frozen source lines with the real writer's unsaved native emission."""
import io
import json
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import identity, write_json, digest
from .mathml import NS


def evaluate(scene, base, spec, feature_bindings):
    if not spec.get('lines'):
        return {'schema':'planned-line-preflight-1','passed':True,'applicable':False,'lines':{}}
    from .build import build
    from .boundary_geometry import nodes_from_trees
    from .line_geometry import decode, native_checks, invalid
    from .line_verification import topology_checks
    planned = build(scene,base,None,plan_only=True)
    stream = io.BytesIO();planned['presentation'].save(stream);stream.seek(0)
    with ZipFile(stream) as archive:
        parts = {name:archive.read(name) for name in archive.namelist() if name.endswith(('.xml','.rels'))}
    tree = E.fromstring(parts['ppt/slides/slide1.xml'])
    canvas = E.fromstring(parts['ppt/presentation.xml']).find('p:sldSz',NS)
    nodes = nodes_from_trees(tree,canvas,[scene['canvas']['width'],scene['canvas']['height']])
    bindings = {row['feature']:row for row in feature_bindings}
    decoded={};errors={};geometries={};checks={}
    for row in spec['lines']:
        for part in row['parts']:
            owner=part['owner']
            if part['role']!='shaft' or owner in decoded or owner in errors:continue
            try:decoded[owner]=decode(nodes[owner],parts,row.get('terminal_sites',{}).get(owner))
            except (ValueError,KeyError,TypeError,IndexError) as error:errors[owner]=str(error)
    # A terminal can refer to a later open shaft. Decode the complete native
    # graph before measuring any contact; source row order is not a dependency.
    for row in spec['lines']:
        failed=[errors[p['owner']] for p in row['parts'] if p['owner'] in errors]
        if failed:
            checks[row['id']]={name:invalid('; '.join(failed)) for name in ('route','terminals','markers','stroke')}
            continue
        value=None
        for refinement in range(6):
            epsilon=max(1e-7,row['source']['limits']['route']/32/(4**refinement))
            try:value=native_checks(row,decoded,nodes,bindings,epsilon)
            except (ValueError,KeyError,TypeError,IndexError) as error:
                value={name:invalid(str(error)) for name in ('route','terminals','markers','stroke')};break
            if value['route']['valid'] or value['route'].get('status')=='FAIL':break
        if 'paths' in value:geometries[row['id']]=value
        checks[row['id']]={name:value[name] for name in ('route','terminals','markers','stroke')}
    topology=topology_checks(spec['lines'],geometries,nodes)
    for row in spec['lines']:
        checks[row['id']]['topology']=topology.get(row['id'],invalid('Planned topology unavailable'))
    issues=[{'line':line,'criterion':name,'status':value.get('status'),
             'valid':value.get('valid'),'reason':value.get('reason')}
            for line,items in checks.items() for name,value in items.items()
            if value.get('passed') is not True or value.get('valid') is not True]
    return {'schema':'planned-line-preflight-1','source_hash':scene['source']['sha256'],
        'scene_hash':identity(scene),'line_basis':spec.get('basis'),'passed':not issues,'applicable':True,
        'lines':checks,'issues':issues,'scope':'Unsaved writer route/defaults/topology/terminals only; saved native and actual render checks remain mandatory'}


def require(task, state, scene, contract):
    from .font_resolution import enabled
    if not enabled(state):return None
    spec=contract.get('line_verification',{})
    if not spec.get('lines'):return None
    report=evaluate(scene,task,spec,contract['feature_bindings'])
    file=Path(task)/'source'/('Line-preflight-'+identity(report)+'.json')
    if not file.exists():write_json(file,report)
    ref={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    if (Path(task)/'state.json').is_file():
        from .context_control import register_output
        register_output(task,file)
    if not report['passed']:
        raise ValueError('LINE_PLAN_CONSTRAINT_REQUIRED: '+json.dumps(report['issues'][:12],ensure_ascii=False)
            +'; repair the native plan while preserving frozen original facts; evidence='+json.dumps(ref))
    return ref
