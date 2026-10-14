"""Patch an existing PPTX's named native leaves without rebuilding the page.

Only unambiguous, one-run text and solid RGB fills are supported here. Other
edits must take a separate route and pass the same saved-product protection.
The source file is never modified, including when verification fails.
"""

import os
from pathlib import Path
import tempfile
from zipfile import ZipFile

from lxml import etree as E
from pptx import Presentation

from .common import digest, identity, read_json
from .saved_ppt_diff import _tag, snapshot, verify_local_change


def _named_shapes(tree, slide_index):
    result = {}
    slide = next((x for x in tree.iter() if _tag(x) == "spTree"), None)
    if slide is None:
        raise ValueError("Slide has no native shape tree")

    def visit(parent, prefix):
        from .native_markup import active_children,variants
        for child in active_children(parent):
            if _tag(child) not in {"sp", "grpSp", "pic", "cxnSp", "graphicFrame"}:
                continue
            marker = next((x for x in child.iter() if _tag(x) == "cNvPr"), None)
            if marker is None or not marker.get("name") or "/" in marker.get("name"):
                raise ValueError("Native shape lacks an unambiguous stable name")
            key = prefix + "/" + marker.get("name")
            if key in result:
                raise ValueError("Duplicate native shape path: " + key)
            result[key] = child
            if _tag(child) == "grpSp":
                visit(child, key)

    visit(slide, "slide-" + str(slide_index))
    return result


def _replace_scalar(element, transition, scale):
    from .native_markup import variants
    if variants(element):
        raise ValueError('Compatibility math requires the complete native math/variant writer; a scalar leaf patch cannot refresh its fallback')
    path = transition["path"]
    if path == "/style/fill":
        visual = next((x for x in element if _tag(x) == "spPr"), None)
        fills = [] if visual is None else [x for x in visual if _tag(x) in {
            "solidFill", "gradFill", "noFill", "pattFill", "blipFill", "grpFill"}]
        if len(fills) != 1 or _tag(fills[0]) != "solidFill":
            raise ValueError("Native fill edit needs exactly one solid RGB fill")
        colors = [x for x in fills[0].iter() if _tag(x) == "srgbClr"]
        if len(colors) != 1:
            raise ValueError("Native fill edit cannot replace theme/gradient color")
        old, new = [str(transition[key]).lstrip("#").upper() for key in ("expected", "value")]
        if any(len(item) != 6 or any(c not in "0123456789ABCDEF" for c in item) for item in (old, new)):
            raise ValueError("Native fill edit requires six-digit RGB colors")
        if colors[0].get("val", "").upper() != old:
            raise ValueError("Saved PPT color no longer matches the approved old value")
        colors[0].set("val", new)
    elif path == "/content/text":
        body = next((x for x in element if _tag(x) == "txBody"), None)
        runs = [] if body is None else [x for x in body.iter() if _tag(x) == "t"]
        if len(runs) != 1 or runs[0].text != transition["expected"]:
            raise ValueError("Native text edit requires one exact old-value run")
        if not isinstance(transition["value"], str):
            raise ValueError("Native text edit requires a string")
        runs[0].text = transition["value"]
    elif path in {"/bbox/0", "/bbox/1", "/bbox/2", "/bbox/3"}:
        if _tag(element) not in {"sp", "cxnSp"}:
            raise ValueError("Native bbox leaf patch does not alter parent group transforms or pictures")
        visual = next((x for x in element if _tag(x) == "spPr"), None)
        xfrm = None if visual is None else next((x for x in visual if _tag(x) == "xfrm"), None)
        off = None if xfrm is None else next((x for x in xfrm if _tag(x) == "off"), None)
        ext = None if xfrm is None else next((x for x in xfrm if _tag(x) == "ext"), None)
        slot = {"/bbox/0": (off, "x"), "/bbox/1": (off, "y"),
                "/bbox/2": (ext, "cx"), "/bbox/3": (ext, "cy")}[path]
        node, attribute = slot
        if node is None or not isinstance(transition["expected"], (int, float)) or not isinstance(transition["value"], (int, float)):
            raise ValueError("Native bbox leaf needs an existing numeric transform")
        old, new = round(transition["expected"] * scale), round(transition["value"] * scale)
        if int(node.get(attribute)) != old or (path in {"/bbox/2", "/bbox/3"} and new <= 0):
            raise ValueError("Saved PPT geometry no longer matches approved old value")
        node.set(attribute, str(new))
    else:
        raise ValueError("Unsupported native leaf route: " + str(path))


def patch_native_ppt(baseline_pptx, candidate_scene, preparation, output):
    """Write a task-local candidate then compare its actual saved properties."""
    baseline_pptx, candidate_scene, output = map(Path, (baseline_pptx, candidate_scene, output))
    if output.exists() or output.resolve() == baseline_pptx.resolve():
        raise ValueError("Native patch needs a new candidate path; source stays untouched")
    if preparation.get("schema_version") != "local-edit-preparation-1":
        raise ValueError("Native patch requires a prepared leaf-edit contract")
    if preparation.get("base_pptx_hash") != digest(baseline_pptx):
        raise ValueError("Existing PowerPoint changed since the local edit was prepared")
    scene = read_json(candidate_scene)
    if preparation.get("candidate_scene_hash") != identity(scene):
        raise ValueError("Native patch candidate Scene differs from the prepared edit")
    transitions = preparation.get("transitions") or []
    writes = {(x["object_id"], x["path"]) for x in preparation.get("write_set", [])}
    if not transitions or writes != {(x["object_id"], x["path"]) for x in transitions}:
        raise ValueError("Native patch requires all exact old/new leaf transitions")
    if len(writes) != len(transitions):
        raise ValueError("Duplicate native edit target")
    scale = preparation.get("source_to_emu_scale")
    if any(x["path"].startswith("/bbox/") for x in transitions):
        expected_scale = Presentation(baseline_pptx).slide_width / scene["canvas"]["width"]
        if not isinstance(scale, (int, float)) or scale != expected_scale:
            raise ValueError("Native bbox patch has a stale canvas transform")
        by_id = {item["id"]: item for item in scene["objects"]}
        for transition in transitions:
            if not transition["path"].startswith("/bbox/"):
                continue
            node = by_id[transition["object_id"]]
            if any(item["render_type"] == "connector" and transition["object_id"] in
                   (item["content"].get("source"), item["content"].get("target"))
                   for item in scene["objects"]):
                raise ValueError("Connected node move requires an explicit connector and Office route")
            parent = by_id.get(node.get("parent"))
            if parent:
                x, y, w, h = node["bbox"]
                px, py, pw, ph = parent["bbox"]
                if x < px or y < py or x+w > px+pw or y+h > py+ph:
                    raise ValueError("Child move would alter parent extent; separate structural edit required")
    old = snapshot(baseline_pptx)
    prs = Presentation(baseline_pptx)
    slide_parts = [str(slide.part.partname).lstrip("/") for slide in prs.slides]
    replacements = {}
    with ZipFile(baseline_pptx) as archive:
        for index, partname in enumerate(slide_parts, 1):
            replacements[partname] = (E.fromstring(archive.read(partname)), index)
        native = {}
        for partname, (tree, index) in replacements.items():
            for key, element in _named_shapes(tree, index).items():
                if key in native:
                    raise ValueError("Duplicate native object identity")
                native[key] = element
        if set(native) != set(old["objects"]):
            raise ValueError("Saved native shape mapping changed unexpectedly")
        for transition in transitions:
            matches = [key for key in native if key.split("/")[-1] == transition["object_id"]]
            if len(matches) != 1:
                raise ValueError("Native object identity missing or ambiguous")
            _replace_scalar(native[matches[0]], transition, scale)
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="." + output.name + "-", suffix=".pptx", dir=output.parent)
        os.close(fd)
        try:
            with ZipFile(temporary, "w") as target:
                for item in archive.infolist():
                    data = (E.tostring(replacements[item.filename][0], encoding="UTF-8", xml_declaration=True)
                            if item.filename in replacements else archive.read(item.filename))
                    target.writestr(item, data)
            # `os.replace` could overwrite a candidate path created by a
            # second writer after the earlier existence check. A same-folder
            # hard link publishes this complete ZIP atomically and refuses
            # if the destination appeared meanwhile.
            os.link(temporary, output)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    report = verify_local_change(baseline_pptx, output, preparation)
    report["route"] = "existing-native-pptx-leaf-patch"
    report["candidate_scene_hash"] = preparation["candidate_scene_hash"]
    return report
