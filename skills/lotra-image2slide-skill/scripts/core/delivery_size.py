"""Lossless package/resource compaction with replayable content protection.

No native geometry, text, equations, fonts, or image samples are simplified.
Only proven equivalent resource representations and storage encoding change.
The original remains immutable; an independent host comparison gates delivery.
"""
import copy,posixpath,hashlib,shutil,zlib
from pathlib import Path,PurePosixPath
from urllib.parse import unquote
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import digest,identity,write_json

REL='http://schemas.openxmlformats.org/package/2006/relationships'
RID='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PARSER=E.XMLParser(resolve_entities=False,no_network=True)

def target(owner,value):
    value=unquote(value)
    if '\\' in value:raise ValueError('Unsafe nonportable OPC resource')
    result=posixpath.normpath(posixpath.join(posixpath.dirname(owner),value)) if not value.startswith('/') else value[1:]
    if result.startswith('../') or result in ('.','..'):raise ValueError('OPC target escapes package')
    return result

def owner_of(name):
    if name=='_rels/.rels':return ''
    path=PurePosixPath(name)
    return str(path.parent.parent/(path.name[:-5]))

def used_ids(data):
    tree=E.fromstring(data,PARSER)
    return {value for node in tree.iter() for key,value in node.attrib.items()
        if key.startswith('{'+RID+'}') or key=='{urn:schemas-microsoft-com:office:office}relid'}

def package_plan(source):
    changed={};removed=set();aliases={};relations={};images={};signed=False
    with ZipFile(source) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate OPC names')
        if any(n.startswith('_xmlsignatures/') for n in names):signed=True
        for name in names:
            if name.endswith('.rels'):
                owner=owner_of(name);tree=E.fromstring(z.read(name),PARSER);used=None
                if owner.endswith('.xml') and owner in names and not signed:used=used_ids(z.read(owner))
                for row in list(tree):
                    if row.get('TargetMode')=='External':continue
                    resolved=target(owner,row.get('Target',''));relations.setdefault(name,[]).append((row.get('Id'),resolved))
                    if resolved not in names:raise ValueError('Missing OPC resource '+resolved)
                    if used is not None and row.get('Type','').endswith('/image') and resolved.startswith('ppt/media/') and row.get('Id') not in used:
                        tree.remove(row);changed[name]=tree
                relations[name]=[(row.get('Id'),target(owner,row.get('Target'))) for row in tree if row.get('TargetMode')!='External']
        reachable={t for rows in relations.values() for _,t in rows}
        if not signed:
            removed={n for n in names if n.startswith('ppt/media/') and n not in reachable}
            for name in sorted(n for n in names if n.startswith('ppt/media/') and n not in removed):
                with z.open(name) as stream:
                    h=hashlib.sha256()
                    for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
                key=(PurePosixPath(name).suffix.lower(),h.hexdigest())
                if key in images:aliases[name]=images[key];removed.add(name)
                else:images[key]=name
            for name in relations:
                tree=changed.get(name)
                if tree is None:tree=E.fromstring(z.read(name),PARSER)
                owner=owner_of(name)
                for row in tree:
                    if row.get('TargetMode')=='External':continue
                    resolved=target(owner,row.get('Target'))
                    if resolved in aliases:
                        row.set('Target',posixpath.relpath(aliases[resolved],posixpath.dirname(owner) or '.'));changed[name]=tree
            if removed:
                types=E.fromstring(z.read('[Content_Types].xml'),PARSER)
                for row in list(types):
                    if row.get('PartName','').lstrip('/') in removed:types.remove(row)
                changed['[Content_Types].xml']=types
    return {'changed':changed,'removed':removed,'aliases':aliases,'signed':signed}

def verify_package(before,after,plan):
    from .representation_codec import verify_asset
    def equivalent(x,y,name):
        if x==y:return True
        suffix=PurePosixPath(name).suffix.lower()
        if name.startswith('ppt/media/') and suffix in ('.svg','.png'):
            return verify_asset(x,y,suffix[1:])
        raise ValueError('Protected resource/native XML changed: '+name)
    if plan['signed'] and digest(before)!=digest(after):raise ValueError('Signed package must remain byte-identical')
    with ZipFile(before) as a,ZipFile(after) as b:
        if set(b.namelist())!=set(a.namelist())-plan['removed']:raise ValueError('Unplanned OPC part change')
        for name in b.namelist():
            if name not in plan['changed']:equivalent(a.read(name),b.read(name),name)
            elif b.read(name)!=E.tostring(plan['changed'][name],xml_declaration=True,encoding='UTF-8',standalone=True):
                raise ValueError('Unplanned relationship/content-type change')
        for name in [n for n in b.namelist() if n.endswith('.rels')]:
            owner=owner_of(name);old=E.fromstring(a.read(name),PARSER);new=E.fromstring(b.read(name),PARSER)
            used=used_ids(a.read(owner)) if owner.endswith('.xml') and owner in a.namelist() else None
            by={r.get('Id'):r for r in new}
            for row in old:
                rid=row.get('Id')
                if rid not in by:
                    if used is None or rid in used or not row.get('Type','').endswith('/image'):raise ValueError('Live relationship removed')
                    continue
                nr=by[rid]
                if row.get('Type')!=nr.get('Type') or row.get('TargetMode')!=nr.get('TargetMode'):raise ValueError('OPC role changed')
                if row.get('TargetMode')=='External':
                    if row.get('Target')!=nr.get('Target'):raise ValueError('External relation changed')
                else:
                    x,y=target(owner,row.get('Target')),target(owner,nr.get('Target'))
                    equivalent(a.read(x),b.read(y),x)
        # Original fonts, native shapes, text and OMML XML stay byte-identical.
    return True

def _strategy(data):
    from .representation_codec import deflate
    choices=[(zlib.Z_DEFAULT_STRATEGY,deflate(data))]
    # Long incompressible streams rarely benefit; bound CPU without weakening
    # quality. The default still encodes every byte and every resource.
    if len(data)<=4*1024*1024:
        choices.extend((s,deflate(data,s)) for s in (zlib.Z_FILTERED,zlib.Z_RLE,zlib.Z_HUFFMAN_ONLY,zlib.Z_FIXED))
    strategy,blob=min(choices,key=lambda item:len(item[1]))
    if zlib.decompress(blob,-15)!=data:raise ValueError('ZIP storage codec changed bytes')
    return strategy,len(blob)

def verify_coverage(source,receipt):
    """Reconcile independently enumerated OPC names, not a claimed count."""
    with ZipFile(source) as z:
        rows=receipt.get('resources',[]);by={r['part']:r for r in rows}
        if len(by)!=len(rows) or set(by)!=set(z.namelist()):raise ValueError('Incomplete resource optimization coverage')
        for info in z.infolist():
            row=by[info.filename]
            if row.get('input_sha256')!=hashlib.sha256(z.read(info)).hexdigest():raise ValueError('Cost coverage input changed')
            if row.get('status') not in ('OPTIMIZED','EVALUATED_NO_GAIN','REMOVED_UNREACHABLE','EXACT_ALIAS','SIGNED_IMMUTABLE'):
                raise ValueError('Resource optimization lacks a terminal result')
    return True

def optimize_pptx(source,output,*,profile='full'):
    from .representation_codec import optimize,sha
    if profile not in ('full','lexical','storage'):raise ValueError('Unknown lossless storage profile')
    source,output=Path(source).resolve(),Path(output).resolve()
    if source==output or output.exists():raise ValueError('New owned output required')
    source_hash=digest(source);plan=package_plan(source);output.parent.mkdir(parents=True,exist_ok=True)
    trial=output.with_name(output.name+'.trial');assert not trial.exists()
    coverage=[]
    if plan['signed']:
        shutil.copyfile(source,output)
        with ZipFile(source) as z:
            coverage=[{'part':i.filename,'input_sha256':sha(z.read(i)),'output_sha256':sha(z.read(i)),
                'status':'SIGNED_IMMUTABLE','before_stored':i.compress_size,'after_stored':i.compress_size} for i in z.infolist()]
        result={'status':'PASS','selection':'ORIGINAL_STORAGE_RETAINED','input_sha256':source_hash,
            'output_sha256':digest(output),'before_bytes':source.stat().st_size,'after_bytes':output.stat().st_size,
            'removed_media':0,'duplicate_media':0,'native_xml_and_fonts':'BYTE_IDENTICAL','relationship_contents':'BYTE_IDENTICAL',
            'geometry_simplification':False,'resources':coverage,'coverage':'COMPLETE','signed_package':'BYTE_IDENTICAL'}
        verify_coverage(source,result);return result
    with ZipFile(source) as old,ZipFile(trial,'w',ZIP_DEFLATED,compresslevel=9) as new:
        for info in old.infolist():
            name=info.filename;original=old.read(info)
            row={'part':name,'input_sha256':sha(original),'before_raw':len(original),'before_stored':info.compress_size}
            if name in plan['removed']:
                row.update(status='EXACT_ALIAS' if name in plan['aliases'] else 'REMOVED_UNREACHABLE',after_stored=0,
                    output_sha256=None,alias=plan['aliases'].get(name));coverage.append(row);continue
            item=copy.copy(info);item.compress_type=ZIP_DEFLATED;item._compresslevel=9
            data=E.tostring(plan['changed'][name],xml_declaration=True,encoding='UTF-8',standalone=True) if name in plan['changed'] else original
            if name.startswith('ppt/media/'):
                kind=PurePosixPath(name).suffix.lower()[1:]
                if profile=='full':data,proof=optimize(data,kind)
                elif profile=='lexical' and kind=='svg':data,proof=optimize(data,kind,region_limit=0)
                else:proof={'status':'INAPPLICABLE','reason':'guarded_fallback_profile_preserves_live_media_bytes'}
                row['representation']=proof
            strategy,length=_strategy(data)
            # ZIP uses ordinary interoperable DEFLATE; no new client runtime.
            with new.open(item,'w') as writer:
                writer._compressor=zlib.compressobj(9,zlib.DEFLATED,-15,8,strategy)
                writer.write(data)
            row.update(status='OPTIMIZED' if data!=original or length<info.compress_size else 'EVALUATED_NO_GAIN',
                output_sha256=sha(data),after_raw=len(data),after_stored=length,zip_strategy=strategy)
            coverage.append(row)
    verify_package(source,trial,plan)
    if trial.stat().st_size<source.stat().st_size:trial.rename(output);selected='COMPACTED'
    else:
        shutil.copyfile(source,output);selected='ORIGINAL_STORAGE_RETAINED'
        trial.unlink()
    if digest(source)!=source_hash:raise ValueError('Source changed during compaction')
    result={'status':'PASS','selection':selected,'input_sha256':source_hash,'output_sha256':digest(output),
        'before_bytes':source.stat().st_size,'after_bytes':output.stat().st_size,
        'removed_media':len(plan['removed']),'duplicate_media':len(plan['aliases']),
        'native_xml_and_fonts':'BYTE_IDENTICAL','relationship_contents':'PROVED_EQUIVALENT','geometry_simplification':False,
        'resources':coverage,'coverage':'COMPLETE','font_subsetting':False,'image_downsampling':False,'profile':profile}
    verify_coverage(source,result)
    return result

def verify_pdf(before,after):
    import pymupdf as pdf
    with pdf.open(before) as a,pdf.open(after) as b:
        if len(a)!=len(b) or a.get_toc()!=b.get_toc():raise ValueError('PDF pages/outline changed')
        for p,q in zip(a,b):
            if p.rect!=q.rect or p.rotation!=q.rotation or p.get_text()!=q.get_text():raise ValueError('PDF geometry/text changed')
            links=lambda page:[{k:v for k,v in row.items() if k!='xref'} for row in page.get_links()]
            if links(p)!=links(q):raise ValueError('PDF link changed')
            # Bound memory on small machines; compare every page at both scales.
            for longest in (720,2000):
                factor=min(2.,longest/max(p.rect.width,p.rect.height));matrix=pdf.Matrix(factor,factor)
                x,y=p.get_pixmap(matrix=matrix,alpha=True),q.get_pixmap(matrix=matrix,alpha=True)
                if (x.width,x.height,x.samples)!=(y.width,y.height,y.samples):raise ValueError('PDF actual pixels changed')
        return {'pages':len(a),'text':'EXACT','rendered_pixels':'EXACT','scales':[720,2000]}

def optimize_pdf(source,output):
    import pymupdf as pdf
    source,output=Path(source).resolve(),Path(output).resolve()
    if source==output or output.exists():raise ValueError('New owned PDF output required')
    before=digest(source);trial=output.with_name(output.name+'.trial')
    with pdf.open(source) as doc:
        if doc.is_encrypted or doc.get_sigflags()>0:raise ValueError('Use the original signed/encrypted PDF storage')
        doc.save(trial,garbage=4,deflate=True,deflate_images=True,deflate_fonts=True,use_objstms=1,compression_effort=100)
    observed=verify_pdf(source,trial)
    if trial.stat().st_size<source.stat().st_size:trial.rename(output);selected='COMPACTED'
    else:shutil.copyfile(source,output);selected='ORIGINAL_STORAGE_RETAINED'
    if digest(source)!=before:raise ValueError('Source PDF changed')
    return {'status':'PASS','selection':selected,'input_sha256':before,'output_sha256':digest(output),
        'before_bytes':source.stat().st_size,'after_bytes':output.stat().st_size,'verification':observed,
        'rasterized':False,'image_downsampling':False,'font_subsetting':False}
