"""Measure named objects from the saved first-slide XML, without Scene answers.

Scene supplies only source-canvas dimensions and expected semantic IDs. Object
geometry, text, formula structure and connection data all come from the PPTX.
Measurements are file evidence, not visual or native-editor acceptance.
"""

import math
import json
from pathlib import Path
import re
from zipfile import ZipFile

from lxml import etree as E

from .common import digest
from .inspect import inventory, parse_math_container, xml
from .mathml import NS

PARSER_VERSION = "saved-object-measure-0.3.0"
IDENTITY = (1., 0., 0., 1., 0., 0.)


def _compose(left, right):
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (a*g+c*h, b*g+d*h, a*i+c*j, b*i+d*j, a*k+c*l+e, b*k+d*l+f)


def _point(matrix, point):
    a, b, c, d, e, f = matrix
    x, y = point
    return [a*x+c*y+e, b*x+d*y+f]


def _translation(x, y):
    return (1., 0., 0., 1., x, y)


def _number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite saved geometry")
    return number


def _transform(node):
    tag = E.QName(node).localname
    path = {"grpSp": "p:grpSpPr/a:xfrm", "graphicFrame": "p:xfrm"}.get(tag, "p:spPr/a:xfrm")
    xf = node.find(path, NS)
    if xf is None:
        raise ValueError("Saved object has no explicit transform; inherited transforms are not inferred")
    off, ext = xf.find("a:off", NS), xf.find("a:ext", NS)
    if off is None or ext is None:
        raise ValueError("Incomplete saved offset/extent")
    x, y, w, h = [_number(v) for v in (off.get("x"), off.get("y"), ext.get("cx"), ext.get("cy"))]
    if w < 0 or h < 0:
        raise ValueError("Negative saved extent")
    angle = _number(xf.get("rot", "0"))/60000
    radians = math.radians(angle)
    cs, sn = math.cos(radians), math.sin(radians)
    rotation = (cs, sn, -sn, cs, 0., 0.)
    flip = (-1. if xf.get("flipH") in ("1", "true", "on") else 1., 0., 0.,
            -1. if xf.get("flipV") in ("1", "true", "on") else 1., 0., 0.)
    centered = _compose(_translation(x+w/2, y+h/2), _compose(rotation, flip))
    local = _compose(centered, _translation(-w/2, -h/2))
    children = None
    if tag == "grpSp":
        coff, cext = xf.find("a:chOff", NS), xf.find("a:chExt", NS)
        if coff is None or cext is None:
            raise ValueError("Group child-coordinate transform is missing")
        cx, cy, cw, ch = [_number(v) for v in (coff.get("x"), coff.get("y"), cext.get("cx"), cext.get("cy"))]
        if cw <= 0 or ch <= 0:
            raise ValueError("Group child-coordinate extent must be positive")
        scale = (w/cw, 0., 0., h/ch, 0., 0.)
        children = _compose(centered, _compose(scale, _translation(-cx-cw/2, -cy-ch/2)))
    return {"bbox": [x, y, w, h], "local": local, "children": children,
            "rotation_degrees": angle, "flip_h": flip[0] == -1, "flip_v": flip[3] == -1}


def _bounds(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)]


def _corners(box):
    x, y, w, h = box
    return [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]


def _selected_children(node):
    """Select actual supported AlternateContent branches inside text bodies."""
    for child in node:
        if child.tag == "{" + NS["mc"] + "}AlternateContent":
            supported = {NS[key] for key in ("a", "p", "m", "a14")}
            selected = next((choice for choice in child.findall("mc:Choice", NS)
                             if choice.get("Requires", "").split() and all(
                                 choice.nsmap.get(key) in supported for key in choice.get("Requires", "").split())), None)
            if selected is None:
                selected = child.find("mc:Fallback", NS)
            if selected is not None:
                yield from _selected_children(selected)
        else:
            yield child


def _text(node):
    body = node.find("p:txBody", NS)
    if body is None:
        return {"text": None, "ast": None, "inline_asts": None}, []
    paragraphs, zones, sequence, errors = [], [], [], []
    ordinary = False
    for paragraph in body.findall("a:p", NS):
        fragments = []
        if paragraphs:
            sequence.append({"kind": "paragraph_break"})
        for child in _selected_children(paragraph):
            if child.tag in ("{"+NS["a"]+"}r", "{"+NS["a"]+"}fld"):
                value = "".join(child.xpath("a:t/text()", namespaces=NS))
                fragments.append(value)
                sequence.append({"kind": "text", "text": value})
                ordinary = True
            elif child.tag == "{"+NS["a"]+"}br":
                fragments.append("\n")
                sequence.append({"kind": "line_break"})
                ordinary = True
            elif child.tag == "{"+NS["a14"]+"}m":
                containers = child.xpath("m:oMath | m:oMathPara/m:oMath", namespaces=NS)
                if not containers:
                    zones.append(None)
                    errors.append("Native math zone lacks a supported math container")
                for container in containers:
                    try:
                        ast = parse_math_container(container)
                    except (ValueError, AttributeError, TypeError, IndexError) as exc:
                        ast = None
                        errors.append("Math parse: " + str(exc))
                    zones.append(ast)
                    sequence.append({"kind": "math", "ast": ast})
        paragraphs.append("".join(fragments))
    return {"text": "\n".join(paragraphs),
            "ast": zones[0] if len(zones) == 1 and not ordinary else None,
            "inline_asts": zones if not errors else None, "content_sequence": sequence}, errors


def _preset_route(preset, width, height):
    """Evaluate the supported native orthogonal preset, retaining saved guides.

    Guide equations/defaults are specified by the DrawingML presets (also
    published in Apache POI's presetShapeDefinitions.xml). This is a numeric
    evaluator; no upstream XML or source code is bundled.
    """
    kind = preset.get("prst")
    if kind in ("line", "straightConnector1"):
        count = 0
    elif kind in ("bentConnector2", "bentConnector3", "bentConnector4", "bentConnector5"):
        count = int(kind[-1])-2
    else:
        raise ValueError("Unsupported saved connector preset: " + str(kind))
    adjustments = {"adj"+str(i): 50000 for i in range(1, count+1)}
    sources = {name: "preset_default" for name in adjustments}
    seen = set()
    for guide in preset.findall("a:avLst/a:gd", NS):
        name = guide.get("name")
        formula = guide.get("fmla", "")
        if name not in adjustments or name in seen:
            raise ValueError("Unknown or duplicate saved connector adjustment")
        match = re.fullmatch(r"\s*val\s+([+-]?\d+)\s*", formula)
        if match is None:
            raise ValueError("Connector measurement supports explicit integer val guides only")
        value = int(match.group(1))
        if not -2147483648 <= value <= 2147483647:
            raise ValueError("Connector adjustment exceeds signed integer range")
        adjustments[name], sources[name] = value, "saved_val"
        seen.add(name)
    if kind in ("line", "straightConnector1"):
        points = [[0., 0.], [width, height]]
    elif kind == "bentConnector2":
        points = [[0., 0.], [width, 0.], [width, height]]
    else:
        x1 = width*adjustments["adj1"]/100000
        if kind == "bentConnector3":
            points = [[0., 0.], [x1, 0.], [x1, height], [width, height]]
        else:
            y2 = height*adjustments["adj2"]/100000
            if kind == "bentConnector4":
                points = [[0., 0.], [x1, 0.], [x1, y2], [width, y2], [width, height]]
            else:
                x3 = width*adjustments["adj3"]/100000
                points = [[0., 0.], [x1, 0.], [x1, y2], [x3, y2], [x3, height], [width, height]]
    return {"endpoints": [points[0], points[-1]], "route_points": points,
            "preset": kind, "adjustments": adjustments, "adjustment_sources": sources}


def _path_geometry(node, width, height):
    """Read saved polyline vertices or curve endpoints; curves are not polylines."""
    paths = node.findall("p:spPr/a:custGeom/a:pathLst/a:path", NS)
    if paths:
        if len(paths) != 1:
            raise ValueError("Multiple custom paths have no single measured endpoint pair")
        path = paths[0]
        pw, ph = _number(path.get("w")), _number(path.get("h"))
        if pw <= 0 or ph <= 0:
            raise ValueError("Custom path coordinate dimensions are missing or invalid")
        first, last, polyline, vertices = None, None, True, []
        for command in path:
            tag = E.QName(command).localname
            points = command.findall("a:pt", NS)
            if tag not in ("moveTo", "lnTo", "cubicBezTo", "quadBezTo") or not points:
                raise ValueError("Unsupported or closed custom connector path")
            if len(points) != {"moveTo": 1, "lnTo": 1, "cubicBezTo": 3, "quadBezTo": 2}[tag]:
                raise ValueError("Invalid point count in saved custom path command")
            if tag == "moveTo":
                if first is not None or len(points) != 1:
                    raise ValueError("Disconnected custom path has no single endpoint pair")
                first = points[0]
            elif first is None:
                raise ValueError("Custom path does not start with moveTo")
            if tag in ("cubicBezTo", "quadBezTo"):
                polyline = False
            vertices.append(points[-1])
            last = points[-1]
        if first is None or last is first:
            raise ValueError("Custom path has fewer than two directed points")
        converted = [[_number(point.get("x"))/pw*width, _number(point.get("y"))/ph*height]
                     for point in vertices]
        return {"endpoints": [converted[0], converted[-1]],
                "route_points": converted if polyline else None, "preset": None,
                "adjustments": None, "adjustment_sources": None}
    preset = node.find("p:spPr/a:prstGeom", NS)
    if preset is not None:
        return _preset_route(preset, width, height)
    raise ValueError("Saved connector lacks a supported explicit geometry")


def measure(scene, pptx):
    """Return an actual_objects receipt in source-pixel coordinates.

    ``bbox`` preserves the object's unrotated saved frame after all ancestor
    transforms; ``visual_bbox`` also applies the object's own rotation/flip.
    Native line/polyline connector ``bbox`` and ``visual_bbox`` instead enclose
    the actual directed route, whose guides may extend outside ``frame_bbox``.
    Zero-area frames stay exact in ``geometry_bbox`` and have ``bbox=None`` so
    consumers do not mistake invented padding for measured geometry.
    """
    pptx = Path(pptx)
    if pptx.stat().st_size > 256*1024*1024:
        raise ValueError("PPTX exceeds file budget")
    before = digest(pptx)
    root = xml(pptx)
    nodes, duplicates = inventory(root)
    if any(not isinstance(name, str) or not name for name in nodes):
        raise ValueError("Saved object lacks a nonempty semantic name")
    width, height = (_number(scene["canvas"][key]) for key in ("width", "height"))
    if width <= 0 or height <= 0:
        raise ValueError("Positive source-canvas dimensions required")
    with ZipFile(pptx) as package:
        presentation = E.fromstring(package.read("ppt/presentation.xml"), E.XMLParser(resolve_entities=False, no_network=True))
    slides = presentation.findall("p:sldIdLst/p:sldId", NS)
    if len(slides) != 1:
        raise ValueError("Object measurement currently requires a single-slide reconstruction")
    size = presentation.find("p:sldSz", NS)
    if size is None:
        raise ValueError("Saved presentation lacks explicit slide dimensions")
    sw, sh = _number(size.get("cx")), _number(size.get("cy"))
    if sw <= 0 or sh <= 0:
        raise ValueError("Saved slide dimensions must be positive")
    canvas = (width/sw, 0., 0., height/sh, 0., 0.)
    transforms, geometries, geometry_errors = {}, {}, {}

    def ancestor(name):
        if name is None:
            return canvas
        if name in transforms:
            return transforms[name]
        if name in duplicates:
            raise ValueError("Ambiguous duplicate group name")
        entry = nodes[name]
        parent = ancestor(entry["parent"])
        geom = geometries.setdefault(name, _transform(entry["node"]))
        if geom["children"] is None:
            raise ValueError("Parent has no group child-coordinate transform")
        transforms[name] = _compose(parent, geom["children"])
        return transforms[name]

    objects = {};contracts={}
    native_ids = {}
    for name, entry in nodes.items():
        native_ids.setdefault(entry["id"], []).append(name)
    for name, entry in nodes.items():
        if name in duplicates:
            continue
        node = entry["node"]
        record = {"bbox": None, "visual_bbox": None, "geometry_bbox": None,
                  "text": None, "ast": None, "inline_asts": None, "endpoints": None,
                  "route_points": None, "route_bbox": None, "frame_bbox": None,
                  "closed_polyline_points": None,
                  "evidence_ref": "ppt/slides/slide1.xml#"+str(name),
                  "native_id": entry["id"], "native_tag": E.QName(node).localname,
                  "parent": entry["parent"], "measurement_errors": []}
        try:
            parent = ancestor(entry["parent"])
            geom = geometries.setdefault(name, _transform(node))
            x, y, w, h = geom["bbox"]
            frame = _bounds([_point(parent, point) for point in _corners(geom["bbox"])])
            local = _compose(parent, geom["local"])
            record.update(geometry_bbox=frame, frame_bbox=frame, raw_bbox_emu=geom["bbox"],
                          bbox=frame if frame[2] > 0 and frame[3] > 0 else None,
                          visual_bbox=_bounds([_point(local, point) for point in _corners([0, 0, w, h])]),
                          rotation_degrees=geom["rotation_degrees"], flip_h=geom["flip_h"], flip_v=geom["flip_v"])
            open_paths=node.findall('p:spPr/a:custGeom/a:pathLst/a:path',NS)
            if (E.QName(node).localname=='sp' and len(open_paths)==1
                    and open_paths[0].find('a:close',NS) is not None):
                outline=open_paths[0];vertices=[];valid=True
                pw,ph=_number(outline.get('w')),_number(outline.get('h'))
                if pw<=0 or ph<=0:valid=False
                for command in outline:
                    tag=E.QName(command).localname
                    if tag=='close':continue
                    points=command.findall('a:pt',NS)
                    if tag not in ('moveTo','lnTo') or len(points)!=1 or (tag=='moveTo' and vertices):valid=False;break
                    vertices.append(points[0])
                if valid and len(vertices)>=3:
                    record['closed_polyline_points']=[_point(local,[_number(p.get('x'))/pw*w,_number(p.get('y'))/ph*h]) for p in vertices]
            is_open_path=(E.QName(node).localname=='sp' and len(open_paths)==1 and open_paths[0].find('a:close',NS) is None)
            if E.QName(node).localname == "cxnSp" or is_open_path:
                route = _path_geometry(node, w, h)
                record["endpoints"] = [_point(local, p) for p in route["endpoints"]]
                record["route_parameters"] = {key: route[key] for key in ("preset", "adjustments", "adjustment_sources")}
                if route["route_points"] is not None:
                    record["route_points"] = [_point(local, p) for p in route["route_points"]]
                    route_box = _bounds(record["route_points"])
                    record.update(route_bbox=route_box, visual_bbox=route_box,
                                  bbox=route_box if route_box[2] > 0 and route_box[3] > 0 else None)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            geometry_errors[name] = str(exc)
            record["measurement_errors"].append(str(exc))
        content, errors = _text(node)
        record.update(content)
        record["measurement_errors"].extend(errors)
        props = node.find(".//p:cNvPr", NS)
        if props is not None and props.get('descr'):
            try:
                marker=json.loads(props.get('descr')).get('sci_rebuild_geometry')
                if marker:contracts[name]=marker
            except (ValueError,AttributeError,TypeError):pass
        hidden = props is not None and props.get("hidden") in ("1", "true", "on")
        current = entry["parent"]
        while current:
            parent_props = nodes[current]["node"].find(".//p:cNvPr", NS)
            hidden |= parent_props is not None and parent_props.get("hidden") in ("1", "true", "on")
            current = nodes[current]["parent"]
        record["hidden"] = bool(hidden)
        if hidden:
            record["saved_text"] = record["text"]
            record.update(text=None, ast=None, inline_asts=None)
            record["measurement_errors"].append("Hidden object or ancestor; native content is not visible evidence")
        if E.QName(node).localname == "cxnSp":
            anchors = {}
            for key, tag in (("source", "stCxn"), ("target", "endCxn")):
                conn = node.find("p:nvCxnSpPr/p:cNvCxnSpPr/a:"+tag, NS)
                if conn is None:
                    anchors[key] = None
                else:
                    names = native_ids.get(conn.get("id"), [])
                    anchors[key] = {"native_id": conn.get("id"), "site": conn.get("idx"),
                                    "object_id": names[0] if len(names) == 1 and names[0] not in duplicates else None}
            record["anchors"] = anchors
            record["arrows"] = {}
            for key, tag in (("start", "headEnd"), ("end", "tailEnd")):
                arrow = node.find("p:spPr/a:ln/a:"+tag, NS)
                record["arrows"][key] = arrow.get("type", "none") if arrow is not None else "none"
        table = node.find("a:graphic/a:graphicData/a:tbl", NS)
        if table is not None:
            from .tables import saved_merges
            record['table_merges']=saved_merges(node,NS)
            record["table_cells"] = [["\n".join("".join(p.xpath(".//a:t/text()", namespaces=NS))
                                               for p in cell.findall("a:txBody/a:p", NS))
                                      for cell in row.findall("a:tc", NS)] for row in table.findall("a:tr", NS)]
        objects[name] = record
    from .geometry import shared_prefix,_on_polyline
    def semantic_tail(record,prefix):
        route=record.get('route_points') or [];stop=prefix[-1]
        for i,(a,b) in enumerate(zip(route,route[1:])):
            if _on_polyline(stop,[a,b],.1):
                points=[stop]+route[i+1:]
                if len(points)>1 and max(abs(x-y) for x,y in zip(points[0],points[1]))<.1:points.pop(0)
                if len(points)<2:raise ValueError('Shared branch has no measured suffix')
                box=_bounds(points)
                record.update(native_route_bbox=record.get('bbox'),semantic_route_points=points,
                              semantic_endpoints=[points[0],points[-1]],semantic_bbox=box,
                              bbox=box if box[2]>0 and box[3]>0 else None,
                              semantic_path_scope='Actual path suffix after the measured shared prefix')
                return
        raise ValueError('Shared prefix does not meet this measured branch')
    for name,contract in contracts.items():
        record=objects[name]
        try:
            if contract.get('version')!=1:raise ValueError('Unknown saved geometry contract version')
            if contract.get('kind')=='shared_trunk':
                members=contract.get('members',[])
                if len(members)<2 or len(set(members))!=len(members) or {key for key,value in nodes.items() if value['parent']==name}!=set(members):
                    raise ValueError('Saved shared-trunk membership changed')
                prefix=shared_prefix([objects[key].get('route_points') for key in members])
                box=_bounds(prefix['points'])
                record.update(group_frame_bbox=record.get('frame_bbox'),route_points=prefix['points'],
                              endpoints=[prefix['points'][0],prefix['points'][-1]],route_bbox=box,
                              bbox=box if box[2]>0 and box[3]>0 else None,visual_bbox=box,
                              shared_prefix_spread_px=prefix['max_spread_px'],geometry_contract=contract)
                for key in members:semantic_tail(objects[key],prefix['points'])
            elif contract.get('kind')=='shared_branch':
                carrier=objects[contract['carrier']]
                prefix=shared_prefix([carrier.get('route_points'),record.get('route_points')])
                semantic_tail(record,prefix['points']);record['geometry_contract']=contract
            else:raise ValueError('Unknown saved geometry contract kind')
        except (ValueError,TypeError,KeyError) as exc:
            record['measurement_errors'].append(str(exc));record['geometry_contract_error']=str(exc)
    if digest(pptx) != before:
        raise ValueError("Saved PPTX changed during measurement")
    expected = {o["id"] for o in scene.get("objects", [])}
    return {"pptx_hash": before, "parser_version": PARSER_VERSION, "objects": objects,
            "canvas": {"width": width, "height": height, "slide_emu": [sw, sh]},
            "missing_ids": sorted(expected-set(objects)), "unexpected_ids": sorted(set(objects)-expected),
            "duplicate_names": sorted(set(duplicates)), "geometry_errors": geometry_errors,
            "scope": "saved_package_measurements_only", "native_edit_roundtrip": "UNVERIFIED",
            "geometry_scope": "Saved transform frames or explicit connector route; excludes stroke, shadows, glyph ink and occlusion",
            "text_scope": "Direct native text; native math is separate; rendering establishes visible glyphs",
            "visible_render_verification": "UNVERIFIED"}
