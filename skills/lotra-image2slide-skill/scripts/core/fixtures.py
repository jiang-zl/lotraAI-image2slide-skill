"""Redistributable, self-authored probe data. Not a recognition backend."""

from pathlib import Path
from PIL import Image, ImageDraw
from .common import ROOT, digest, write_json
from .scene import FACETS


def token(text):
    return {"op": "token", "text": text}


def formulas():
    return {
        "scripts": {"op": "scripts", "base": token("f"), "sub": token("k"), "sup": token("max")},
        "fraction": {"op": "fraction", "numerator": token("1"), "denominator": {"op": "fraction", "numerator": token("x"), "denominator": token("y")}},
        "sum": {"op": "sum", "lower": token("i=1"), "upper": token("n"), "body": token("α")},
        "root": {"op": "sqrt", "body": token("β+1")},
        "accent": {"op": "accent", "mark": "̂", "body": token("v")},
        "matrix": {"op": "matrix", "rows": [[token("a"), token("b")], [token("c"), token("d")]]},
        "cases": {"op": "cases", "rows": [[token("x"), token("x≥0")], [token("0"), token("x<0")]]}}


def object_(id, kind, bbox, content=None, parent=None, semantic=None, **style):
    return {"id": id, "semantic_type": semantic or kind, "render_type": kind,
            "parent": parent, "bbox": bbox, "content": content or {}, "style": style,
            "versions": {k: 0 for k in FACETS}, "locks": {k: False for k in FACETS},
            "evidence_status": "observed"}


def create_probe(directory, variant=0):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    # This independent drawing is a limited geometric reference, not an Office render.
    ref = Image.new("RGB", (960, 540), "white")
    d = ImageDraw.Draw(ref)
    d.rectangle((50, 120, 190, 290), fill="#A7C5DF", outline="#17324D", width=2)
    d.rectangle((280, 160, 390, 225), fill="#A7C5DF", outline="#17324D", width=2)
    d.line((190, 205, 280, 192), fill="#17324D", width=2)
    d.text((50, 25), "sci-rebuild native capability probe", fill="#17324D")
    ref.save(directory / "reference.png")
    profile = (ROOT / "config/quality.seed.json").read_bytes()
    (directory / "profile.json").write_bytes(profile)
    objects = [
        object_("Title", "text", [40, 20, 850, 35], {"text": "sci-rebuild — native capability probe"}, font_size=20),
        object_("Device", "group", [50, 120, 140, 170], semantic="server"),
        object_("Chassis", "shape", [50, 120, 140, 170], {"preset": "cube"}, "Device", "chassis"),
        object_("FrontPanel", "group", [66, 178, 79, 67], parent="Device", semantic="front_panel"),
        object_("Indicator", "shape", [74, 187, 9, 9], {"preset": "ellipse"}, "FrontPanel", "indicator", fill="4B9D76"),
        object_("SlotA", "shape", [73, 210, 67, 8], {"preset": "rect"}, "FrontPanel", "slot", fill="35556E"),
        object_("SlotB", "shape", [73, 236, 67, 8], {"preset": "rect"}, "FrontPanel", "slot", fill="35556E"),
        object_("EndpointA", "shape", [280, 160, 110, 65], {"preset": "rect"}),
        object_("EndpointB", "shape", [560, 160, 100, 65], {"preset": "rect"}, fill="C6E2D2"),
        object_("Link", "connector", [390, 192, 170, 1], {"source": "EndpointA", "target": "EndpointB", "source_site": 3, "target_site": 1}),
        object_("BlockArrow", "shape", [715, 167, 150, 65], {"preset": "rightArrow"}, fill="DAA85A"),
        object_("Curve", "bezier", [280, 255, 380, 65], {"points": [[0, .8], [.3, -.2], [.65, 1.2], [1, .2]]}, stroke="597BB6", line_width=2),
    ]
    for i, (name, ast) in enumerate(formulas().items()):
        objects.append(object_("Equation_" + name, "equation", [40 + i % 4 * 225, 350 + i // 4 * 95, 205, 82], {"ast": ast}, font_size=19))
    if variant:
        # A different layout and semantic object type exercise the generic renderer.
        objects[1]["semantic_type"] = "instrument"
        for o in objects:
            if o["id"] in ("EndpointA", "EndpointB", "BlockArrow"):
                o["bbox"][1] += 45
        objects[2]["content"]["preset"] = "roundRect"
    evidence = {"revision": 0, "source_hash": digest(directory / "reference.png"),
                "origin": "self_authored_probe_v1", "scope": "native_structure_ground_truth_only",
                "source_semantic_review": "UNVERIFIED", "visual_reference_complete": False,
                "objects": objects, "note": "Reference sketch is not a fidelity benchmark or recognized research input."}
    write_json(directory / "evidence.json", evidence)
    scene = {"schema_version": "0.1", "revision": 0,
             "canvas": {"width": 960, "height": 540, "unit": "px", "target_width_inches": 10},
             "objects": objects, "relations": [], "prototypes": [],
             **{key: {"path": path, "sha256": digest(directory / path)}
                for key, path in [("source", "reference.png"), ("evidence", "evidence.json"), ("profile", "profile.json")]}}
    write_json(directory / "scene.json", scene)
    return scene
