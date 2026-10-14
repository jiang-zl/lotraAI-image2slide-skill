"""Actual render validation, compact observations, and owned PDF disposal.

A PDF remains live during recursion/HD/font checks. Terminal delivery releases
only files registered by this implementation. Completed task resumption needs
fresh rendering and current checks, never a missing-PDF synthetic PASS.
"""
import hashlib,re,shutil,tempfile
from pathlib import Path
from .common import digest,identity,read_json,write_json

VERSION='temporary-pdf-1'
SCALES=(1,2,4)

class EquivalenceError(ValueError):
    """Located storage representation failure eligible for deterministic rollback."""

def fingerprint(pdf):
    import pymupdf
    from .resource_facts import derived_value
    return derived_value(pdf,None,{'pdf_fingerprint':digest(__file__),'PyMuPDF':pymupdf.VersionBind,
                                   'scales':SCALES,'alpha':True,'base_long_side_px':720},
                         lambda: _fingerprint(pdf))

def _fingerprint(pdf):
    import pymupdf as fitz
    rows=[]
    from .resource_facts import pdf_document
    with pdf_document(pdf) as doc:
        if not len(doc) or doc.is_encrypted:raise ValueError('Readable nonempty exported PDF required')
        for page in doc:
            row={'rect':list(page.rect),'mediabox':list(page.mediabox),'cropbox':list(page.cropbox),
                'rotation':page.rotation,'text_sha256':identity(page.get_text()),
                'links':identity([{k:str(v) for k,v in link.items() if k!='xref'} for link in page.get_links()]),'pixels':[]}
            for scale in SCALES:
                # All pages at fixed coordinates, bounded memory even on CPU-only
                # machines. Exact vector semantics separately protect finer detail.
                factor=720*scale/max(page.rect.width,page.rect.height)
                pix=page.get_pixmap(matrix=fitz.Matrix(factor,factor),alpha=True)
                row['pixels'].append({'scale':scale,'width':pix.width,'height':pix.height,
                    'sha256':hashlib.sha256(pix.samples).hexdigest()})
            rows.append(row)
        return {'pages':rows,'outline':identity(doc.get_toc()),'scales':list(SCALES),'base_long_side_px':720}

def register(folder,pptx,receipt):
    folder,pptx=Path(folder).resolve(),Path(pptx).resolve();pdf=folder/'Final.pdf'
    if receipt.get('pdf',{}).get('status')!='EXPORTED' or not pdf.is_file():return
    if receipt.get('pptx_hash')!=digest(pptx) or receipt.get('pdf_hash')!=digest(pdf):raise ValueError('Unbound PDF ownership')
    write_json(folder/'Pdf-lifecycle.json',{'schema':VERSION,'status':'LIVE_FOR_CHECKS','pptx':str(pptx),
        'pptx_sha256':digest(pptx),'pdf_sha256':digest(pdf),'root':str(folder),'pdf':'Final.pdf',
        'host':{k:receipt.get(k) for k in ('backend','backend_version','office_build','font_inventory_hash','renderer_script_hash')}})

def _safe(file,root):
    root=Path(root);file=Path(file)
    if root.is_symlink() or file.is_symlink() or root.resolve()!=root.absolute():raise ValueError('PDF cleanup refuses a redirected root')
    root=root.resolve();file=file.resolve()
    if not file.is_relative_to(root) or file==root:raise ValueError('PDF cleanup escaped owned scope')
    for parent in (file,*file.parents):
        if parent.is_symlink():raise ValueError('PDF cleanup refuses a linked path')
        if parent==root:break
    return file

def release(folder,*,observed=None):
    """Call only after all dependent checks and official delivery verification."""
    folder=Path(folder).resolve();mark=folder/'Pdf-lifecycle.json'
    if not mark.is_file():return {'status':'PROTECTED_UNREGISTERED','root':str(folder)}
    owner=read_json(mark)
    if owner.get('schema')!=VERSION or owner.get('root')!=str(folder):raise ValueError('Invalid temporary PDF owner')
    if owner.get('status')=='DISPOSED':
        if (folder/owner['pdf']).exists():raise ValueError('Disposed PDF unexpectedly returned')
        return owner
    pdf=_safe(folder/owner['pdf'],folder)
    if digest(owner['pptx'])!=owner['pptx_sha256'] or digest(pdf)!=owner['pdf_sha256']:raise ValueError('Temporary PDF changed before cleanup')
    if observed is not None:
        if observed.get('pdf_sha256')!=owner['pdf_sha256'] or not observed.get('fingerprint',{}).get('pages'):
            raise ValueError('PDF disposal observation is stale')
        observation=observed['fingerprint']
    else:observation=fingerprint(pdf)
    owner['observation']=observation;owner['bytes_released']=pdf.stat().st_size
    owner.update(status='DISPOSED',resume='FRESH_RENDER_AND_CURRENT_CHECKS_REQUIRED')
    pdf.unlink();write_json(mark,owner)
    return owner

def release_task_pdfs(task):
    task=Path(task).resolve();results=[]
    for marker in sorted(task.rglob('Pdf-lifecycle.json')):
        if marker.is_symlink() or not marker.resolve().is_relative_to(task):raise ValueError('Task PDF owner escaped task')
        # Only v1.26-created leases; archived/user PDFs without one stay protected.
        if read_json(marker).get('schema')==VERSION:results.append(release(marker.parent))
    return {'status':'DEPENDENTS_COMPLETE','registered_pdfs':results,
        'unregistered_history':'PROTECTED','resume':'program rerenders disposed candidates before new measurements'}

def live_pdf(folder,pptx,caps=None):
    """A new lease from a real rerender; old observations cannot invent pixels."""
    folder=Path(folder).resolve();pptx=Path(pptx).resolve();marker=folder/'Pdf-lifecycle.json'
    owner=read_json(marker)
    if (owner.get('schema')!=VERSION or owner.get('status')!='DISPOSED'
            or owner.get('pptx_sha256')!=digest(pptx) or not owner.get('observation')):
        raise ValueError('Missing PDF needs a verified disposed lease or full fresh rendering')
    from .tool_router import capabilities,render_saved
    caps=caps or capabilities();key=identity({'pptx':digest(pptx),'host':caps,'implementation':digest(__file__)})[:20]
    pointer=folder/('Reexport-'+key+'.json')
    if pointer.is_file():
        row=read_json(pointer);pdf=Path(row['pdf'])
        if pdf.is_file():
            if digest(pdf)!=row['pdf_sha256']:raise ValueError('Reexported PDF changed')
            return pdf,row
    output=folder/('reexport-'+key);i=0
    while output.exists():i+=1;output=folder/('reexport-'+key+'-'+str(i))
    render=render_saved(pptx,output,caps,2000);pdf=_pdf(output,render,pptx)
    if any(render.get(k)!=v for k,v in owner.get('host',{}).items()):
        raise ValueError('Disposed comparator host changed; refresh full current quality checks')
    if fingerprint(pdf)!=owner['observation']:
        raise ValueError('Disposed comparator differs after actual rerender; refresh full current quality checks')
    proof={'status':'ACTUALLY_REEXPORTED_IDENTICAL','pptx_sha256':digest(pptx),'pdf':str(pdf),'pdf_sha256':digest(pdf),
        'render':str(output/'render.json'),'render_sha256':digest(output/'render.json'),'original_disposition_sha256':digest(marker)}
    write_json(pointer,proof);return pdf,proof

def clean_office_stage(folder,pptx):
    """Exact successful helper-owned GUID staging; never a shared Office process."""
    folder=Path(folder);receipt=folder/'job-receipt.json'
    if not receipt.is_file():return {'status':'NOT_APPLICABLE'}
    row=read_json(receipt)
    if row.get('status')!='COMPLETED_REQUIRES_RESULT_REVIEW':return {'status':'PRESERVED_RECOVERY_STAGE'}
    from .office_bridge import _local_path
    root=_local_path(row['staging_directory']);parent=root.parent
    if (parent.name!='sci-rebuild-office' or not re.fullmatch('[0-9a-fA-F]{32}',root.name)
            or root.is_symlink() or root.resolve()!=root.absolute()):raise ValueError('Office cleanup refuses unexpected staging')
    # Windows TEMP can be on another volume. The wrapper receipt and immutable
    # Input.pptx are the ownership boundary; all descendants are checked too.
    if row.get('input_pptx_hash')!=digest(pptx) or digest(root/'Input.pptx')!=digest(pptx):raise ValueError('Office staging owner changed')
    if read_json(root/'execute-status.json').get('status')!='COMPLETED':raise ValueError('Office helper remains incomplete')
    for p in root.rglob('*'):
        if p.is_symlink():raise ValueError('Linked Office staging descendant')
    for p in (root/'result').rglob('*'):
        if p.is_file() and digest(p)!=digest(folder/p.relative_to(root/'result')):raise ValueError('Uncopied Office staging result')
    size=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    shutil.rmtree(root)
    return {'status':'DISPOSED_OWNED_SUCCESS_STAGE','bytes_released':size,'input_sha256':row['input_pptx_hash']}

def _pdf(folder,receipt,pptx):
    pdf=Path(folder)/'Final.pdf'
    if (receipt.get('status')!='PASS' or receipt.get('pptx_hash')!=digest(pptx)
            or receipt.get('pdf',{}).get('status')!='EXPORTED' or not pdf.is_file()
            or digest(pdf)!=receipt.get('pdf_hash')):raise ValueError('Actual saved PPTX to PDF export did not succeed')
    return pdf

def validate(before,after,root,caps,*,base_render=None):
    """Same host, same canvas, every page. Failure cannot authorize adoption."""
    from .tool_router import render_saved
    from .delivery_size import verify_package,package_plan
    from PIL import Image
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    before,after=Path(before).resolve(),Path(after).resolve();start=(digest(before),digest(after))
    verify_package(before,after,package_plan(before))
    out=root/'optimized-render'
    final=render_saved(after,out,caps,2000);pdf_final=_pdf(out,final,after)
    original=None;own_base=False
    if base_render:
        path=Path(base_render);row=read_json(path)
        keys=('backend','backend_version','office_build','font_inventory_hash','renderer_script_hash')
        if all(row.get(k)==final.get(k) for k in keys) and row.get('pptx_hash')==start[0]:
            _pdf(path.parent,row,before);original=(path.parent,row)
    if original is None:
        folder=root/'original-render';row=render_saved(before,folder,caps,2000);original=(folder,row);own_base=True
    folder,row=original;pdf_original=_pdf(folder,row,before)
    keys=('backend','backend_version','office_build','font_inventory_hash','renderer_script_hash')
    if any(row.get(k)!=final.get(k) for k in keys):raise ValueError('Comparison host or font environment changed')
    a,b=fingerprint(pdf_original),fingerprint(pdf_final)
    if a!=b:
        write_json(root/'Difference.json',{'status':'REJECTED','basis':'same-host fixed-page comparison',
            'input_pptx_sha256':start[0],'output_pptx_sha256':start[1],'original':a,'candidate':b})
        raise EquivalenceError('Optimized PPTX changed actual PDF appearance, text, links or geometry')
    def previews(folder,row):
        pages=row.get('pages') or [{'path':'Final_preview.png'}]
        result=[]
        for page in pages:
            path=Path(folder)/page.get('path','Final_preview.png')
            if not path.is_file():raise ValueError('Actual preview page absent')
            with Image.open(path) as im:result.append((im.size,hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest()))
        return result
    if previews(folder,row)!=previews(out,final):raise EquivalenceError('Actual host preview pixels changed')
    if (digest(before),digest(after))!=start:raise ValueError('PPTX changed during actual equivalence verification')
    proof={'schema':VERSION,'status':'PASS','input_pptx_sha256':start[0],'output_pptx_sha256':start[1],
        'backend':final.get('backend'),'backend_version':final.get('backend_version'),'office_build':final.get('office_build'),
        'font_inventory_hash':final.get('font_inventory_hash'),'renderer_script_hash':final.get('renderer_script_hash'),
        'pdf_export':'SUCCEEDED','all_page_pixels':'EXACT','preview_pixels':'EXACT','observation':a,
        'native_xml_and_fonts':'BYTE_IDENTICAL','validator_code_sha256':digest(__file__),
        'scope':'size optimization equivalence, preserves prior quality acceptance scope'}
    write_json(root/'Validation.json',proof)
    # Cleanup only after all observations above succeeded; exceptions retain
    # bounded current evidence for repair and never overwrite the original.
    disposal=[release(out,observed={'pdf_sha256':digest(pdf_final),'fingerprint':b})]
    if own_base:disposal.append(release(folder,observed={'pdf_sha256':digest(pdf_original),'fingerprint':a}))
    proof['temporary_pdf_disposal']=disposal
    write_json(root/'Validation.json',proof)
    return proof

def verify(proof,pptx):
    if (proof.get('schema')!=VERSION or proof.get('status')!='PASS' or proof.get('pdf_export')!='SUCCEEDED'
            or proof.get('all_page_pixels')!='EXACT' or proof.get('preview_pixels')!='EXACT'
            or proof.get('native_xml_and_fonts')!='BYTE_IDENTICAL' or proof.get('output_pptx_sha256')!=digest(pptx)
            or proof.get('validator_code_sha256')!=digest(__file__)
            or proof.get('backend') not in ('PowerPoint','LibreOffice')):raise ValueError('Current final PPTX lacks current actual export/equivalence proof')
    observation=proof.get('observation',{})
    if observation.get('scales')!=list(SCALES) or observation.get('base_long_side_px')!=720 or not observation.get('pages'):
        raise ValueError('Incomplete multi-scale export observation')
    for page in observation['pages']:
        if any(len(page.get(k,[]))!=4 for k in ('rect','mediabox','cropbox')) or page.get('rotation') not in (0,90,180,270):
            raise ValueError('Incomplete PDF canvas observation')
        if [p.get('scale') for p in page.get('pixels',[])]!=list(SCALES):raise ValueError('Missing PDF scale observation')
        for row in page['pixels']:
            if not re.fullmatch('[0-9a-f]{64}',row.get('sha256','')) or row.get('width',0)<=0 or row.get('height',0)<=0:
                raise ValueError('Invalid actual PDF pixel observation')
    return True
