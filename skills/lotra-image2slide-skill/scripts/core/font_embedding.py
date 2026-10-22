"""Full editable font embedding on a new PPTX copy, without Office installs.

Uses PresentationML font parts and uncompressed EOT 0x00020001. TrueType
collections are split losslessly by the already declared fontTools dependency.
CFF/variable fonts remain capability-pending rather than being mislabeled.
"""
import io
import posixpath
import struct
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from .common import digest, identity, read_json, write_json
from .font_resources import describe, font_names, matches

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
FONT_REL = R+'/font'


class FontCommitPending(PermissionError):
    """A verified owned font stage can be committed after its Windows lock clears."""
    def __init__(self,record,cause):
        self.record=Path(record)
        super().__init__('FONT_COMMIT_PENDING: release the existing file handle, then resume the owned font stage: '+str(record)+'; '+str(cause))


def _commit_identity(bindings):
    return identity([{'request':b.get('request'),'family':b['family'],
        'resource':{k:b['resource'][k] for k in ('id','file_sha256','face_index')}} for b in bindings])


def _commit_record(pptx,temporary,bindings,operation):
    marker=temporary.with_suffix('.font-commit.json')
    expected={'schema':'lotra-font-commit-1','operation':operation,'target':pptx.name,
              'temporary':temporary.name,'bindings_hash':_commit_identity(bindings)}
    if temporary.is_symlink() or marker.is_symlink():raise ValueError('FONT_COMMIT_CONFLICT: redirected font stage')
    if marker.exists():
        record=read_json(marker)
        if any(record.get(k)!=v for k,v in expected.items()):raise ValueError('FONT_COMMIT_CONFLICT: different font stage owner or intent')
        return marker,record
    if temporary.exists():raise FileExistsError('Unregistered font stage retained for inspection: '+str(temporary))
    record={**expected,'phase':'WRITING','input_sha256':digest(pptx)}
    with marker.open('x',encoding='utf-8',newline='\n') as file:
        __import__('json').dump(record,file,sort_keys=True)
    return marker,record


def _finish_commit(pptx,temporary,marker,record,bindings,max_font_bytes):
    if record.get('phase') not in ('READY','COMMITTED'):
        raise ValueError('FONT_COMMIT_RECOVERY_REQUIRED: incomplete owned font stage retained: '+str(marker))
    current=digest(pptx)
    if not temporary.exists() and current==record.get('staged_sha256'):
        return dict(record['result'],pptx_sha256=current)
    if current!=record['input_sha256'] or not temporary.is_file() or digest(temporary)!=record.get('staged_sha256'):
        raise ValueError('FONT_COMMIT_CONFLICT: source or staged bytes changed; preserve both files')
    if record['result']['font_bytes']>max_font_bytes:raise ValueError('FONT_BUDGET_PENDING: retained stage exceeds the current font budget')
    from .font_retention import verify_package
    checked=[b for b in bindings if b['resource'].get('outline')=='truetype' and not b['resource'].get('variable')] if record['operation']=='direct' else bindings
    with ZipFile(temporary) as completed:verify_package(completed,checked)
    # No source, output or validation ZIP remains open at the replacement boundary.
    try:temporary.replace(pptx)
    except PermissionError as error:raise FontCommitPending(marker,error) from error
    record['phase']='COMMITTED';write_json(marker,record)
    return dict(record['result'],pptx_sha256=digest(pptx))


def eot(face):
    from fontTools.ttLib import TTFont
    if digest(face['path']) != face['file_sha256']:
        raise ValueError('Bound font file changed; resolve its identity before export')
    current = describe(face['path'], face['face_index'], face['file_sha256'])
    if not matches(current,face['family']):
        raise ValueError('Font resource metadata cannot alias another typeface')
    if not current['editable_embedding']:
        raise ValueError('Font does not permit editable embedding: '+current['family'])
    if current['variable'] or current['outline'] != 'truetype':
        raise ValueError('FONT_EMBEDDING_CAPABILITY_PENDING: static TrueType outlines required for the direct EOT route; retain this exact font and use a compatible existing Office/font provider')
    font = TTFont(face['path'], fontNumber=face['face_index'], lazy=False,
                  recalcBBoxes=False, recalcTimestamp=False)
    try:
        os2 = font['OS/2']
        panose = bytes(getattr(os2.panose, name) for name in (
            'bFamilyType', 'bSerifStyle', 'bWeight', 'bProportion', 'bContrast',
            'bStrokeVariation', 'bArmStyle', 'bLetterForm', 'bMidline', 'bXHeight'))
        data = io.BytesIO()
        font.save(data)
        sfnt = data.getvalue()
        ranges = [int(getattr(os2, 'ulUnicodeRange'+str(i), 0)) for i in range(1, 5)]
        codepages = [int(getattr(os2, 'ulCodePageRange'+str(i), 0)) for i in range(1, 3)]
        header = struct.pack('<IIII10sBBIHH7I4IH', 0, len(sfnt), 0x00020001, 0,
            panose, 1, int(current['italic']), current['weight'], current['fs_type'], 0x504C,
            *ranges, *codepages, int(font['head'].checkSumAdjustment), 0, 0, 0, 0, 0)
        strings = b''
        for index, names in enumerate(((1,), (2,), (5,), (4,))):
            text = (font_names(font, names) or [''])[0].encode('utf-16le')
            if len(text) > 65535:
                raise ValueError('Font naming data exceeds the EOT string bound')
            strings += (b'\0\0' if index else b'') + struct.pack('<H', len(text)) + text
        payload = header + strings + b'\0\0\0\0' + sfnt
        return struct.pack('<I', len(payload)) + payload[4:]
    finally:
        font.close()


def embed(pptx, bindings, max_font_bytes=64*1024*1024):
    """Only font parts/relationships/settings change; all slide XML is retained."""
    faces = {b['resource']['id']: b['resource'] for b in bindings}
    if not faces:
        return {'status': 'NO_TEXT_FONTS', 'font_count': 0}
    pptx=Path(pptx);temporary=pptx.with_name(pptx.stem+'.fonts-pending.pptx')
    marker=temporary.with_suffix('.font-commit.json')
    if marker.exists() or temporary.exists():
        marker,record=_commit_record(pptx,temporary,bindings,'direct')
        return _finish_commit(pptx,temporary,marker,record,bindings,max_font_bytes)
    input_hash=digest(pptx)
    payloads={};pending=[]
    for key,face in faces.items():
        if face.get('outline')!='truetype' or face.get('variable'):
            pending.append({'resource_id':key,'family':face['family'],'reason':'existing compatible Office/font embedding provider required'})
            continue
        cache_root=next((p for p in Path(face['path']).parents if p.name=='.lotraAI-build'),None)
        cache=(cache_root/'toolchain/fontdata'/('eot-v2-'+key+'.fntdata')) if cache_root else None
        receipt=cache.with_suffix('.json') if cache else None
        record=read_json(receipt) if receipt and receipt.is_file() else {}
        if (cache and cache.is_file() and digest(face['path'])==face['file_sha256']
                and record.get('source_sha256')==face['file_sha256'] and record.get('fontdata_sha256')==digest(cache)):
            payloads[key]=cache.read_bytes()
        else:
            payloads[key]=eot(face)
            if cache:
                cache.parent.mkdir(parents=True,exist_ok=True)
                cache.write_bytes(payloads[key])
                write_json(receipt,{'source_sha256':face['file_sha256'],'face_index':face['face_index'],'fontdata_sha256':digest(cache)})
    if sum(map(len, payloads.values())) > max_font_bytes:
        raise ValueError('FONT_BUDGET_PENDING: do not silently subset editable fonts or substitute another family')
    pptx = Path(pptx)
    with ZipFile(pptx) as archive:
        content = {name:archive.read(name) for name in ('ppt/presentation.xml','ppt/_rels/presentation.xml.rels','[Content_Types].xml')}
        infos = {info.filename: info for info in archive.infolist()}
    presentation = E.fromstring(content['ppt/presentation.xml'])
    relname = 'ppt/_rels/presentation.xml.rels'
    rels = E.fromstring(content[relname])
    types = E.fromstring(content['[Content_Types].xml'])
    embedded = presentation.find('{'+P+'}embeddedFontLst')
    if embedded is None:
        embedded = E.Element('{'+P+'}embeddedFontLst')
        successors = {'custShowLst', 'photoAlbum', 'custDataLst', 'kinsoku', 'defaultTextStyle', 'modifyVerifier', 'extLst'}
        position = next((i for i, n in enumerate(presentation) if E.QName(n).localname in successors), len(presentation))
        presentation.insert(position, embedded)
    presentation.set('embedTrueTypeFonts', '1')
    presentation.set('saveSubsetFonts', '0')
    records = []
    for key, data in sorted(payloads.items()):
        face=faces[key]
        part = 'ppt/fonts/lotra-'+key[:24]+'.fntdata'
        content[part] = data
        target = posixpath.relpath(part, 'ppt')
        relation = next((r for r in rels if r.get('Type') == FONT_REL and r.get('Target') == target), None)
        if relation is None:
            rid = 'rIdLotraFont'+key[:24]
            if any(r.get('Id') == rid for r in rels):
                raise ValueError('Font relationship identity collision')
            relation = E.SubElement(rels, '{'+REL+'}Relationship', Id=rid, Type=FONT_REL, Target=target)
        family = face['family']
        entry = next((n for n in embedded if n.find('{'+P+'}font') is not None
                      and n.find('{'+P+'}font').get('typeface') == family), None)
        if entry is None:
            entry = E.SubElement(embedded, '{'+P+'}embeddedFont')
            E.SubElement(entry, '{'+P+'}font', typeface=family)
        slot = ('bold' if face['weight'] >= 600 else '')+('Italic' if face['italic'] and face['weight'] >= 600 else 'italic' if face['italic'] else '')
        slot = slot or 'regular'
        node = entry.find('{'+P+'}'+slot)
        if node is None:
            node = E.SubElement(entry, '{'+P+'}'+slot)
            order = {'font': 0, 'regular': 1, 'bold': 2, 'italic': 3, 'boldItalic': 4}
            entry[:] = sorted(entry, key=lambda n: order[E.QName(n).localname])
        node.set('{'+R+'}id', relation.get('Id'))
        if not any(n.get('PartName') == '/'+part for n in types):
            E.SubElement(types, '{'+CT+'}Override', PartName='/'+part, ContentType='application/x-fontdata')
        records.append({'family': family, 'slot': slot, 'file_sha256': face['file_sha256'],
                        'face_index': face['face_index'], 'part': part, 'fontdata_bytes': len(data)})
    for name, tree in (('ppt/presentation.xml', presentation), (relname, rels), ('[Content_Types].xml', types)):
        content[name] = E.tostring(tree, xml_declaration=True, encoding='UTF-8', standalone=True)
    if digest(pptx)!=input_hash:raise ValueError('FONT_COMMIT_CONFLICT: source changed before font staging')
    marker,commit=_commit_record(pptx,temporary,bindings,'direct')
    import shutil
    with ZipFile(pptx) as source,ZipFile(temporary, 'x', compression=ZIP_DEFLATED) as output:
        for info in source.infolist():
            if info.filename in content:output.writestr(info,content.pop(info.filename))
            else:
                with source.open(info) as reader,output.open(info,'w') as file:
                    shutil.copyfileobj(reader,file,1024*1024)
        for name,data in content.items():output.writestr(name,data)
    result={'status': 'FONT_EMBEDDING_PROVIDER_REQUIRED' if pending else 'EMBEDDED_FULL_EDITABLE_FONTS',
            'pending':pending,'font_count':len(payloads),'fonts':records,
            'font_bytes': sum(map(len, payloads.values())), 'pptx_sha256': digest(pptx),
            'scope': 'Serialized font resources; receiver application behavior and visual appearance are separate evidence'}
    if digest(pptx)!=commit['input_sha256']:raise ValueError('FONT_COMMIT_CONFLICT: source changed while embedding')
    commit.update(phase='READY',staged_sha256=digest(temporary),result=result);write_json(marker,commit)
    return _finish_commit(pptx,temporary,marker,commit,bindings,max_font_bytes)


def transfer_provider(original,provider,bindings,max_font_bytes=64*1024*1024):
    """Copy only requested embedded font resources from a staged Office save."""
    import shutil
    original,provider=map(Path,(original,provider))
    temporary=original.with_name(original.stem+'.provider-pending.pptx')
    marker=temporary.with_suffix('.font-commit.json')
    if marker.exists() or temporary.exists():
        marker,record=_commit_record(original,temporary,bindings,'provider')
        if record.get('result',{}).get('provider_sha256')!=digest(provider):raise ValueError('FONT_COMMIT_CONFLICT: provider changed')
        return _finish_commit(original,temporary,marker,record,bindings,max_font_bytes)
    input_hash=digest(original)
    expected={b['family'] for b in bindings}
    def slot(face):return 'boldItalic' if face['italic'] and face['weight']>=600 else 'italic' if face['italic'] else 'bold' if face['weight']>=600 else 'regular'
    expected_slots={(b['family'],slot(b['resource'])) for b in bindings}
    with ZipFile(provider) as donor,ZipFile(original) as source:
        present=E.fromstring(donor.read('ppt/presentation.xml'))
        embedded=present.find('{'+P+'}embeddedFontLst')
        if embedded is None or present.get('saveSubsetFonts') in ('1','true'):
            raise ValueError('Provider must serialize full embedded fonts, not a used-character subset')
        donor_rels={r.get('Id'):r for r in E.fromstring(donor.read('ppt/_rels/presentation.xml.rels'))}
        donor_types=E.fromstring(donor.read('[Content_Types].xml'))
        main=E.fromstring(source.read('ppt/presentation.xml'))
        rels=E.fromstring(source.read('ppt/_rels/presentation.xml.rels'))
        types=E.fromstring(source.read('[Content_Types].xml'))
        destination=main.find('{'+P+'}embeddedFontLst')
        if destination is None:
            destination=E.Element('{'+P+'}embeddedFontLst')
            successors={'custShowLst','photoAlbum','custDataLst','kinsoku','defaultTextStyle','modifyVerifier','extLst'}
            at=next((i for i,n in enumerate(main) if E.QName(n).localname in successors),len(main))
            main.insert(at,destination)
        changed={};found=set();found_slots=set();records=[]
        # A provider is needed for unsupported font resources only. Retain
        # already compiled complete TrueType families and avoid shipping a
        # second complete CJK font merely because Office saved another copy.
        source_rels={r.get('Id'):r for r in rels}
        for family in expected:
            faces=[b['resource'] for b in bindings if b['family']==family]
            entry=next((n for n in destination if n.find('{'+P+'}font') is not None and n.find('{'+P+'}font').get('typeface')==family),None)
            if entry is None or not all(f.get('outline')=='truetype' and not f.get('variable') for f in faces):continue
            direct=[]
            for face in {f['id']:f for f in faces}.values():
                node=entry.find('{'+P+'}'+slot(face))
                relation=source_rels.get(node.get('{'+R+'}id')) if node is not None else None
                target='fonts/lotra-'+face['id'][:24]+'.fntdata'
                if relation is None or relation.get('Type')!=FONT_REL or relation.get('Target')!=target:break
                part='ppt/'+target
                if part not in source.namelist():break
                direct.append({'family':family,'slot':slot(face),'part':part,'bytes':source.getinfo(part).file_size,'retained_direct_resource':True})
            else:
                found.add(family);found_slots.update((r['family'],r['slot']) for r in direct);records.extend(direct)
        for entry in embedded:
            font=entry.find('{'+P+'}font');family=font.get('typeface') if font is not None else None
            if family not in expected or family in found:continue
            replacement=E.fromstring(E.tostring(entry));slots=0
            for node in replacement:
                rid=node.get('{'+R+'}id')
                if rid is None:continue
                relation=donor_rels.get(rid)
                if relation is None or relation.get('Type')!=FONT_REL or relation.get('TargetMode')=='External':
                    raise ValueError('Embedded font provider has an invalid resource relation')
                part=posixpath.normpath(posixpath.join('ppt',relation.get('Target','')))
                if part.startswith('../') or part not in donor.namelist():raise ValueError('Embedded font resource leaves the provider package')
                data=donor.read(part);key=__import__('hashlib').sha256(data).hexdigest()
                if not data:raise ValueError('Embedded font resource is empty')
                target='ppt/fonts/lotra-provider-'+key[:24]+'.fntdata';changed[target]=data
                link='rIdLotraProvider'+key[:24]
                existing=next((r for r in rels if r.get('Id')==link),None)
                if existing is None:E.SubElement(rels,'{'+REL+'}Relationship',Id=link,Type=FONT_REL,Target=posixpath.relpath(target,'ppt'))
                elif existing.get('Target')!=posixpath.relpath(target,'ppt'):raise ValueError('Font provider relationship collision')
                node.set('{'+R+'}id',link)
                content_type=next((n.get('ContentType') for n in donor_types if n.get('PartName')=='/'+part),None)
                content_type=content_type or next((n.get('ContentType') for n in donor_types if n.get('Extension')==part.rsplit('.',1)[-1]),None)
                if content_type not in ('application/x-fontdata','application/x-font-ttf'):
                    raise ValueError('Unsupported embedded font content type')
                if content_type=='application/x-fontdata':
                    if len(data)<82 or struct.unpack_from('<H',data,34)[0]!=0x504C or struct.unpack_from('<I',data)[0]!=len(data):
                        raise ValueError('Provider did not serialize valid EOT font data')
                    permissions=struct.unpack_from('<H',data,32)[0]
                    flags=struct.unpack_from('<I',data,12)[0]
                    if flags&1 or permissions&0x200 or not (permissions&8 or permissions&0xE==0):
                        raise ValueError('Provider font is subsetted or lacks editable embedding rights')
                    if flags&4:raise ValueError('Compressed EOT needs a compatible identity-decoding provider; do not assert an unparsed font identity')
                    size=struct.unpack_from('<I',data,4)[0]
                    if not 0<size<=len(data)-82:raise ValueError('Provider EOT font payload is invalid')
                    fontdata=data[-size:]
                else:fontdata=data
                from fontTools.ttLib import TTFont
                resource=TTFont(io.BytesIO(fontdata),lazy=True)
                try:
                    families=font_names(resource,(16,1))
                    from .font_resources import name_key
                    if name_key(family) not in {name_key(n) for n in families}:raise ValueError('Provider font part names another actual typeface')
                    permission=int(getattr(resource.get('OS/2'),'fsType',2))
                    if permission&0x200 or not (permission&8 or permission&0xE==0):raise ValueError('Provider SFNT resource does not allow editable embedding')
                finally:resource.close()
                found_slots.add((family,E.QName(node).localname))
                if not any(n.get('PartName')=='/'+target for n in types):E.SubElement(types,'{'+CT+'}Override',PartName='/'+target,ContentType=content_type)
                slots+=1;records.append({'family':family,'slot':E.QName(node).localname,'part':target,'sha256':key,'bytes':len(data)})
            if not slots:continue
            old=next((n for n in destination if n.find('{'+P+'}font') is not None and n.find('{'+P+'}font').get('typeface')==family),None)
            if old is not None:destination.remove(old)
            destination.append(replacement);found.add(family)
        if expected-found:raise ValueError('Provider did not embed requested fonts: '+repr(sorted(expected-found)))
        if expected_slots-found_slots:raise ValueError('Provider did not embed every used font face: '+repr(sorted(expected_slots-found_slots)))
        if sum(r['bytes'] for r in records)>max_font_bytes:raise ValueError('FONT_BUDGET_PENDING: preserve exact families and revise the explicit file-size budget')
        main.set('embedTrueTypeFonts','1');main.set('saveSubsetFonts','0')
        for name,tree in (('ppt/presentation.xml',main),('ppt/_rels/presentation.xml.rels',rels),('[Content_Types].xml',types)):
            changed[name]=E.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True)
        marker,commit=_commit_record(original,temporary,bindings,'provider')
        with ZipFile(temporary,'x',compression=ZIP_DEFLATED) as output:
            for info in source.infolist():
                if info.filename in changed:output.writestr(info,changed.pop(info.filename))
                else:
                    with source.open(info) as reader,output.open(info,'w') as file:shutil.copyfileobj(reader,file,1024*1024)
            for name,data in changed.items():output.writestr(name,data)
    from .font_retention import verify_package
    with ZipFile(temporary) as completed:verify_package(completed,bindings)
    result={'status':'EMBEDDED_FULL_EDITABLE_FONTS','font_count':len(expected),'fonts':records,
            'font_bytes':sum(r['bytes'] for r in records),
            'provider_sha256':digest(provider),'pptx_sha256':digest(original),
            'scope':'Only embedded font parts transferred; native slide content, geometry and text retained byte-for-byte'}
    if digest(original)!=input_hash:raise ValueError('FONT_COMMIT_CONFLICT: source changed during provider transfer')
    commit.update(phase='READY',staged_sha256=digest(temporary),result=result);write_json(marker,commit)
    return _finish_commit(original,temporary,marker,commit,bindings,max_font_bytes)


def windows_provider(pptx,output,caps,bindings):
    import subprocess
    from .office_bridge import _host_path
    from .common import write_json,read_json
    capability=caps.get('windows_office',{})
    if not capability.get('available'):raise RuntimeError('Existing compatible font embedding host required; no Office/font installation')
    output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    output.mkdir(parents=True)
    ready=output/'Fonts-embedded.pptx';receipt=output/'font-provider.json'
    request=output/'font-request.json'
    write_json(request,{'input':_host_path(pptx),'input_sha256':digest(pptx),'output':_host_path(ready),
                        'receipt':_host_path(receipt),'families':sorted({b['family'] for b in bindings})})
    script=Path(__file__).resolve().parent.parent/'embed_office_fonts.ps1'
    process=subprocess.run([capability['powershell'],'-NoProfile','-ExecutionPolicy','Bypass','-File',_host_path(script),
                            '-Request',_host_path(request)],capture_output=True,stdin=subprocess.DEVNULL,timeout=180)
    if process.returncode or not ready.is_file() or not receipt.is_file():
        raise RuntimeError('Existing Office font save failed; preserve the staged attempt and use the bounded provider packet')
    result=read_json(receipt)
    if result.get('input_sha256')!=digest(pptx) or result.get('output_sha256')!=digest(ready):
        raise ValueError('Font provider receipt belongs to another file')
    return ready
