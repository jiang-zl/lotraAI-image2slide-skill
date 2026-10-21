"""PPTX + necessary report; export PDFs are transient validation artifacts."""
from pathlib import Path
from .common import identity,digest,read_json,write_json
from .delivery_size import optimize_pptx,verify_package,package_plan,verify_coverage

def table(metrics,status):
    rows=metrics.get('components',[]) if metrics else []
    if not rows:raise ValueError('Every delivered semantic unit needs current component metric observations')
    keys=[('cer','↓'),('wer','↓'),('ssim','↑'),('psnr','↑'),('foreground_iou','↑'),('edge_iou','↑'),('edge_chamfer','↓'),('colour_error','↓'),
          ('hd_edge_width_px','↓'),('hd_overshoot','↓'),('hd_reversal','↓'),('material_residual','↓'),('joint_gap_px','↓')]
    lines=[f'结果：{status}','','| 部件 | 类别 | 指标分数 |','|---|---|---|']
    for row in rows:
        values=row.get('flat_final') or row.get('flat_comparable') or row.get('values',{})
        scores=[f'{k}{arrow} {values[k]:.4f}' for k,arrow in keys if isinstance(values.get(k),(int,float))]
        if not scores:raise ValueError('Missing numerical observations for '+row['id'])
        lines.append('| '+row['id']+' | '+row.get('profile',{}).get('family',row.get('kind',''))+' | '+'; '.join(scores)+' |')
    return '\n'.join(lines)+'\n'

def expose(pptx,pdf,metrics,output,audits,*,status='ACCEPTED',acceptance=None,caps=None,base_render=None):
    pptx,output,audits=map(Path,(pptx,output,audits))
    if output.exists():raise FileExistsError('User output must be new')
    audits.mkdir(parents=True,exist_ok=True);output.mkdir(parents=True)
    from .transient_export import validate,EquivalenceError,release_task_pdfs
    from .tool_router import capabilities
    # The final optimized PPTX is actually exported, never inferred from an
    # earlier input PDF. The obsolete PDF argument remains for internal callers.
    current_caps=caps or capabilities();attempts=[]
    for profile in ('full','lexical','storage'):
        pp=optimize_pptx(pptx,output/'Final_editable.pptx',profile=profile)
        try:
            pd=validate(pptx,output/'Final_editable.pptx',audits/('actual-equivalence-'+profile),current_caps,base_render=base_render)
        except EquivalenceError as error:
            rejected=audits/('Rejected-'+profile+'.pptx')
            if rejected.exists():raise FileExistsError('Retain failed candidate; inspect exact owned audit path')
            (output/'Final_editable.pptx').rename(rejected)
            attempt={'profile':profile,'status':'REJECTED_ACTUAL_DISPLAY','message':str(error),
                'candidate_sha256':digest(rejected),'changed_resources':[r['part'] for r in pp['resources'] if r.get('input_sha256')!=r.get('output_sha256')]}
            attempts.append(attempt);write_json(audits/'Storage-attempts.json',attempts)
            continue
        attempts.append({'profile':profile,'status':'ACTUALLY_VERIFIED','after_bytes':pp['after_bytes']});break
    else:raise ValueError('No storage candidate passed actual equivalence; immutable source retained for host diagnosis')
    from .presentation_backend import validate_delivery
    native=validate_delivery(output/'Final_editable.pptx',audits,current_caps,destination=output)
    report=f"PPTX：{pp['before_bytes']/1048576:.2f} → {pp['after_bytes']/1048576:.2f} MiB；显示比对一致，PDF 导出验证通过。\n\n"
    (output/'Report.md').write_text(report+table(metrics,status)+'\nNative application validation: '+native['status']+' ('+native['backend']+').\n',encoding='utf8')
    files={p.name:digest(p) for p in output.iterdir() if p.is_file()}
    if set(files)!={'Final_editable.pptx','Report.md'}:raise ValueError('Unexpected user artifact')
    receipt={'kind':'compact-user-delivery-2','status':status,'output':str(output.resolve()),'files':files,
        'native_validation':native,'input_pptx':str(pptx.resolve()),'pptx':pp,'pdf_validation':pd,'acceptance':acceptance,'storage_attempts':attempts}
    file=audits/'Receipt.json';write_json(file,receipt)
    runtime=next((p for p in audits.resolve().parents if p.name=='.lotraAI-build'),None)
    if runtime:write_json(runtime/'delivery-receipts'/(identity(str(output.resolve()))+'.json'),{'receipt':str(file),'sha256':digest(file)})
    verify(output,file)
    release_task_pdfs(audits)
    from .projection_gc import dispose
    dispose(audits)
    return {'status':status,'pptx':str(output/'Final_editable.pptx'),
        'report':str(output/'Report.md'),'size':{'before_bytes':pp['before_bytes'],'after_bytes':pp['after_bytes']},
        'pdf_export_validation':'PASS_DISPOSED','audit_receipt':str(file)}

def verify(directory,receipt=None):
    directory=Path(directory).resolve()
    if receipt is None:
        for parent in directory.parents:
            index=parent/'.lotraAI-build/delivery-receipts'/(identity(str(directory))+'.json')
            if index.exists():
                pointer=read_json(index);receipt=Path(pointer['receipt'])
                if digest(receipt)!=pointer['sha256']:raise ValueError('Local delivery proof changed')
                break
    if receipt is None:raise ValueError('Retain the local runtime delivery receipt for verification')
    r=read_json(receipt);found={p.name:digest(p) for p in directory.iterdir() if p.is_file()}
    if found!=r['files'] or any(p.is_dir() for p in directory.iterdir()):raise ValueError('User delivery changed')
    if r.get('kind')!='compact-user-delivery-2':raise ValueError('Use the historical implementation for older three-file delivery receipts')
    if set(found)!={'Final_editable.pptx','Report.md'}:raise ValueError('PPTX/report-only delivery required')
    if digest(r['input_pptx'])!=r['pptx']['input_sha256']:
        raise ValueError('Original delivery evidence changed; retain its immutable source before replay')
    if r['pptx']['selection']=='COMPACTED':verify_package(r['input_pptx'],directory/'Final_editable.pptx',package_plan(r['input_pptx']))
    elif digest(r['input_pptx'])!=digest(directory/'Final_editable.pptx'):raise ValueError('Retained original package changed')
    verify_coverage(r['input_pptx'],r['pptx'])
    native=r.get('native_validation',{})
    if native.get('status')=='PASS':
        if native.get('input_sha256')!=digest(directory/'Final_editable.pptx') or digest(native['receipt'])!=native['receipt_sha256']:
            raise ValueError('Native final-file validation binding changed')
        proof=read_json(native['receipt'])
        if proof.get('native_editing_claim')!='PASS_OWNED_COPY_EDIT_SAVE_REOPEN':raise ValueError('Missing actual native save/reopen proof')
        from .presentation_backend import _code
        if proof.get('renderer_script_hash')!=identity(_code()):raise ValueError('Final native proof belongs to a different adapter implementation')
    from .transient_export import verify as verify_export
    verify_export(r['pdf_validation'],directory/'Final_editable.pptx')
    return {'integrity':'PASS','product_status':r['status'],'file_count':2,'scope':'lossless delivery and preserved acceptance scope'}
