"""Product-level saved-PPT shape comparison across benign Office serialization.

The comparator reports differences; it does not decide whether an authorized
visual change is good. Unknown or reordered content is conservatively flagged.
"""

import copy
from collections import Counter
import hashlib
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as E
from pptx import Presentation

from .common import digest


def _tag(node):
    return E.QName(node).localname


def _clone(node):
    if node is None:
        return None
    copied = copy.deepcopy(node)
    for part in list(copied.iter()):
        if _tag(part) == "endParaRPr" and not part.attrib and not len(part):
            part.getparent().remove(part)
        elif _tag(part) == "path" and part.get("fill") == "norm":
            # DrawingML's omitted path fill is the same normal-fill default.
            del part.attrib["fill"]
    return copied


def _hash(node):
    return hashlib.sha256(E.tostring(_clone(node), method="c14n") if node is not None else b"").hexdigest()


def _slide_shell(data):
    """Hash slide-level background, timing and metadata outside the shape tree."""
    root = E.fromstring(data)
    for node in root.iter():
        if _tag(node) == "spTree":
            node.getparent().remove(node)
            break
    return _hash(root)


def _package_side_effects(original_pptx, candidate_pptx, allowed_slide_parts):
    """Find changes outside edited slide XML, ignoring only volatile Office metadata.

    An altered part is not interpreted as harmless merely because the named
    shapes still match. XML canonicalization tolerates attribute ordering;
    uncertain side effects withhold PASS for independent review.
    """
    volatile = {"docProps/core.xml", "docProps/app.xml",
                "docProps/thumbnail.jpeg", "ppt/viewProps.xml"}
    with ZipFile(original_pptx) as old, ZipFile(candidate_pptx) as new:
        before, after = set(old.namelist()), set(new.namelist())
        changed = []
        for name in sorted((before | after) - volatile - set(allowed_slide_parts)):
            if name not in before or name not in after:
                changed.append(name)
                continue
            left, right = old.read(name), new.read(name)
            if left == right:
                continue
            if name.endswith((".xml", ".rels")):
                try:
                    if E.tostring(E.fromstring(left), method="c14n") == E.tostring(E.fromstring(right), method="c14n"):
                        continue
                except E.XMLSyntaxError:
                    pass
            changed.append(name)
    return changed


def _one(element, name):
    return next((x for x in element if _tag(x) == name), None)


def _normalized_text(shape_element):
    body = _one(shape_element, "txBody")
    if body is None:
        return {"content": None, "format": None}
    text = "".join(node.text or "" for node in body.iter() if _tag(node) == "t")
    body = _clone(body)
    for node in body.iter():
        if _tag(node) == "t":
            node.text = "__TEXT__"
        elif _tag(node) in ("rPr", "endParaRPr"):
            # PowerPoint adds proofing metadata on edited text and may omit
            # the schema-default false italic flag. Neither changes the
            # displayed glyph style; size, family, color and true style flags
            # remain protected by the hash below.
            for attribute in ("lang", "dirty"):
                node.attrib.pop(attribute, None)
            for attribute in ("b", "i"):
                if node.get(attribute) == "0":
                    del node.attrib[attribute]
    for paragraph in (node for node in body.iter() if _tag(node) == "p"):
        runs = [node for node in paragraph if _tag(node) == "r"]
        ends = [node for node in paragraph if _tag(node) == "endParaRPr"]
        if not runs or len(ends) != 1:
            continue
        run_style = _one(runs[-1], "rPr")
        if run_style is None:
            continue
        # Office writes a trailing-paragraph style when text is edited. It is
        # redundant only when every effective property equals the final run.
        trailing = _clone(ends[0])
        trailing.tag = run_style.tag
        if _hash(trailing) == _hash(run_style):
            paragraph.remove(ends[0])
    return {"content": text, "format": _hash(body)}


def _fill_record(members):
    """Expose solid RGB as one leaf while protecting alpha and fill structure."""
    if len(members) == 1 and _tag(members[0]) == "solidFill":
        colors = [node for node in members[0].iter() if _tag(node) == "srgbClr"]
        if len(colors) == 1 and colors[0].get("val") is not None:
            structure = _clone(members[0])
            next(node for node in structure.iter() if _tag(node) == "srgbClr").set("val", "__COLOR__")
            return _hash(structure), colors[0].get("val").upper()
    raw = b"".join(E.tostring(_clone(item), method="c14n") for item in members)
    return hashlib.sha256(raw).hexdigest(), None


def _shape_record(shape):
    element = shape._element
    kind = _tag(element)
    properties = {"shape_type": kind, "shape_id": shape.shape_id,
                  "bbox.left": int(shape.left), "bbox.top": int(shape.top),
                  "bbox.width": int(shape.width), "bbox.height": int(shape.height),
                  "rotation": int(shape.rotation * 1000), "text_content": None,
                  "text_format": None, "geometry": None, "fill": None, "fill_color": None,
                  "line": None, "effects": None, "other": None, "media_sha256": None,
                  "picture_structure": None}
    properties.update({"text_" + k: v for k, v in _normalized_text(element).items()})
    visual = _one(element, "spPr")
    if visual is None:
        visual = _one(element, "grpSpPr")
    if visual is not None:
        shapes = {"prstGeom", "custGeom", "prstTxWarp"}
        fills = {"solidFill", "noFill", "gradFill", "blipFill", "pattFill", "grpFill"}
        effects = {"effectLst", "effectDag", "scene3d", "sp3d"}
        for key, names in (("geometry", shapes), ("fill", fills), ("line", {"ln"}), ("effects", effects)):
            members = [item for item in visual if _tag(item) in names]
            if key == "fill":
                properties["fill"], properties["fill_color"] = _fill_record(members)
            else:
                properties[key] = hashlib.sha256(b"".join(E.tostring(_clone(item), method="c14n") for item in members)).hexdigest()
    shell = _clone(element)
    if kind == "pic":
        blip = _one(element, "blipFill")
        if blip is not None:
            structural = _clone(blip)
            for item in structural.iter():
                for attribute in list(item.attrib):
                    if E.QName(attribute).localname == "embed":
                        item.set(attribute, "__IMAGE_PART__")
            properties["picture_structure"] = _hash(structural)
    for child in list(shell):
        if _tag(child) in ("spPr", "grpSpPr", "txBody", "blipFill", "sp", "grpSp", "pic", "cxnSp", "graphicFrame"):
            shell.remove(child)
    properties["other"] = _hash(shell)
    if kind == "pic":
        properties["media_sha256"] = hashlib.sha256(shape.image.blob).hexdigest()
        masters=element.xpath('.//*[local-name()="svgBlip" or (local-name()="vectorMaster" and namespace-uri()="https://lotra.ai/ns/vector-master/1")]')
        if masters:
            from .vector_asset import master_bytes
            raw=shape.part.related_part(masters[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")).blob
            data=master_bytes(raw,masters[0].get('compression'),masters[0].get('sha256'))
            properties["svg_sha256"]=hashlib.sha256(data).hexdigest()
    return properties


def snapshot(pptx):
    pptx = Path(pptx)
    prs = Presentation(pptx)
    objects = {}

    def visit(shapes, prefix):
        for shape in shapes:
            key = prefix + "/" + shape.name
            if key in objects:
                raise ValueError("Duplicate saved shape name under one owner: " + key)
            objects[key] = _shape_record(shape)
            if shape.shape_type == 6:
                visit(shape.shapes, key)

    for slide_number, slide in enumerate(prs.slides, 1):
        visit(slide.shapes, "slide-" + str(slide_number))
    shared = {}
    slide_shells = {}
    compatibility = {}
    with ZipFile(pptx) as archive:
        for slide in prs.slides:
            partname = str(slide.part.partname).lstrip("/")
            slide_shells[partname] = _slide_shell(archive.read(partname))
            from .native_markup import variants
            from .inspect import inventory
            logical,duplicates=inventory(E.fromstring(archive.read(partname)))
            if duplicates:raise ValueError('Ambiguous native compatibility owner: '+repr(duplicates))
            compatibility[partname]={name:variants(row['node']) for name,row in logical.items() if variants(row['node'])}
        for name in archive.namelist():
            if name.startswith(("ppt/media/", "ppt/theme/")):
                shared[name] = hashlib.sha256(archive.read(name)).hexdigest()
    return {"pptx_hash": digest(pptx), "objects": objects, "shared_parts": shared,
            "slide_shells": slide_shells,
            "compatibility_variants": compatibility,
            "slide_count": len(prs.slides)}


def _picture_shared_change_allowed(before, after, old_media_hash, new_media_hash):
    theme = lambda parts: {key: value for key, value in parts.items() if key.startswith("ppt/theme/")}
    if theme(before) != theme(after) or old_media_hash == new_media_hash:
        return False
    old_counts = Counter(value for key, value in before.items() if key.startswith("ppt/media/"))
    new_counts = Counter(value for key, value in after.items() if key.startswith("ppt/media/"))
    for media_hash in set(old_counts) | set(new_counts):
        delta = new_counts[media_hash] - old_counts[media_hash]
        if media_hash == old_media_hash:
            if delta not in (-1, 0):
                return False
        elif media_hash == new_media_hash:
            if delta not in (0, 1):
                return False
        elif delta != 0:
            return False
    return new_counts[new_media_hash] >= 1


def compare(baseline, candidate, allowed, *, picture_media_target=None):
    """`allowed` contains exact (saved shape path, product property) pairs."""
    before, after = baseline["objects"], candidate["objects"]
    failures = []
    if baseline["slide_count"] != candidate["slide_count"] or set(before) != set(after):
        failures.append({"scope": "inventory", "reason": "slide/shape name inventory changed"})
    if baseline["slide_shells"] != candidate["slide_shells"]:
        failures.append({"scope": "slide_shells", "reason": "slide background, timing or metadata changed"})
    if baseline.get('compatibility_variants')!=candidate.get('compatibility_variants'):
        failures.append({'scope':'compatibility_variants','reason':'Native Choice/Fallback changed; a scalar local writer cannot certify all math/preview variants'})
    picture_media_ok = False
    if picture_media_target is not None:
        key = picture_media_target
        if key in before and key in after and (key, "media_sha256") in allowed:
            picture_media_ok = _picture_shared_change_allowed(
                baseline["shared_parts"], candidate["shared_parts"],
                before[key]["media_sha256"], after[key]["media_sha256"])
    if baseline["shared_parts"] != candidate["shared_parts"] and not picture_media_ok:
        failures.append({"scope": "shared_parts", "reason": "media or theme asset changed"})
    changed = []
    for key in sorted(set(before) & set(after)):
        for property_name in sorted(set(before[key]) | set(after[key])):
            if before[key].get(property_name) == after[key].get(property_name):
                continue
            item = {"shape": key, "property": property_name,
                    "authorized": (key, property_name) in allowed}
            changed.append(item)
            if not item["authorized"]:
                failures.append({"scope": key + "/" + property_name, "reason": "unapproved saved-PPT product change"})
    return {"status": "FAIL" if failures else "PASS_SAVED_PRODUCT_ONLY",
            "baseline_pptx_hash": baseline["pptx_hash"],
            "candidate_pptx_hash": candidate["pptx_hash"],
            "changed": changed, "failures": failures,
            "scope": "saved shape product properties; visual renderer and Office editing remain separate"}


PRODUCT_MAPPING = {"/bbox/0": "bbox.left", "/bbox/1": "bbox.top",
                   "/bbox/2": "bbox.width", "/bbox/3": "bbox.height",
                   "/content/text": "text_content", "/style/fill": "fill_color",
                   "/style/stroke": "line", "/style/line_width": "line"}


def verify_local_change(original_pptx, candidate_pptx, preparation, *, office_noop_pptx=None):
    """Resolve stable Scene names to saved shapes and check the actual package."""
    old = snapshot(original_pptx)
    if preparation.get("base_pptx_hash") != old["pptx_hash"]:
        raise ValueError("Local edit preparation refers to another saved PPT")
    new = snapshot(candidate_pptx)
    allowed = set()
    unsupported = []
    for write in preparation.get("write_set", []):
        matches = [key for key in old["objects"] if key.split("/")[-1] == write["object_id"]]
        property_name = PRODUCT_MAPPING.get(write["path"])
        if len(matches) != 1:
            raise ValueError("Stable object-to-PPT mapping is missing or ambiguous: " + write["object_id"])
        if property_name is None:
            unsupported.append(write)
        else:
            allowed.add((matches[0], property_name))
    report = compare(old, new, allowed)
    edited_slides = {int(key.split("/", 1)[0].split("-", 1)[1])
                     for key, _ in allowed}
    slide_parts = list(old["slide_shells"])
    allowed_slide_parts = {slide_parts[index - 1] for index in edited_slides
                           if 1 <= index <= len(slide_parts)}
    package_changes = _package_side_effects(original_pptx, candidate_pptx, allowed_slide_parts)
    report["other_package_changes"] = package_changes
    if office_noop_pptx is not None:
        no_op = snapshot(office_noop_pptx)
        control = compare(old, no_op, set())
        extra = _package_side_effects(office_noop_pptx, candidate_pptx, allowed_slide_parts)
        report["office_noop_control"] = {
            "pptx_hash": no_op["pptx_hash"],
            "product_status": control["status"],
            "product_changed": control["changed"],
            "candidate_extra_package_changes": extra,
            "scope": "saved-product control only; host must independently witness the Office no-op operation",
        }
        if control["status"] != "PASS_SAVED_PRODUCT_ONLY":
            report["failures"].append({"scope": "office_noop_control",
                                       "reason": "no-op Office save changed protected product properties"})
            report["status"] = "FAIL"
    unsupported_transitions = []
    for transition in preparation.get("transitions", []):
        property_name = PRODUCT_MAPPING.get(transition["path"])
        if property_name not in ("fill_color", "text_content") and not (property_name or "").startswith("bbox."):
            continue
        matches = [key for key in old["objects"] if key.split("/")[-1] == transition["object_id"]]
        if len(matches) != 1:
            raise ValueError("Stable object-to-PPT mapping is missing or ambiguous")
        key = matches[0]
        if key not in new["objects"]:
            report["failures"].append({"scope": key,
                                       "reason": "authorized target disappeared or was renamed in saved PPT"})
            report["status"] = "FAIL"
            continue
        expected, value = transition["expected"], transition["value"]
        if property_name == "fill_color":
            expected, value = str(expected).lstrip("#").upper(), str(value).lstrip("#").upper()
        elif property_name.startswith("bbox."):
            scale = preparation.get("source_to_emu_scale")
            if not isinstance(scale, (int, float)) or scale <= 0:
                unsupported_transitions.append(transition)
                continue
            expected, value = round(expected * scale), round(value * scale)
        if old["objects"][key][property_name] != expected or new["objects"][key][property_name] != value:
            report["failures"].append({"scope": key + "/" + property_name,
                                       "reason": "saved PPT does not match authorized old/new scalar values"})
            report["status"] = "FAIL"
    report["preparation_hash"] = preparation.get("candidate_scene_hash")
    report["unsupported_native_paths"] = unsupported
    if unsupported_transitions:
        unsupported.extend(unsupported_transitions)
    if report["status"] != "FAIL" and unsupported:
        report["status"] = "UNVERIFIED_UNSUPPORTED_NATIVE_LEAF"
    unexplained_package_changes = (report["office_noop_control"]["candidate_extra_package_changes"]
                                   if office_noop_pptx is not None else package_changes)
    if report["status"] != "FAIL" and unexplained_package_changes:
        report["status"] = "UNVERIFIED_PACKAGE_SIDE_EFFECT"
    if report["status"] != "FAIL" and not any(x["authorized"] for x in report["changed"]):
        report["status"] = "UNVERIFIED_NO_TARGET_EFFECT"
    return report


def verify_local_picture_change(original_pptx, candidate_pptx, request, receipt):
    """Allow one bound picture payload swap, protecting crop, owner and siblings."""
    old, new = snapshot(original_pptx), snapshot(candidate_pptx)
    if request.get("source_pptx_hash") != old["pptx_hash"]:
        raise ValueError("Picture edit request refers to another saved baseline")
    changes = request.get("replacements", [])
    if len(changes) != 1 or len(receipt.get("replacements", [])) != 1:
        raise ValueError("One local picture layer must be checked at a time")
    item = changes[0]
    matches = [key for key, record in old["objects"].items()
               if record["shape_id"] == item["shape_id"] and key.split("/")[-1] == item.get("layer_id")]
    if len(matches) != 1 or not matches[0].startswith("slide-" + str(item.get("slide", 1)) + "/"):
        raise ValueError("Local picture shape ID/name is missing or ambiguous")
    key = matches[0]
    if (receipt.get("source_pptx_hash") != old["pptx_hash"]
            or receipt.get("output_pptx_hash") != new["pptx_hash"]
            or receipt["replacements"][0].get("shape_id") != item["shape_id"]
            or receipt["replacements"][0].get("local_edit_receipt_hash") != item.get("local_edit_receipt_hash")
            or receipt["replacements"][0].get("asset_hash") != item["asset"]["sha256"]):
        raise ValueError("Saved picture, asset and local-edit receipts do not bind")
    report = compare(old, new, {(key, "media_sha256")}, picture_media_target=key)
    if key not in new["objects"]:
        report["failures"].append({"scope": key,
                                   "reason": "authorized picture disappeared or was renamed in saved PPT"})
        report["status"] = "FAIL"
        return report
    if new["objects"][key]["media_sha256"] != item["asset"]["sha256"]:
        report["failures"].append({"scope": key + "/media_sha256",
                                   "reason": "saved picture payload does not match bound asset"})
        report["status"] = "FAIL"
    if report["status"] != "FAIL" and report["changed"] != [
            {"shape": key, "property": "media_sha256", "authorized": True}]:
        report["status"] = "UNVERIFIED_PICTURE_TARGET_EFFECT"
    report["scope"] = "one saved picture payload and all protected saved objects; renderer and Office remain separate"
    return report
