"""Same-face compatible names for an owned native rendering copy.

Only stdlib: the editor controller is also used before runtime registration.
No font installation, typographic-family merging or source-family substitution.
"""
import hashlib
import json
import posixpath
import re
import struct
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.parsers import expat
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

VERSION='native-font-aliases-1.37.5'
P='http://schemas.openxmlformats.org/presentationml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
A='http://schemas.openxmlformats.org/drawingml/2006/main'


def name_key(value):return ' '.join(unicodedata.normalize('NFC',value).split()).casefold()


def tables(data):
    if len(data)<12 or data[:4] not in (b'\0\1\0\0',b'OTTO',b'true'):
        raise ValueError('Complete standalone SFNT header required')
    count=struct.unpack_from('>H',data,4)[0]
    if not 0<count<=4096 or 12+16*count>len(data):raise ValueError('Complete SFNT table directory required')
    result={}
    for index in range(count):
        tag,checksum,offset,size=struct.unpack_from('>4sIII',data,12+16*index)
        if offset+size>len(data):raise ValueError('SFNT table leaves the embedded font')
        if tag in result:raise ValueError('Duplicate SFNT table')
        result[tag]=(offset,size)
    return result


def saved_checksum_adjustment(data):
    head,size=tables(data).get(b'head',(0,0))
    if size<54:raise ValueError('One complete SFNT head table required')
    complete=len(data)//4*4
    checksum=sum(value for (value,) in struct.iter_unpack('>I',memoryview(data)[:complete]))
    if complete<len(data):checksum+=int.from_bytes(data[complete:]+b'\0'*(4-len(data[complete:])),'big')
    if checksum&0xFFFFFFFF!=0xB1B0AFBA:raise ValueError('Embedded SFNT checksum is invalid')
    return struct.unpack_from('>I',data,head+8)[0]


def decode_sfnt(data,content_type):
    if content_type=='application/x-font-ttf':saved_checksum_adjustment(data);return data
    if content_type!='application/x-fontdata' or len(data)<82:raise ValueError('Unsupported embedded font representation')
    total,size,version,flags=struct.unpack_from('<4I',data)
    rights,magic=struct.unpack_from('<HH',data,32)
    if total!=len(data) or magic!=0x504C or flags&5:
        raise ValueError('A complete uncompressed, non-subset EOT resource is required')
    if rights&0x200 or not (rights&8 or rights&0xE==0) or not 0<size<=len(data)-82:
        raise ValueError('Embedded font payload/rights are incompatible with editable delivery')
    body=data[-size:]
    if struct.unpack_from('<I',data,60)[0]!=saved_checksum_adjustment(body):
        raise ValueError('EOT CheckSumAdjustment differs from the actual saved SFNT head')
    return body


def names(data,wanted):
    offset,size=tables(data).get(b'name',(0,0))
    if size<6:raise ValueError('Embedded font name table missing')
    version,count,storage=struct.unpack_from('>3H',data,offset)
    if count>4096 or 6+12*count>size or storage>size:raise ValueError('Invalid embedded font name directory')
    result=set()
    for index in range(count):
        platform,encoding,language,name_id,length,start=struct.unpack_from('>6H',data,offset+6+12*index)
        if name_id not in wanted:continue
        if storage+start+length>size or length>8192:raise ValueError('Embedded font name leaves its table')
        raw=data[offset+storage+start:offset+storage+start+length]
        if platform in (0,3):text=raw.decode('utf-16be')
        elif platform==1 and encoding==0:text=raw.decode('mac_roman')
        else:continue
        text=text.strip()
        if text and '\0' not in text and not text.startswith('@'):result.add(text)
    return sorted(result)


def family_plan(pptx):
    families={};total=0
    with ZipFile(pptx) as package:
        listing=package.namelist()
        if len(listing)!=len(set(listing)):raise ValueError('Duplicate native input ZIP members')
        root=ET.fromstring(package.read('ppt/presentation.xml'))
        embedded=root.find('{'+P+'}embeddedFontLst')
        if embedded is None:return {'version':VERSION,'families':{}}
        rels={n.get('Id'):n for n in ET.fromstring(package.read('ppt/_rels/presentation.xml.rels'))}
        types=ET.fromstring(package.read('[Content_Types].xml'))
        if len(embedded)>256:raise ValueError('Bounded native font family count exceeded')
        for entry in embedded:
            font=entry.find('{'+P+'}font');family=font.get('typeface','') if font is not None else ''
            if not family or len(family)>2048 or family in families:raise ValueError('One distinct declared embedded font family required')
            aliases=None;faces=[]
            for slot in ('regular','bold','italic','boldItalic'):
                node=entry.find('{'+P+'}'+slot)
                if node is None:continue
                rel=rels.get(node.get('{'+R+'}id'))
                if rel is None or rel.get('Type')!=R+'/font' or rel.get('TargetMode')=='External':
                    raise ValueError('Bound native font needs an internal font relationship')
                part=posixpath.normpath(posixpath.join('ppt',rel.get('Target','')))
                if not part.startswith('ppt/fonts/') or part not in listing:raise ValueError('Embedded native font leaves the font domain')
                if package.getinfo(part).file_size>64*1024*1024:raise ValueError('Native embedded font budget exceeded')
                data=package.read(part);total+=len(data)
                if total>64*1024*1024:raise ValueError('Native embedded font budget exceeded')
                content=next((n.get('ContentType') for n in types if n.get('PartName')=='/'+part),None)
                content=content or next((n.get('ContentType') for n in types if n.get('Extension')==part.rsplit('.',1)[-1]),None)
                body=decode_sfnt(data,content);directory=tables(body)
                os2,length=directory.get(b'OS/2',(0,0))
                if length<10:raise ValueError('Native font embedding rights table missing')
                rights=struct.unpack_from('>H',body,os2+8)[0]
                if rights&0x200 or not (rights&8 or rights&0xE==0):raise ValueError('Editable native font rights required')
                compatible=names(body,{1})
                if name_key(family) not in {name_key(name) for name in compatible}:
                    raise ValueError('FONT_NATIVE_ALIAS_IDENTITY: declared family differs from compatible name ID 1')
                current={name_key(name):name for name in compatible}
                aliases=current if aliases is None else {k:aliases[k] for k in aliases.keys()&current.keys()}
                faces.append({'slot':slot,'part':part,'part_sha256':hashlib.sha256(data).hexdigest(),
                    'sfnt_sha256':hashlib.sha256(body).hexdigest(),'postscript_names':names(body,{6})})
            if not faces or not aliases:raise ValueError('Native font has no complete compatible resource')
            families[family]={'aliases':[aliases[k] for k in sorted(aliases)],'faces':faces}
    return {'version':VERSION,'families':families}


def validate_plan(directory):
    directory=Path(directory);plan=json.loads((directory/'editor-plan.json').read_bytes())
    expected=family_plan(directory/'editor-input.pptx')
    if expected['families'] or 'font_aliases' in plan:
        if plan.get('font_aliases')!=expected:
            raise ValueError('FONT_NATIVE_ALIAS_PLAN_REQUIRED: use the exact current embedded compatible-family resources')
    return expected


def patch_names(data,mapping):
    """Replace attribute values only; retain namespace prefixes/extension bytes."""
    parser=expat.ParserCreate(namespace_separator='}');edits=[];changes=[]
    def forbidden(*args):raise ValueError('DTD/entity declarations are not native font names')
    parser.StartDoctypeDeclHandler=forbidden;parser.EntityDeclHandler=forbidden
    def start(tag,attributes):
        if tag not in {A+'}'+kind for kind in ('latin','ea','cs')}:return
        original=attributes.get('typeface','');match=mapping.get(name_key(original))
        if not match or not match[1] or original==match[1]:return
        begin=parser.CurrentByteIndex;end=begin;quote=None
        while end<len(data):
            char=data[end]
            if quote:
                if char==quote:quote=None
            elif char in (34,39):quote=char
            elif char==62:break
            end+=1
        found=re.search(rb'\stypeface\s*=\s*([\x22\x27])(.*?)\1',data[begin:end],re.DOTALL)
        if found is None:raise ValueError('Native typeface attribute byte span missing')
        value=escape(match[1],{'"':'&quot;',"'":'&apos;'}).encode('utf-8')
        edits.append((begin+found.start(2),begin+found.end(2),value))
        changes.append({'family':match[0],'from':original,'to':match[1]})
    parser.StartElementHandler=start;parser.Parse(data,True)
    for begin,end,value in reversed(edits):data=data[:begin]+value+data[end:]
    return data,changes


def native_input(directory,plan,available):
    """Resolve compatible ID-1 names only in an owned transient import copy."""
    directory=Path(directory);available={name_key(n):n for n in available if n and not n.startswith('@')}
    mapping={};resolved={};changes=[]
    for family,row in plan['families'].items():
        aliases={name_key(n) for n in row['aliases']}
        chosen=available.get(name_key(family)) or next((available[k] for k in sorted(aliases) if k in available),None)
        resolved[family]=chosen
        for alias in aliases:
            if alias in mapping and mapping[alias][0]!=family:raise ValueError('Ambiguous compatible native family alias')
            mapping[alias]=(family,chosen)
    source=directory/'editor-input.pptx';target=directory/'editor-native-input.pptx'
    if target.exists() or target.is_symlink():raise ValueError('Preserve existing native font import copy')
    with ZipFile(source) as package,ZipFile(target,'x',ZIP_DEFLATED) as output:
        for info in package.infolist():
            data=package.read(info.filename)
            if info.filename.startswith('ppt/') and info.filename.endswith('.xml'):
                data,edits=patch_names(data,mapping)
                if edits:
                    changes.append({'part':info.filename,'attributes':edits})
            output.writestr(info,data)
    return target,{'version':VERSION,'resolved_families':resolved,'changes':changes,
        'native_input_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'scope':'Owned import copy; compatible name ID 1 aliases from the exact embedded physical faces; canonical input unchanged'}


def ordinary_usage(document,plan,resolution):
    """Inspect every real text portion, nested shape and table cell after import."""
    aliases={name_key(alias):family for family,row in plan['families'].items() for alias in row['aliases']}
    usage={};portions=0;cells=0;shapes=0
    def text(owner,label):
        nonlocal portions
        before=owner.String
        for paragraph in owner.createEnumeration():
            for portion in paragraph.createEnumeration():
                text=portion.String
                if not text:continue
                portions+=1;roles=set()
                for char in text:
                    if char.isspace():continue
                    roles.add('Asian' if ord(char)>=0x2E80 else 'Complex' if unicodedata.bidirectional(char) in ('R','AL','AN') else '')
                for role in roles:
                    name=portion.getPropertyValue('CharFontName'+role);family=aliases.get(name_key(name))
                    if family is None:continue
                    chosen=resolution['resolved_families'][family]
                    if not chosen or name_key(name)!=name_key(chosen):
                        raise ValueError('FONT_NATIVE_ALIAS_UNAVAILABLE: '+family+' at '+label)
                    row=usage.setdefault(family,{'native_names':set(),'postscript_names':set(),'owners':set()})
                    row['native_names'].add(name);row['owners'].add(label)
                    for face in plan['families'][family]['faces']:row['postscript_names'].update(face['postscript_names'])
        if owner.String!=before:raise ValueError('Native font resolution changed text literals')
    def collection(items,path):
        nonlocal cells,shapes
        for index in range(items.Count):
            shape=items.getByIndex(index);shapes+=1;label=path+'/'+str(index)+':'+shape.Name
            if shape.ShapeType=='com.sun.star.drawing.GroupShape':collection(shape,label)
            elif shape.ShapeType=='com.sun.star.drawing.TableShape':
                table=shape.Model
                for row in range(table.Rows.Count):
                    for col in range(table.Columns.Count):cells+=1;text(table.getCellByPosition(col,row),label+'/cell/'+str(row)+','+str(col))
            elif hasattr(shape,'Text'):text(shape.Text,label)
    for slide in range(document.DrawPages.Count):collection(document.DrawPages.getByIndex(slide),'slide/'+str(slide))
    return {'families':{family:{key:sorted(values) for key,values in row.items()} for family,row in usage.items()},
        'coverage':{'shapes':shapes,'table_cells':cells,'nonempty_text_portions':portions}}


def verify_pdf_families(usage,actual_names):
    """Global PDF family evidence only; per-feature visual gates remain separate."""
    actual={name_key(re.sub(r'^[A-Z]{6}\+','',name)) for name in actual_names}
    result=[]
    for family,row in usage.items():
        expected={name_key(name) for name in row['postscript_names']}
        passed=bool(expected&actual)
        result.append({'family':family,'native_names':row['native_names'],
            'expected_postscript_names':row['postscript_names'],'passed':passed})
    if any(not row['passed'] for row in result):
        raise ValueError('FONT_RENDER_FAMILY_UNVERIFIED: '+json.dumps(result,ensure_ascii=False))
    return {'status':'PDF_FAMILIES_OBSERVED' if result else 'NO_BOUND_ORDINARY_TEXT_FAMILIES',
        'families':result,'actual_pdf_font_names':sorted(actual_names),
        'scope':'Observed PDF family set; no per-glyph, source-font identity, mathematics or whole-artwork acceptance claim'}
