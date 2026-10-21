"""Keep evidence on disk when an action exceeds its model context budget."""
from .common import canonical,identity,write_json,digest,read_json,safe_path

CONTROL=('packet_id','kind','target','revision','objective','baseline','source','original_view','return','views','file_cost','component_implementation','action','submission_command','submission_template','incremental','completion_policy')

def _store(file,value):
    file.parent.mkdir(exist_ok=True)
    if file.exists():
        if identity(read_json(file))!=identity(value):raise ValueError('Frozen packet content changed')
    else:write_json(file,value)

def compact(task,packet,budget):
    if type(budget) is not int or budget<=0:raise ValueError('Positive character context budget required')
    if len(canonical(packet).decode('utf-8'))<=budget:return packet
    full=task/'packets'/('full-'+identity(packet)[:20]+'.json')
    _store(full,packet)
    execution={'path':full.relative_to(task).as_posix(),'sha256':digest(full)}
    secondary=('priorities','diagnostics','review_targets','source_requirements','trace',
               'assets','available_recipes','available_presets','source_trace','original_word_anchors',
               'native_targets','allowed_changes')
    detail={k:packet[k] for k in secondary if k in packet}
    if not detail:detail={k:v for k,v in packet.items() if k not in CONTROL}
    file=task/'packets'/('detail-'+identity(detail)[:20]+'.json')
    _store(file,detail)
    result={k:v for k,v in packet.items() if k not in detail}
    result['execution_reference']=execution
    result['detail_reference']={'path':file.relative_to(task).as_posix(),'sha256':digest(file),
        'keys':list(detail),'read':'Read only the needed section or owner from this frozen JSON; geometry and evidence are not discarded.'}
    if 'review_targets' in detail:
        result['pending_units']=[r['id'] for r in detail['review_targets']]
    if 'source_requirements' in detail:
        result['source_owners']=[{'id':r['id'],'semantic_class':r['semantic_class']} for r in detail['source_requirements']]
    if 'trace' in detail:
        result['root_cause_work']=detail['trace'].get('root_cause_work')
    if 'allowed_changes' in detail:
        result['write_owner_ids']=list(detail['allowed_changes'])
        result['write_scope_reference']=result['detail_reference']
    if len(canonical(result).decode('utf-8'))>budget:
        # Large component/source specifications are first-use data too. Keep
        # the entire immutable packet available by a bounded selector, rather
        # than failing before the host can discover its relevant section.
        result={k:packet[k] for k in CONTROL if k in packet}
        result['execution_reference']=execution
        result['detail_reference']={**execution,
            'keys':list(packet),'read':'Use scripts/packet_detail.py to select a field, owner or paged list without loading the full packet.'}
    if len(canonical(result).decode('utf-8'))>budget:
        # Oversized optional control prose/views remain in the full contract.
        # Preserve every retained identity exactly; restore verifies them.
        for name in ('objective','return','views'):
            result.pop(name,None)
            if len(canonical(result).decode('utf-8'))<=budget:break
    if len(canonical(result).decode('utf-8'))>budget:
        # The full referenced contract remains unchanged. Optional field lists
        # and reader prose must not crowd out the executable submit controls at
        # the supported minimum context budget.
        for name in ('keys','read'):
            result.get('detail_reference',{}).pop(name,None)
            if len(canonical(result).decode('utf-8'))<=budget:break
    if len(canonical(result).decode('utf-8'))>budget:
        raise ValueError('Identity envelope exceeds the context budget; no contract fields may be silently truncated')
    return result

def restore(task,packet):
    """Programs execute the complete hash-bound packet, never its UI summary."""
    ref=packet.get('execution_reference')
    legacy=False
    if not ref:
        ref=packet.get('detail_reference')
        if not ref:return packet
        legacy=True
    file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Executable work packet reference changed')
    stored=read_json(file)
    if not isinstance(stored,dict):raise ValueError('Executable work packet must be an object')
    if legacy and 'packet_id' not in stored:
        return {**stored,**{k:v for k,v in packet.items() if k!='detail_reference'}}
    for key in CONTROL:
        if key not in packet:continue
        expected=stored.get(key)
        if legacy and key=='views':expected=(expected or [])[:len(packet[key])]
        if canonical(packet[key])!=canonical(expected):
            raise ValueError('Compacted work packet identity changed: '+key)
    return stored
