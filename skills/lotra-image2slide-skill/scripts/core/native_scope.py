"""Dedicated native subtree/resource operations; unrelated package parts retained."""
import copy
import hashlib
import posixpath
from lxml import etree as E
from .mathml import NS

REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


def resources(clone, incoming, parts):
    """Import only relationships actually referenced by this authorized subtree."""
    relpart = 'ppt/slides/_rels/slide1.xml.rels'
    donor = {n.get('Id'): n for n in E.fromstring(incoming.read(relpart))} if relpart in incoming.namelist() else {}
    rels = E.fromstring(parts[relpart]) if relpart in parts else E.Element('{'+REL+'}Relationships')
    types = E.fromstring(parts['[Content_Types].xml'])
    source_types = E.fromstring(incoming.read('[Content_Types].xml'))
    mapping = {}
    for node in clone.iter():
        for attr, rid in list(node.attrib.items()):
            if not attr.startswith('{'+NS['r']+'}'):continue
            if rid not in mapping:
                relationship = donor.get(rid)
                if relationship is None or relationship.get('TargetMode') == 'External':
                    raise ValueError('Scoped native resource requires an internal donor relation')
                source = posixpath.normpath(posixpath.join('ppt/slides', relationship.get('Target', '')))
                if not source.startswith('ppt/media/') or source not in incoming.namelist():
                    raise ValueError('Only self-contained scoped media may be imported')
                data = incoming.read(source); key = hashlib.sha256(data).hexdigest()
                target = 'ppt/media/lotra-scoped-'+key+posixpath.splitext(source)[1]
                if target in parts and parts[target] != data:raise ValueError('Resource identity collision')
                parts[target] = data; link = 'rIdLotraScoped'+key[:24]
                exists = next((n for n in rels if n.get('Id') == link), None)
                relative = posixpath.relpath(target, 'ppt/slides')
                if exists is None:E.SubElement(rels, '{'+REL+'}Relationship', Id=link, Type=relationship.get('Type'), Target=relative)
                elif exists.get('Target') != relative or exists.get('Type') != relationship.get('Type'):
                    raise ValueError('Scoped media relationship collision')
                mime = next((t.get('ContentType') for t in source_types if t.get('PartName') == '/'+source), None)
                mime = mime or next((t.get('ContentType') for t in source_types if t.get('Extension') == source.rsplit('.', 1)[-1]), None)
                if not mime or not mime.startswith('image/'):raise ValueError('A scoped photo must carry image content')
                if not any(t.get('PartName') == '/'+target for t in types):
                    E.SubElement(types, '{'+CT+'}Override', PartName='/'+target, ContentType=mime)
                mapping[rid] = link
            node.set(attr, mapping[rid])
    parts[relpart] = E.tostring(rels, xml_declaration=True, encoding='UTF-8', standalone=True)
    parts['[Content_Types].xml'] = E.tostring(types, xml_declaration=True, encoding='UTF-8', standalone=True)
    return clone


def replace(old, new, old_nodes, new_nodes, allowed, incoming, parts):
    from .native_commit import _nodes, _props
    clone = copy.deepcopy(new); before = _nodes(old); after = _nodes(clone)
    if any(allowed.get(name) not in (['replace_component'], ['remove']) for name in before):
        raise ValueError('Every replaced native descendant needs explicit subtree authority')
    if any(allowed.get(name) not in (['replace_component'], ['add']) for name in after):
        raise ValueError('Every incoming native descendant needs explicit subtree authority')
    next_id = max(int(_props(n).get('id')) for n in old_nodes.values())+1
    identifiers = {}
    for name, node in after.items():
        prior = _props(node).get('id')
        if name in before:current = _props(before[name]).get('id')
        elif name in old_nodes:raise ValueError('Replacement would capture another native owner')
        else:current = str(next_id); next_id += 1
        identifiers[prior] = current; _props(node).set('id', current)
    donor_ids = {_props(n).get('id'): name for name, n in new_nodes.items()}
    for connection in clone.xpath('.//a:stCxn | .//a:endCxn', namespaces=NS):
        prior = connection.get('id')
        if prior in identifiers:connection.set('id', identifiers[prior])
        elif donor_ids.get(prior) in old_nodes:connection.set('id', _props(old_nodes[donor_ids[prior]]).get('id'))
        else:raise ValueError('Replacement connector endpoint is unresolved')
    removed_ids = {_props(n).get('id') for name, n in before.items() if name not in after}
    for name, node in old_nodes.items():
        if name in before:continue
        if any(n.get('id') in removed_ids for n in node.xpath('.//a:stCxn | .//a:endCxn', namespaces=NS)):
            raise ValueError('Repair outside connector endpoints before replacing their removed target')
    resources(clone, incoming, parts)
    parent=new.getparent()
    destination=old_nodes.get(_props(parent).get('name')) if E.QName(parent).localname=='grpSp' else None
    if E.QName(parent).localname=='grpSp' and destination is None:raise ValueError('Scoped replacement parent is absent')
    if destination is not None and old.getparent() is not destination:
        if destination is old or old in destination.iterancestors():raise ValueError('Invalid scoped replacement parent')
        old.getparent().remove(old);destination.append(clone)
    elif E.QName(parent).localname=='spTree' and E.QName(old.getparent()).localname!='spTree':
        tree=old.getroottree().getroot().find('p:cSld/p:spTree',NS)
        old.getparent().remove(old);tree.append(clone)
    else:
        old.getparent().replace(old, clone)
    for name in before:old_nodes.pop(name, None)
    old_nodes.update(_nodes(clone))
    return set(before) | set(after)
