"""Minimal explicit Scene contract; unknown semantics are preserved, unresolved."""

import math
from pathlib import Path
import jsonschema
from .common import ROOT, digest, read_json, safe_path
from .mathml import math_node

RENDER_TYPES = {"text", "shape", "group", "connector", "bezier", "path", "trace", "equation", "photo", "svg", "table", "unresolved"}
FACETS = ("content", "structure", "style", "placement")
MAX_SCENE_OBJECTS = 200000  # Upper resource guard, not an Office usability claim.


def validate(scene, base=None, verify_resources=True):
    from .source_contract import finite
    finite(scene,'Scene')
    if (isinstance(scene, dict) and isinstance(scene.get('objects'), list)
            and len(scene['objects']) > MAX_SCENE_OBJECTS):
        raise ValueError('Scene object count exceeds the bounded native resource limit')
    try:jsonschema.validate(scene, read_json(ROOT / "schemas/scene.json"))
    except jsonschema.ValidationError as exc:raise ValueError('Invalid Scene: '+exc.message) from exc
    objects = {o["id"]: o for o in scene["objects"]}
    if len(objects) != len(scene["objects"]):
        raise ValueError("Duplicate object identity")
    if not objects:
        raise ValueError("Empty Scene cannot be validated as a reconstruction")
    from .typography_units import validate as validate_typography
    validate_typography(scene)
    if scene.get('frame_plan') and base is not None:
        from .frame_plan import load as load_frames, validate as validate_frames
        validate_frames(load_frames(base,scene['frame_plan']),base,scene=scene)
    prototypes = {p["id"] for p in scene["prototypes"]}
    if len(prototypes) != len(scene["prototypes"]):
        raise ValueError("Duplicate prototype")
    for r in scene["relations"]:
        if r.get("source") not in objects or r.get("target") not in objects:
            raise ValueError("Dangling scene relation")
    for o in objects.values():
        if o['render_type']=='group' and o['content'].get('native_asset') and base is not None:
            from .native_asset import load
            load(base,o['content']['native_asset'])
        if o.get("prototype_id") and o["prototype_id"] not in prototypes:
            raise ValueError("Dangling prototype reference")
        for key in ("font_size", "line_width"):
            value = o["style"].get(key)
            no_outline=(key=='line_width' and o['style'].get('stroke','17324D') in (None,'none') and value==0)
            if value is not None and not no_outline and (not isinstance(value, (int,float)) or not math.isfinite(value) or value <= 0):
                raise ValueError("Invalid style size")
        for n in o["bbox"]:
            if not math.isfinite(n):
                raise ValueError("Nonfinite geometry")
        extent=o['bbox'][2:]
        if min(extent)<0 or max(extent)<=0 or min(extent)==0 and o['render_type']!='connector':
            raise ValueError("Nonpositive extent")
        seen = {o["id"]}
        parent = o.get("parent")
        while parent:
            if parent not in objects or parent in seen:
                raise ValueError("Missing parent or containment cycle")
            if objects[parent]["render_type"] != "group":
                raise ValueError("Only groups may contain render nodes")
            seen.add(parent)
            parent = objects[parent].get("parent")
        if o["render_type"] not in RENDER_TYPES:
            raise ValueError("Unsupported render type; preserve unknown as unresolved")
        if o['render_type']=='svg' and base is not None:
            from .vector_asset import validate as validate_svg
            validate_svg(o['content'],base)
        if o["render_type"] == "equation":
            math_node(o["content"]["ast"])
        if o['render_type']=='text':
            c=o['content']
            from .text_layout import validate as validate_text_layout
            validate_text_layout(c)
            if not any(k in c for k in ('text','runs','paragraphs')):raise ValueError('Text content required')
            for paragraph in c.get('paragraphs',[c.get('runs',[])]):
                for run in paragraph:
                    if 'ast' in run:math_node(run['ast'])
                    if 'baseline' in run and (type(run['baseline']) is not int or not -35000<=run['baseline']<=35000):
                        raise ValueError('Native text baseline uses integer OOXML units (-35000..35000); -30000 is a 30 percent subscript')
        if o['render_type'] in ('path','trace'):
            contours=o['content'].get('contours')
            if contours is None:
                ref=o['content']['geometry_ref']
                if base is not None:
                    path=safe_path(base,ref['path'])
                    if digest(path)!=ref['sha256']:raise ValueError('Geometry asset changed')
                    contours=read_json(path)['contours']
                    if o['render_type']=='trace' and not read_json(path).get('layers'):raise ValueError('Trace requires measured tone layers')
            if contours is not None:
                if not contours or sum(len(c.get('points',c.get('commands',[]))) for c in contours)>200000:raise ValueError('Invalid/overbudget path contours')
                for contour in contours:
                    from .geometry import path_operations
                    if len(path_operations(contour))<2:raise ValueError('Invalid path point')
        if o['render_type']=='shape' and o['content'].get('connection_sites'):
            if o['content']['preset'] not in ('rect','roundRect','ellipse'):raise ValueError('Unsupported ported shape')
            if any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in o['content']['connection_sites']):raise ValueError('Invalid custom connection site')
        if o['render_type']=='shape':
            from .material_effects import validate as validate_material
            validate_material(o['style'])
            from .presets import validate as validate_preset
            validate_preset(o['content']['preset'],o['content'].get('adjustments',[]))
        if o["render_type"]=="table":
            from .tables import validate as validate_table
            validate_table(o['content'])
            for key,index in [('column_widths',2),('row_heights',3)]:
                if key in o['content'] and abs(sum(o['content'][key])-o['bbox'][index])>1e-6:raise ValueError('Table source-pixel dimensions must sum to declared bbox')
        if o["render_type"] == "connector":
            for field in ("source", "target"):
                if o["content"].get(field) and o["content"][field] not in objects:
                    raise ValueError("Dangling connector")
            if o['content'].get('source') and o["content"]["source"] == o["content"].get("target") and not o['content'].get('points'):
                raise ValueError("Self connector needs an explicit curve route")
            for endpoint in ("source","target"):
                if not o['content'].get(endpoint) or not o['content'].get(endpoint+'_anchor',True):continue
                target_id=o['content'].get(endpoint+'_anchor_object',o['content'][endpoint])
                if target_id not in objects:raise ValueError('Unknown native anchor object')
                target=objects[target_id]
                supported=(target['render_type'] in ('photo','svg','table','group') or target['render_type']=='path' and bool(target['content'].get('connection_sites')) or target['render_type']=='shape' and target['content'].get('preset') in ('rect','roundRect','ellipse'))
                if not supported:raise ValueError('Unsupported native anchor geometry')
                site=o['content'].get(endpoint+'_site',3 if endpoint=='source' else 1)
                if not isinstance(site,int) or not 0<=site<4+len(target['content'].get('connection_sites',[])):raise ValueError('Invalid native connection site')
                if target['render_type']=='path' and site<4:raise ValueError('Path endpoint must use an explicit visible-path port')
            from .geometry import connector_points
            points=connector_points(objects,o)
            if any(not all(math.isfinite(v) for v in p) for p in points):raise ValueError('Invalid connector route')
        from .complex_assets import validate_contract, RASTER_ROLES
        validate_contract(o, scene, base)
        if o["render_type"] == "photo" and o["semantic_type"] not in {"photo", "experimental_image", "data_image"} | RASTER_ROLES:
            raise ValueError("Raster cannot represent schematic icon")
        if o['render_type'] == 'photo' and o['content'].get('reconstruction', {}).get('appearance_policy') == 'semantic_hd_replace':
            if o['semantic_type'] in ('experimental_image', 'data_image'):
                raise ValueError('Generated illustration cannot masquerade as observed scientific data')
            if o['semantic_type'] not in RASTER_ROLES:
                from .appearance import semantic_hd_asset
                semantic_hd_asset(o['content'], base)
        if o['semantic_type']=='data_image' and o['render_type']=='photo':
            if o['content'].get('original_numeric_data')!='unavailable' or not o['content'].get('source_roi') or not o['content'].get('purpose'):raise ValueError('Observed data image requires provenance and unknown numeric-data boundary')
    from .geometry import validate_attachment_contracts
    validate_attachment_contracts(scene)
    from .complex_assets import validate_foreground
    validate_foreground(scene)
    if scene.get('analysis') and base is not None:
        p=safe_path(base,scene['analysis']['path'])
        if digest(p)!=scene['analysis']['sha256']:raise ValueError('Frozen Source Analysis changed')
        from .source_analysis import validate as validate_analysis
        validate_analysis(read_json(p),base,scene)
    if verify_resources:
        if base is None:
            raise ValueError("Input base directory required")
        for field in ("source", "evidence", "profile"):
            resource = scene[field]
            p = safe_path(base, resource["path"])
            if digest(p) != resource["sha256"]:
                raise ValueError(f"Frozen {field} hash changed")
    return objects
