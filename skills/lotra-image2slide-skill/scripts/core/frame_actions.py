"""Finite frame operations on an actual saved PPT; preserve other ZIP data.

The caller supplies existing scoped authority. A plan never grants permission.
This is a saved-native operator for the same runtime, not another draw loop.
"""
import copy
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import numpy as np
from lxml import etree as E
from .common import digest, identity, read_json, safe_path, write_json
from .mathml import NS
from . import frame_plan as fp


def _geometry(entry, body, frame):
    from .boundary_geometry import segments, clip_polygon
    node = entry['node']; original = node.find('p:spPr/a:custGeom', NS)
    if original is None:
        original=node.find('p:spPr/a:prstGeom',NS)
        if original is None or original.get('prst')!='rect':raise ValueError('Saved clipping needs a supported closed native background plane')
    elif len(original.findall('a:pathLst/a:path', NS)) != 1 or len(original.findall('.//a:moveTo', NS)) != 1:
        raise ValueError('Saved clipping requires one explicitly continuous native background plane')
    if original.findall('a:cxnLst/a:cxn', NS):
        raise ValueError('Do not clip a ported scientific/connector owner')
    matrix = body['matrix']; center = (matrix @ np.array([.5, .5, 1.]))[:2]
    vertices, proof = clip_polygon(segments(entry), center, matrix[:2, :2]/2,
                                  frame.get('clip_precision_px', .01), frame.get('clip_inset_px', .02))
    local = (np.c_[vertices, np.ones(len(vertices))] @ np.linalg.inv(entry['matrix']).T)[:, :2]
    geom = E.Element('{'+NS['a']+'}custGeom')
    for key in ('avLst', 'gdLst', 'ahLst', 'cxnLst', 'rect'):
        child = original.find('a:'+key, NS)
        if child is not None:
            geom.append(copy.deepcopy(child))
        elif key != 'rect':
            E.SubElement(geom, '{'+NS['a']+'}'+key)
    paths = E.SubElement(geom, '{'+NS['a']+'}pathLst')
    path = E.SubElement(paths, '{'+NS['a']+'}path', w='1000000', h='1000000')
    for i, point in enumerate(local):
        command = E.SubElement(path, '{'+NS['a']+'}'+('moveTo' if i == 0 else 'lnTo'))
        E.SubElement(command, '{'+NS['a']+'}pt', x=str(round(point[0]*1000000)), y=str(round(point[1]*1000000)))
    E.SubElement(path, '{'+NS['a']+'}close')
    original.getparent().replace(original, geom)
    return proof


def _position(entry, box):
    mapping = entry['parent_matrix']
    if (entry['error'] or not entry['axis_aligned'] or abs(mapping[0, 1])+abs(mapping[1, 0]) > 1e-9
            or min(mapping[0, 0], mapping[1, 1]) <= 0):
        raise ValueError('Grid operator needs a common positive axis-aligned parent; do not guess rotated slots')
    point = np.linalg.inv(mapping) @ np.array([box[0], box[1], 1.])
    xf = entry['node'].find('p:spPr/a:xfrm', NS)
    if xf is None:
        raise ValueError('Grid member needs a native picture/shape frame')
    xf.find('a:off', NS).set('x', str(round(point[0])))
    xf.find('a:off', NS).set('y', str(round(point[1])))
    xf.find('a:ext', NS).set('cx', str(round(box[2]/mapping[0, 0])))
    xf.find('a:ext', NS).set('cy', str(round(box[3]/mapping[1, 1])))


def apply(plan, base, baseline, output, size, request):
    """Execute only geometry/frame/media changes explicitly granted by caller."""
    fp.validate(plan, base)
    baseline, output = Path(baseline), Path(output)
    if baseline.resolve() == output.resolve() or digest(baseline) != request.get('expected_baseline_sha256'):
        raise ValueError('Bind the actual unchanged baseline and a separate candidate')
    grants = request.get('allowed_changes', {})
    if not grants or not set(grants) <= set(plan['scope']):
        raise ValueError('Explicit frame leaf authority within frozen scope required')
    finite = {'geometry', 'bbox.left', 'bbox.top', 'bbox.width', 'bbox.height', 'media', 'replace_component'}
    if any(not fields or not set(fields) <= finite for fields in grants.values()):
        raise ValueError('Unknown/broad frame operation grant')
    receipt_path = output.with_suffix('.frame-action.json'); action = identity({'plan': plan, 'request': request})
    if output.exists():
        if receipt_path.exists():
            prior = read_json(receipt_path)
            if prior.get('action') == action and prior.get('pptx_sha256') == digest(output):
                return prior
        raise FileExistsError('Preserve different/unverified candidate: '+str(output))
    from .boundary_geometry import saved_nodes
    from .content_viewport import normalize
    nodes = saved_nodes(baseline, size)
    if not set(plan['scope']) <= set(nodes):
        raise ValueError('Saved frame plan has missing/ambiguous owners')
    before = {name: E.tostring(entry['node']) for name, entry in nodes.items()}
    with ZipFile(baseline) as archive:
        payload = {info.filename: archive.read(info.filename) for info in archive.infolist()}
        infos = {info.filename: info for info in archive.infolist()}
    tree = next(iter(nodes.values()))['node'].getroottree().getroot()
    rels = E.fromstring(payload['ppt/slides/_rels/slide1.xml.rels'])
    types = E.fromstring(payload['[Content_Types].xml'])
    changes = []; added = {}
    def permit(name, fields):
        allowed = set(grants.get(name, []))
        if 'replace_component' not in allowed and not set(fields) <= allowed:
            raise ValueError('Frame operation exceeds frozen leaf authority: '+name+' '+repr(fields))
    def relationship(path):
        target = '../media/'+Path(path).name
        for rel in rels:
            if rel.get('Target') == target and rel.get('Type', '').endswith('/image'):
                return rel.get('Id')
        existing = {r.get('Id') for r in rels}; number = 1
        while 'rId'+str(number) in existing:
            number += 1
        rid = 'rId'+str(number)
        E.SubElement(rels, '{'+fp.REL_NS+'}Relationship', Id=rid, Type=fp.R_NS+'/image', Target=target)
        return rid
    def media(path, extension, content_type):
        data = Path(path).read_bytes(); sha = hashlib.sha256(data).hexdigest()
        name = 'ppt/media/lotra-content-'+sha+'.'+extension
        if name in payload and payload[name] != data:
            raise ValueError('Media identity collision')
        added[name] = data
        namespace = '{http://schemas.openxmlformats.org/package/2006/content-types}'
        if not any(e.get('Extension') == extension for e in types):
            E.SubElement(types, namespace+'Default', Extension=extension, ContentType=content_type)
        return relationship(name)
    for frame in plan['frames']:
        if frame['kind'] == 'container':
            body = nodes[frame['body']]
            if body['frame'] is None or max(abs(a-b) for a, b in zip(body['frame'], frame['bbox'])) > frame.get('tolerance_px', .01):
                raise ValueError('Actual container differs from the frozen frame; revise source evidence explicitly')
            preset = body['node'].find('p:spPr/a:prstGeom', NS)
            if preset is None or preset.get('prst') != 'ellipse':
                raise ValueError('Saved clip requires the actual ellipse body')
            for member in frame['members']:
                if member['operation'] == 'clip_fill':
                    name = member['object']
                    if name not in grants:continue
                    permit(name, ['geometry'])
                    proof = _geometry(nodes[name], body, frame)
                    changes.append({'object': name, 'fields': ['geometry'], 'proof': proof})
            continue
        if frame['kind'] == 'native_table':
            from .table_slots import boxes as table_boxes
            members=frame['members'];boxes=table_boxes(frame,nodes)
        elif frame['kind'] == 'grid':
            # Quantize boundaries in the actual shared parent's integer grid.
            members = frame['members']; matrices = [nodes[m['object']]['parent_matrix'] for m in members]
            if any(not np.allclose(matrices[0], m, atol=1e-12, rtol=0) for m in matrices[1:]):
                raise ValueError('Grid members must share actual parent coordinates')
            matrix = matrices[0]; local_frame = copy.deepcopy(frame)
            origin = np.linalg.inv(matrix) @ np.array([*frame['bbox'][:2], 1.])
            local_frame['bbox'] = [origin[0], origin[1], frame['bbox'][2]/matrix[0, 0], frame['bbox'][3]/matrix[1, 1]]
            local_frame['gap'] = [frame.get('gap', [0, 0])[0]/matrix[0, 0], frame.get('gap', [0, 0])[1]/matrix[1, 1]]
            local_boxes = fp.grid_boxes(local_frame)
            boxes = {name: [matrix[0, 0]*b[0]+matrix[0, 2], matrix[1, 1]*b[1]+matrix[1, 2], matrix[0, 0]*b[2], matrix[1, 1]*b[3]] for name, b in local_boxes.items()}
        else:
            members = [{'object': frame['object'], 'content_window': frame.get('content_window')}]
            boxes = {frame['object']: frame['bbox']}
        for member in members:
            name = member['object']; entry = nodes[name]; box = boxes[name]
            if name not in grants:continue
            fields = ['bbox.left', 'bbox.top', 'bbox.width', 'bbox.height']; permit(name, fields)
            _position(entry, box); changed = {'object': name, 'fields': fields}
            if member.get('content_window'):
                permit(name, ['media'])
                if entry['tag'] != 'pic':
                    raise ValueError('Semantic media window needs an actual independent picture')
                window = member['content_window']
                normalized = normalize(fp.window_content(window), window['render_type'], window, box, base)
                blip = entry['node'].find('.//a:blip', NS)
                if blip is None:
                    raise ValueError('Missing saved picture blip')
                # Both native SVG and compressed paper-export masters are
                # media authorities. Replacement must retain one coherent
                # normalized artwork in every downstream consumer.
                for master in list(entry['node'].findall('.//{'+fp.MASTER_NS+'}vectorMaster')):
                    parent = master.getparent(); parent.remove(master)
                    if not len(parent): parent.getparent().remove(parent)
                if window['render_type'] == 'svg':
                    rid = media(safe_path(base, normalized['path']), 'svg', 'image/svg+xml')
                    preview = normalized['preview']
                    preview_rid = media(safe_path(base, preview['path']), 'png', 'image/png')
                    vector = blip.find('.//{'+fp.ASVG_NS+'}svgBlip')
                    if vector is None:
                        extlst = blip.find('a:extLst', NS)
                        if extlst is None:
                            extlst = E.SubElement(blip, '{'+NS['a']+'}extLst')
                        ext = E.SubElement(extlst, '{'+NS['a']+'}ext', uri='{96DAC541-7B7A-43D3-8B79-37D633B846F1}')
                        vector = E.SubElement(ext, '{'+fp.ASVG_NS+'}svgBlip', nsmap={'asvg': fp.ASVG_NS})
                    vector.set('{'+fp.R_NS+'}embed', rid); blip.set('{'+fp.R_NS+'}embed', preview_rid)
                else:
                    blip.set('{'+fp.R_NS+'}embed', media(safe_path(base, normalized['path']), 'png', 'image/png'))
                    # Office gives SVG authority to svgBlip when present.
                    # A photo replacement must not retain that old artwork.
                    for vector in list(blip.findall('.//{'+fp.ASVG_NS+'}svgBlip')):
                        parent = vector.getparent(); parent.remove(vector)
                        if not len(parent): parent.getparent().remove(parent)
                    extlst = blip.find('a:extLst', NS)
                    if extlst is not None and not len(extlst): blip.remove(extlst)
                rect = entry['node'].find('p:blipFill/a:srcRect', NS)
                if rect is None:
                    fill = entry['node'].find('p:blipFill', NS)
                    rect = E.Element('{'+NS['a']+'}srcRect'); fill.insert(1, rect)
                for key, value in zip(('l', 't', 'r', 'b'), normalized['viewport']['native_crop']):
                    rect.set(key, str(round(value*100000)))
                changed.update(fields=fields+['media'], normalized_media_sha256=normalized['sha256'], semantic_window=window['window'])
            changes.append(changed)
    # The program can only have touched named leaves. Ancestor serialization
    # changes are expected; their own native properties remain protected.
    changed_names = {c['object'] for c in changes}
    unauthorized = []
    for name, entry in nodes.items():
        if name in changed_names:
            after=copy.deepcopy(entry['node']);old=E.fromstring(before[name])
            fields={f for c in changes if c['object']==name for f in c['fields']}
            for node in (old,after):
                if 'geometry' in fields:
                    for geometry in node.findall('p:spPr/a:custGeom',NS)+node.findall('p:spPr/a:prstGeom',NS):
                        geometry.getparent().remove(geometry)
                xf=node.find('p:spPr/a:xfrm',NS)
                if xf is not None:
                    for field,key,attribute in [('bbox.left','off','x'),('bbox.top','off','y'),('bbox.width','ext','cx'),('bbox.height','ext','cy')]:
                        if field in fields:xf.find('a:'+key,NS).attrib.pop(attribute,None)
                if 'media' in fields:
                    for blip in node.findall('.//a:blip',NS):
                        blip.attrib.pop('{'+fp.R_NS+'}embed',None)
                        for vector in blip.findall('.//{'+fp.ASVG_NS+'}svgBlip'):
                            parent=vector.getparent();parent.remove(vector)
                            if not len(parent):parent.getparent().remove(parent)
                        extlst=blip.find('a:extLst',NS)
                        if extlst is not None and not len(extlst):blip.remove(extlst)
                    for master in list(node.findall('.//{'+fp.MASTER_NS+'}vectorMaster')):
                        parent=master.getparent(); parent.remove(master)
                        if not len(parent): parent.getparent().remove(parent)
                    for extlst in list(node.findall('.//a:extLst',NS)):
                        if not len(extlst):extlst.getparent().remove(extlst)
                    for rect in node.findall('p:blipFill/a:srcRect',NS):rect.getparent().remove(rect)
            if E.tostring(old,method='c14n',exclusive=True,with_tail=False)!=E.tostring(after,method='c14n',exclusive=True,with_tail=False):
                unauthorized.append(name+':protected_target_properties')
            continue
        if entry['tag'] == 'grpSp':
            node = copy.deepcopy(entry['node'])
            for child in list(node):
                if E.QName(child).localname in ('sp', 'grpSp', 'pic', 'cxnSp', 'graphicFrame'):
                    node.remove(child)
            old = E.fromstring(before[name])
            for child in list(old):
                if E.QName(child).localname in ('sp', 'grpSp', 'pic', 'cxnSp', 'graphicFrame'):
                    old.remove(child)
            equal = E.tostring(node,method='c14n',exclusive=True,with_tail=False) == E.tostring(old,method='c14n',exclusive=True,with_tail=False)
        else:
            equal = E.tostring(entry['node']) == before[name]
        if not equal:
            unauthorized.append(name)
    if unauthorized:
        raise ValueError('Unexpected non-target native changes: '+repr(unauthorized))
    updated = {'ppt/slides/slide1.xml': E.tostring(tree, encoding='UTF-8', xml_declaration=True, standalone=True)}
    if added:
        updated.update({'ppt/slides/_rels/slide1.xml.rels': E.tostring(rels, encoding='UTF-8', xml_declaration=True, standalone=True),
                        '[Content_Types].xml': E.tostring(types, encoding='UTF-8', xml_declaration=True, standalone=True)})
    payload.update(updated); payload.update(added)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream, ZipFile(stream, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in payload.items():
            archive.writestr(infos[name] if name in infos else name, data, compress_type=ZIP_DEFLATED, compresslevel=9)
    if digest(baseline) != request['expected_baseline_sha256']:
        raise ValueError('Baseline changed while executing; do not adopt candidate')
    checked = fp.check(plan, base, output, size)
    result = {'schema': 'frame-action-1', 'action': action, 'status': 'SAVED_CHECKED' if checked['passed'] else 'SAVED_REQUIRES_REPAIR',
              'baseline_sha256': request['expected_baseline_sha256'], 'pptx_sha256': digest(output), 'changes': changes,
              'non_target_native_changes': unauthorized, 'new_resources': {n: hashlib.sha256(b).hexdigest() for n, b in added.items()},
              'saved_check': checked, 'limits': 'Actual host rendering/semantic review/protection and final adoption remain required.'}
    write_json(receipt_path, result)
    return result
