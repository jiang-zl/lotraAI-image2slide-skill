"""Physical canvas and one-shot, single-slide package normalization."""
import posixpath
import shutil
from zipfile import ZipFile
from lxml import etree as E
from .mathml import NS

SLIDE_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide'
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
CANONICAL = 'ppt/slides/slide1.xml'


def scene_dimensions(scene):
    canvas=scene['canvas']
    width=round(canvas['target_width_inches']*914400)
    return width,round(width*canvas['height']/canvas['width'])


def physical_canvas(presentation):
    root=E.fromstring(presentation) if isinstance(presentation,bytes) else presentation
    size=root.find('p:sldSz',NS)
    if size is None:raise ValueError('Native presentation canvas is missing')
    result=tuple(int(size.get(key,'0')) for key in ('cx','cy'))
    if min(result)<=0:raise ValueError('Positive native presentation dimensions required')
    return result


def same_canvas(left,right):
    """One EMU rounding tolerance; size classification is not physical size."""
    return all(abs(a-b)<=1 for a,b in zip(left,right))


def _target(owner,target):
    part=posixpath.normpath(target.lstrip('/') if target.startswith('/') else
                            posixpath.join(posixpath.dirname(owner),target))
    if part in ('','.','..') or part.startswith('../') or '\\' in part:
        raise ValueError('Invalid internal single-slide relationship target')
    return part


def _rels(part):
    return posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')


def _owner(rels):
    if rels=='_rels/.rels':return ''
    folder,name=posixpath.split(rels)
    return posixpath.join(posixpath.dirname(folder),name[:-5])


def single_slide(package):
    """Resolve the sole active slide through presentation relationships."""
    presentation=E.fromstring(package.read('ppt/presentation.xml'))
    slides=presentation.findall('p:sldIdLst/p:sldId',NS)
    if len(slides)!=1:raise ValueError('One reference image requires one uploaded partial slide')
    rels=E.fromstring(package.read('ppt/_rels/presentation.xml.rels'))
    matches=[r for r in rels if r.get('Id')==slides[0].get(RID)]
    if len(matches)!=1 or matches[0].get('Type')!=SLIDE_REL or matches[0].get('TargetMode')=='External':
        raise ValueError('The sole slide must have one internal presentation relationship')
    part=_target('ppt/presentation.xml',matches[0].get('Target',''))
    names=package.namelist()
    if len(names)!=len(set(names)):raise ValueError('Duplicate uploaded package parts require a corrected partial PPT')
    if part not in names:raise ValueError('The active partial slide part is missing')
    if any(name!=part for name in names if name.startswith('ppt/slides/slide') and name.endswith('.xml')):
        raise ValueError('Orphan slide parts require a clean single-slide partial PPT before adoption')
    if part!=CANONICAL and (CANONICAL in names or _rels(CANONICAL) in names):
        raise ValueError('An unrelated slide1 part conflicts with the sole active slide; supply a clean single-slide partial PPT')
    return {'part':part,'canvas':physical_canvas(presentation)}


def normalize_one_slide(source,output,description):
    """Rename only the selected slide in a private copy; retain original input."""
    part=description['part']
    if part==CANONICAL:
        shutil.copyfile(source,output)
        return {'original_slide_part':part,'working_slide_part':CANONICAL,'renamed':False}
    moved={part:CANONICAL,_rels(part):_rels(CANONICAL)}
    with ZipFile(source) as incoming,ZipFile(output,'x') as outgoing:
        for entry in incoming.infolist():
            name=entry.filename;data=incoming.read(name);destination=moved.get(name,name)
            if name=='[Content_Types].xml':
                root=E.fromstring(data);changed=False
                for item in root:
                    if item.get('PartName')=='/'+part:
                        item.set('PartName','/'+CANONICAL);changed=True
                if changed:data=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
            elif name.endswith('.rels'):
                root=E.fromstring(data);owner=_owner(name);new_owner=moved.get(owner,owner);changed=False
                for relation in root:
                    if relation.get('TargetMode')=='External':continue
                    target=_target(owner,relation.get('Target',''));new_target=moved.get(target,target)
                    if target!=new_target or owner!=new_owner:
                        relation.set('Target',posixpath.relpath(new_target,posixpath.dirname(new_owner) or '.'));changed=True
                if changed:data=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
            entry.filename=destination
            outgoing.writestr(entry,data)
    return {'original_slide_part':part,'working_slide_part':CANONICAL,'renamed':True}
