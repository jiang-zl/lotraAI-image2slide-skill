"""Observe every saved candidate and compact new construction before fonts.

Complexity flags are located optimization opportunities, never quality gates.
No arbitrary byte budget is permitted to remove editable semantic detail.
"""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import digest,identity,write_json,read_json,safe_path
from .delivery_size import package_plan,optimize_pptx,PARSER

VERSION='candidate-resource-cost-2'
# Diagnostic defaults, not limits on semantic coverage or final acceptance.
POLICY={'compressed_bytes':16*1024*1024,'expanded_bytes':64*1024*1024,
        'native_objects':10000,'path_commands':50000}
NATIVE={'sp','grpSp','cxnSp','pic','graphicFrame'}
COMMANDS={'moveTo','lnTo','arcTo','quadBezTo','cubicBezTo','close'}

def measure(file):
    file=Path(file);before=digest(file);plan=package_plan(file)
    owners=[];resources=[];media=fonts=expanded=commands=objects=svg_commands=0
    with ZipFile(file) as z:
        links={}
        for part in z.namelist():
            if not part.endswith('.rels'):continue
            from .delivery_size import owner_of,target
            owner=owner_of(part)
            for row in E.fromstring(z.read(part),PARSER):
                if row.get('TargetMode')!='External':
                    links.setdefault(target(owner,row.get('Target')),[]).append({'owner_part':owner,'rid':row.get('Id'),'role':row.get('Type')})
        for info in z.infolist():
            import hashlib,re
            data=z.read(info);suffix=Path(info.filename).suffix.lower();own_commands=0
            expanded+=info.file_size
            if info.filename.startswith('ppt/media/'):media+=info.compress_size
            if info.filename.startswith('ppt/fonts/'):fonts+=info.compress_size
            if suffix=='.svg':
                from .representation_codec import D_ATTR
                own_commands=sum(len(re.findall(rb'[MmLlHhVvCcSsQqTtAaZz]',d)) for d in D_ATTR.findall(data));svg_commands+=own_commands
            resources.append({'part':info.filename,'sha256':hashlib.sha256(data).hexdigest(),'raw_bytes':info.file_size,
                'stored_bytes':info.compress_size,'compression':info.compress_type,'referrers':links.get(info.filename,[]),
                'category':'font' if info.filename.startswith('ppt/fonts/') else 'media' if info.filename.startswith('ppt/media/') else 'native_or_package',
                'svg_path_commands':own_commands,'unreachable_media':info.filename in plan['removed']})
            if not (info.filename.startswith('ppt/slides/slide') and info.filename.endswith('.xml')):continue
            root=E.fromstring(data,PARSER);rel_owner={r['rid']:r for rows in links.values() for r in rows if r['owner_part']==info.filename}
            for element in root.iter():
                if E.QName(element).localname not in NATIVE:continue
                objects+=1;local_commands=0
                # Descendant group costs must not count each child's path twice.
                for child in element:
                    if E.QName(child).localname in NATIVE:continue
                    local_commands+=sum(E.QName(n).localname in COMMANDS for n in child.iter())
                commands+=local_commands
                props=next((n for n in element.iter() if E.QName(n).localname=='cNvPr'),None)
                direct=[]
                def visit(n):
                    for child in n:
                        if E.QName(child).localname not in NATIVE:direct.append(child);visit(child)
                visit(element)
                from .delivery_size import RID,target
                refs={value for n in direct for key,value in n.attrib.items() if key.startswith('{'+RID+'}')}
                owned_media=sorted({name for name,rows in links.items() if any(r['owner_part']==info.filename and r['rid'] in refs for r in rows)})
                owners.append({'id':props.get('name') if props is not None else None,
                    'native_id':props.get('id') if props is not None else None,'part':info.filename,
                    'xml_bytes':len(E.tostring(element)),'own_path_commands':local_commands,'resource_parts':owned_media})
                for index,cell in enumerate(n for n in direct if E.QName(n).localname=='tc'):
                    owners.append({'id':(props.get('name') if props is not None else 'table')+'/cell/'+str(index),
                        'native_id':props.get('id') if props is not None else None,'part':info.filename,'table_cell':index,
                        'xml_bytes':len(E.tostring(cell)),'own_path_commands':0,'resource_parts':[]})
    if digest(file)!=before:raise ValueError('Candidate changed during resource observation')
    values={'compressed_bytes':file.stat().st_size,'expanded_bytes':expanded,'media_compressed_bytes':media,
            'font_compressed_bytes':fonts,'native_objects':objects,'path_commands':commands,
            'svg_path_commands':svg_commands,'all_path_commands':commands+svg_commands,
            'zip_overhead_bytes':file.stat().st_size-sum(r['stored_bytes'] for r in resources)}
    work=[]
    if plan['removed']:work.append({'kind':'lossless_resource_cleanup','count':len(plan['removed']),
        'executor':'final verified package compactor; never change an already rendered candidate in place'})
    if plan['aliases']:work.append({'kind':'exact_media_reuse','count':len(plan['aliases']),
        'executor':'verified byte-identical media aliases'})
    if svg_commands:work.append({'kind':'equivalent_vector_encoding','executor':'mandatory immutable resource codec; retain semantic parts and exact closed paths'})
    if any(values[k]>v for k,v in POLICY.items()) or svg_commands>POLICY['path_commands']:work.append({'kind':'complexity_review',
        'exceeded':[k for k,v in POLICY.items() if values[k]>v],
        'executor':'inspect located owner costs; use source-supported reusable mothers or bounded curve fitting only',
        'guard':'Any geometry change requires a frozen error contract and complete current quality recheck'})
    return {'schema':VERSION,'pptx_sha256':before,'status':'MEASURED','values':values,
        'opportunities':work,'owners':owners,'resources':resources,'resource_set_hash':identity(sorted(r['part'] for r in resources)),
        'coverage':'COMPLETE','policy':POLICY,
        'scope':'Storage/complexity diagnosis; semantic quality and every object check remain mandatory'}

def attach(task,state):
    task=Path(task).resolve();reports=state.setdefault('file_cost_history',{})
    current=None
    for candidate in (state.get('selected'),state.get('active_candidate')):
        if not candidate:continue
        ref=candidate.get('pptx')
        if not ref:continue
        file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Candidate resource observation needs the exact current PPTX')
        from . import representation_codec,delivery_size
        key=identity({'pptx':ref['sha256'],'code':digest(__file__),'codec':digest(representation_codec.__file__),
            'storage':digest(delivery_size.__file__),'policy':POLICY})
        cached=reports.get(key)
        if cached:
            proof=safe_path(task,cached['path'])
            if digest(proof)!=cached['sha256']:raise ValueError('Stored candidate cost evidence changed')
            row=read_json(proof)
            if row['pptx_sha256']!=ref['sha256']:raise ValueError('Candidate cost identity changed')
        else:
            row=measure(file);proof=safe_path(task,'audits/file-cost/'+key+'.json');write_json(proof,row)
            cached={'path':proof.relative_to(task).as_posix(),'sha256':digest(proof)};reports[key]=cached
        current={**cached,'pptx_sha256':ref['sha256'],'status':row['status'],'values':row['values'],
                 'opportunity_kinds':[r['kind'] for r in row['opportunities']]}
    if current:state['file_cost']=current
    else:state.pop('file_cost',None)
    return current

def compact_construction(pending):
    """Only an owned, not-yet-font-finalized new build; keep original evidence."""
    pending=Path(pending);raw=pending.with_name(pending.stem+'.construction-raw.pptx')
    if raw.exists():raise FileExistsError(raw)
    pending.rename(raw)
    result=optimize_pptx(raw,pending)
    result['phase']='before_font_embedding_and_actual_render'
    result['original_runtime_file']=raw.name
    return result
