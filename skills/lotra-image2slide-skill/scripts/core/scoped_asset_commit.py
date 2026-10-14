"""Replace one declared artwork subtree without reserializing protected parts."""
import copy,posixpath,hashlib
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .mathml import NS
from .common import digest,write_json
R='{'+NS['r']+'}'
P='{'+NS['p']+'}'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
TYPES={'sp','grpSp','pic','cxnSp'}

def _nodes(tree):
    result={}
    for e in tree.iter():
        if E.QName(e).localname not in TYPES:continue
        p=e.find('.//p:cNvPr',NS)
        if p is not None:result[p.get('name')]=e
    return result

def merge(baseline,donor,allowed,output,_legacy_order=None):
    targets=sorted(key for key,fields in allowed.items() if fields==['replace_component'])
    if _legacy_order is not None:
        if len(_legacy_order)!=len(targets) or set(_legacy_order)!=set(targets):raise ValueError('Legacy constructor order must cover exactly the frozen targets')
        targets=list(_legacy_order)
    if not targets or len(targets)!=len(allowed):
        raise ValueError('Component replacement cannot be mixed with unrelated field grants')
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    slide='ppt/slides/slide1.xml';rels='ppt/slides/_rels/slide1.xml.rels'
    with ZipFile(baseline) as base,ZipFile(donor) as inc:
        old=E.fromstring(base.read(slide));new=E.fromstring(inc.read(slide))
        oldnodes,newnodes=_nodes(old),_nodes(new)
        oldrels=E.fromstring(base.read(rels));incoming=E.fromstring(inc.read(rels))
        typexml=E.fromstring(base.read('[Content_Types].xml'))
        types=E.fromstring(inc.read('[Content_Types].xml'))
        newparts={};copied={};receipts=[];retired_rids=set()
        # A replacement can retain an unchanged material/mother already used
        # by another owner. Reuse its actual relationship, rather than append
        # the same content-addressed rId twice (Office cannot open that slide).
        from .vector_asset import MASTER_REL
        for relation in oldrels:
            kind=relation.get('Type','')
            if relation.get('TargetMode')=='External' or not (kind.endswith('/image') or kind==MASTER_REL):continue
            path=posixpath.normpath(posixpath.join('ppt/slides',relation.get('Target')))
            if path in base.namelist():
                copied.setdefault((hashlib.sha256(base.read(path)).hexdigest(),kind),relation.get('Id'))
        nextid=max(int(n.find('.//p:cNvPr',NS).get('id')) for n in oldnodes.values())+1
        for target in targets:
            if target not in oldnodes or target not in newnodes:raise ValueError('Actual component root missing')
            before,after=oldnodes[target],newnodes[target]
            retired_rids.update(value for node in before.iter() for key,value in node.attrib.items() if key.startswith(R))
            forbidden=before.xpath('.//a:t | .//a14:m',namespaces=NS)
            if forbidden:raise ValueError('Text/math cannot be flattened as an artwork replacement')
            # A replacement does not authorize breaking external scientific links.
            removed={n.find('.//p:cNvPr',NS).get('id') for n in _nodes(before).values()}
            rootid=before.find('.//p:cNvPr',NS).get('id')
            # Immutable derived connection sites survive an anatomy repair.
            # Retain their complete old XML/ID, not a regenerated placeholder.
            # Ordinary referenced children still need an explicit redock.
            from .native_connection_transaction import anchor_metadata
            retained_ports={}
            for name,node in _nodes(before).items():
                meta=anchor_metadata(node)
                if not meta:continue
                proposed=_nodes(after).get(name)
                if (meta.get('kind')!='program_connection_port' or proposed is None
                        or node.find('p:spPr/a:noFill',NS) is None or node.find('p:spPr/a:ln/a:noFill',NS) is None):
                    raise ValueError('Derived connection port requires its complete unchanged owner')
                oldxf=node.find('p:spPr/a:xfrm',NS);newxf=proposed.find('p:spPr/a:xfrm',NS)
                if oldxf is None or newxf is None or E.tostring(oldxf)!=E.tostring(newxf):
                    raise ValueError('Anatomy repair cannot move an existing connection port; redock explicitly')
                if proposed.find('p:spPr/a:noFill',NS) is None or proposed.find('p:spPr/a:ln/a:noFill',NS) is None:
                    raise ValueError('Anatomy donor cannot paint a derived connection port')
                retained_ports[name]=node
            retained_ids={n.find('p:nvSpPr/p:cNvPr',NS).get('id') for n in retained_ports.values()}
            for conn in old.xpath('.//a:stCxn | .//a:endCxn',namespaces=NS):
                if conn.get('id') in removed-{rootid}-retained_ids and conn not in set(before.iter()):
                    raise ValueError('External link depends on a removed child; repair its endpoint explicitly')
            clone=copy.deepcopy(after)
            if E.QName(before).localname=='grpSp' and E.QName(clone).localname=='grpSp':
                oldframe=before.find('./p:grpSpPr/a:xfrm',NS);newframe=clone.find('./p:grpSpPr/a:xfrm',NS)
                if oldframe is None or newframe is None:raise ValueError('Native artwork group needs an explicit ancestor frame')
                def affine(frame):
                    from fractions import Fraction
                    if dict(frame.attrib):return None
                    off=frame.find('a:off',NS);ext=frame.find('a:ext',NS);co=frame.find('a:chOff',NS);ce=frame.find('a:chExt',NS)
                    scales=[Fraction(int(ext.get(k)),int(ce.get(k))) for k in ('cx','cy')]
                    shifts=[Fraction(int(off.get(k)))-scales[i]*int(co.get(k)) for i,k in enumerate(('x','y'))]
                    return scales,shifts
                if E.tostring(oldframe)!=E.tostring(newframe):
                    original,proposed=affine(oldframe),affine(newframe)
                    if original is None or original!=proposed:
                        raise ValueError('Artwork replacement cannot change its existing native ancestor coordinate mapping; use a source-scoped transform repair')
                    # Even equivalent identity mappings with different group
                    # extents can change Office's SVG sampling grid. Preserve
                    # the actual old renderer frame, not just the scene bbox.
                    newframe.getparent().replace(newframe,copy.deepcopy(oldframe))
            idmap={after.find('.//p:cNvPr',NS).get('id'):rootid}
            for node in _nodes(clone).values():
                props=node.find('.//p:cNvPr',NS);sid=props.get('id')
                name=props.get('name')
                if name in retained_ports:idmap[sid]=retained_ports[name].find('p:nvSpPr/p:cNvPr',NS).get('id')
                elif sid not in idmap:idmap[sid]=str(nextid);nextid+=1
                props.set('id',idmap[sid])
            for conn in clone.xpath('.//a:stCxn | .//a:endCxn',namespaces=NS):
                if conn.get('id') not in idmap:raise ValueError('Imported artwork has an external link')
                conn.set('id',idmap[conn.get('id')])
            for node in clone.iter():
                for key,value in list(node.attrib.items()):
                    if not key.startswith(R):continue
                    relation=next((r for r in incoming if r.get('Id')==value),None)
                    from .vector_asset import MASTER_REL,master_bytes
                    if (relation is None or relation.get('TargetMode')=='External'
                            or not (relation.get('Type','').endswith('/image') or relation.get('Type')==MASTER_REL)):
                        raise ValueError('Only owned static image or explicit vector-master resources may be imported')
                    path=posixpath.normpath(posixpath.join('ppt/slides',relation.get('Target')))
                    if path.startswith('../') or path not in inc.namelist():raise ValueError('Image relation outside package')
                    data=inc.read(path);sha=hashlib.sha256(data).hexdigest()
                    if relation.get('Type')==MASTER_REL:
                        master_bytes(data,node.get('compression'),node.get('sha256'))
                    resource_key=(sha,relation.get('Type'))
                    if resource_key not in copied:
                        suffix=Path(path).suffix;dest='ppt/media/lotra-'+sha+suffix
                        if dest not in base.namelist():newparts[dest]=data
                        stem='rIdLotra'+sha[:20];rid=stem;counter=0
                        existing_ids={r.get('Id') for r in oldrels}
                        while rid in existing_ids:
                            counter+=1;rid=stem+'_'+str(counter)
                        E.SubElement(oldrels,'{'+REL+'}Relationship',Id=rid,Type=relation.get('Type'),Target='../media/'+Path(dest).name)
                        copied[resource_key]=rid
                        ctype=next((r.get('ContentType') for r in types if r.get('PartName')=='/'+path),None)
                        if ctype is None:ctype=next((r.get('ContentType') for r in types if r.get('Extension')==suffix.lstrip('.')),None)
                        if not ctype:raise ValueError('Imported artwork content type missing')
                        if not any(r.get('PartName')=='/'+dest for r in typexml):
                            E.SubElement(typexml,'{'+CT+'}Override',PartName='/'+dest,ContentType=ctype)
                    node.set(key,copied[resource_key])
            for name,port in retained_ports.items():
                carrier=_nodes(clone)[name];carrier.getparent().replace(carrier,copy.deepcopy(port))
            before.getparent().replace(before,clone)
            receipts.append({'owner':target,'before':hashlib.sha256(E.tostring(before)).hexdigest(),'after':hashlib.sha256(E.tostring(clone)).hexdigest()})
        # Remove only resources retired by the explicitly replaced artwork.
        # Any current slide/XML relationship keeps the corresponding payload.
        live_rids={value for node in old.iter() for key,value in node.attrib.items() if key.startswith(R)}
        retired_paths=set()
        for relation in list(oldrels):
            if (relation.get('Id') in retired_rids-live_rids and relation.get('TargetMode')!='External'
                    and (relation.get('Type','').endswith('/image') or relation.get('Type')==MASTER_REL)):
                retired_paths.add(posixpath.normpath(posixpath.join('ppt/slides',relation.get('Target'))))
                oldrels.remove(relation)
        inbound=set()
        for name in base.namelist():
            if not name.endswith('.rels'):continue
            relationships=oldrels if name==rels else E.fromstring(base.read(name))
            origin=posixpath.dirname(posixpath.dirname(name))
            for relation in relationships:
                if relation.get('TargetMode')!='External':
                    inbound.add(posixpath.normpath(posixpath.join(origin,relation.get('Target'))))
        retired_parts=retired_paths-inbound-set(newparts)
        for entry in list(typexml):
            if entry.get('PartName','').lstrip('/') in retired_parts:typexml.remove(entry)
        replacement={slide:E.tostring(old,xml_declaration=True,encoding='UTF-8',standalone=True),rels:E.tostring(oldrels,xml_declaration=True,encoding='UTF-8',standalone=True),'[Content_Types].xml':E.tostring(typexml,xml_declaration=True,encoding='UTF-8',standalone=True)}
        with ZipFile(output,'w',compression=ZIP_DEFLATED) as dst:
            for info in base.infolist():
                if info.filename not in retired_parts:dst.writestr(info,replacement.get(info.filename,base.read(info.filename)))
            for name,data in newparts.items():dst.writestr(name,data)
    result={'source_sha256':digest(baseline),'output_sha256':digest(output),'owners':receipts,'imported_resources':list(newparts),'retired_unreferenced_owned_resources':sorted(retired_parts),'protection':'all current/unrelated ZIP parts and shape subtrees inherited; only replaced-owned resources without remaining inbound references retired'}
    write_json(output.with_suffix('.component-commit.json'),result)
    return result
