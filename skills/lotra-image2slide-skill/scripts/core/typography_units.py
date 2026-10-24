"""Explicit source-pixel/point conversion and half-point native typography."""
import copy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

POLICY = 'typography-preflight-1.37.5'
POINT_FIELDS = ('line_spacing_pt', 'char_spacing_pt', 'left_indent_pt', 'right_indent_pt')


def number(value):
    if type(value) not in (int, float, str, Decimal):
        raise ValueError('TYPOGRAPHY_NUMBER_REQUIRED: finite decimal quantity')
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError('TYPOGRAPHY_NUMBER_REQUIRED: finite decimal quantity') from error
    if not result.is_finite():
        raise ValueError('TYPOGRAPHY_NUMBER_REQUIRED: finite decimal quantity')
    return result


def half_point(value, *, positive=True):
    value = number(value)
    if positive is True and value <= 0 or positive is False and value < 0:
        raise ValueError('TYPOGRAPHY_RANGE_REQUIRED: positive size/nonnegative spacing')
    result = (value * 2).quantize(Decimal('1'), rounding=ROUND_HALF_UP) / 2
    if positive is True and result <= 0:
        raise ValueError('TYPOGRAPHY_RANGE_REQUIRED: rounded size is below 0.5 pt')
    return float(result)


def points_per_pixel(scene):
    canvas = scene['canvas']
    if canvas.get('unit') != 'px':
        raise ValueError('TYPOGRAPHY_CANVAS_UNIT_REQUIRED: source geometry uses px')
    width = number(canvas['width']); inches = number(canvas['target_width_inches'])
    if width <= 0 or inches <= 0:
        raise ValueError('TYPOGRAPHY_CANVAS_REQUIRED: positive frozen physical/source width')
    return float(inches * 72 / width)


def canonicalize(scene):
    if scene.get('typography_policy') != POLICY:
        return scene
    if not any(obj['render_type'] in ('text','equation','table') for obj in scene['objects']):
        return scene
    result = copy.deepcopy(scene)
    scale = points_per_pixel(result)
    declared = result.get('typography_units', {})
    if declared.get('font_size') not in ('pt', 'source_px'):
        raise ValueError('TYPOGRAPHY_UNIT_REQUIRED: declare typography_units.font_size as pt or source_px')
    changes = []

    def style(value, inherited, path):
        if 'font_size' in value:
            unit = value.get('font_size_unit', declared['font_size'])
            if unit not in ('pt', 'source_px'):
                raise ValueError('TYPOGRAPHY_UNIT_REQUIRED: '+path)
            raw = number(value['font_size'])
            size = raw * number(scale) if unit == 'source_px' else raw
            # Explicit run scale is resolved once; OMML's implicit script layout
            # is left to the native Math engine, not rounded as an ordinary run.
            size *= number(value.get('font_scale', 1))
            rounded = half_point(size)
            if float(raw) != rounded or unit != 'pt' or 'font_scale' in value:
                changes.append({'location': path, 'input': float(raw), 'unit': unit,
                                'unrounded_pt': float(size), 'font_size_pt': rounded})
            value['font_size'] = rounded; value['font_size_unit'] = 'pt'
            value.pop('font_scale', None)
        elif 'font_scale' in value:
            if 'font_size' not in inherited:
                raise ValueError('TYPOGRAPHY_BASE_SIZE_REQUIRED: '+path)
            value['font_size'] = half_point(number(inherited['font_size']) * number(value.pop('font_scale')))
            value['font_size_unit'] = 'pt'
        for field in POINT_FIELDS:
            if field in value:
                mode=True if field=='line_spacing_pt' else None if field=='char_spacing_pt' else False
                value[field] = half_point(value[field], positive=mode)
        if isinstance(value.get('math_typography'),dict) and 'font_size_pt' in value['math_typography']:
            value['math_typography']['font_size_pt']=half_point(value['math_typography']['font_size_pt'])
        return {**inherited, **value}

    for obj in result['objects']:
        if obj['render_type'] not in ('text', 'equation', 'table'):
            continue
        base = style(obj['style'], {}, obj['id']+'/style')
        if 'font_size' not in base:
            raise ValueError('TYPOGRAPHY_BASE_SIZE_REQUIRED: '+obj['id'])
        content = obj['content']
        for pi, paragraph in enumerate(content.get('paragraphs', [content.get('runs', [])])):
            for ri, run in enumerate(paragraph):
                style(run, base, obj['id']+'/p'+str(pi)+'.r'+str(ri))
        for ri, row in enumerate(content.get('cell_styles', [])):
            for ci, cell in enumerate(row):
                style(cell, base, obj['id']+'/cell.'+str(ri)+'.'+str(ci))
        for pi, layout in enumerate(content.get('paragraph_layout', [])):
            style(layout, base, obj['id']+'/paragraph_layout.'+str(pi))
    result['typography_units'] = {'font_size': 'pt', 'geometry': 'source_px', 'point_step': 0.5}
    if changes:
        result.setdefault('typography_rounding_history', []).append(changes)
    return result


def guard_saved(scene, pptx):
    """Read written native attributes before any document rendering."""
    if scene.get('typography_policy') != POLICY:
        return {'applicable': False, 'legacy_policy_retained': True}
    from .inspect import xml
    from .mathml import NS
    root = xml(pptx); count = 0
    for node in root.iter():
        if node.tag in ('{'+NS['a']+'}rPr', '{'+NS['a']+'}defRPr', '{'+NS['a']+'}endParaRPr') and node.get('sz'):
            if int(node.get('sz')) <= 0 or int(node.get('sz')) % 50:
                raise ValueError('TYPOGRAPHY_NATIVE_GRID_REQUIRED: DrawingML size must be a multiple of 0.5 pt')
            count += 1
    return {'applicable': True, 'explicit_native_sizes': count, 'step_pt': 0.5,
            'scope': 'Saved explicit sizes only; no source-fidelity or backend-paint PASS'}


def validate(scene):
    if scene.get('typography_policy') != POLICY:
        return
    if not any(obj['render_type'] in ('text','equation','table') for obj in scene['objects']):
        return
    points_per_pixel(scene)
    if scene.get('typography_units', {}).get('font_size') != 'pt':
        raise ValueError('TYPOGRAPHY_CANONICAL_UNIT_REQUIRED: native construction uses pt')
    from .font_contract import payloads
    for obj in scene['objects']:
        samples=obj.get('typography_samples',{})
        if not isinstance(samples,dict) or any(not isinstance(row,dict) for row in samples.values()):
            raise ValueError('TYPOGRAPHY_SAMPLE_SCHEMA_REQUIRED: per-location source sample records')
    for obj, location, leaf, literal, math in payloads(scene):
        effective={**obj['style'], **leaf}
        value=effective.get('font_size')
        if value is None or number(value)!=number(half_point(value)) or effective.get('font_size_unit','pt')!='pt':
            raise ValueError('TYPOGRAPHY_HALF_POINT_REQUIRED: '+obj['id']+'/'+location)
        if 'font_scale' in leaf:
            raise ValueError('TYPOGRAPHY_SCALE_REQUIRED: resolve explicit run scaling before native write')
        math_size=effective.get('math_typography',{}).get('font_size_pt')
        if math_size is not None and number(math_size)!=number(half_point(math_size)):
            raise ValueError('TYPOGRAPHY_HALF_POINT_REQUIRED: explicit Math override at '+obj['id']+'/'+location)


def guard_written_math(obj, node):
    """Read back token/operator structure; physical style is checked separately."""
    from .mathml import math_zone, NS
    content=obj['content'];base=obj['style'];wanted=[]
    if obj['render_type']=='equation':
        spans=[(content['ast'],base)]
    else:
        spans=[(run['ast'],{**base,**run}) for paragraph in content.get('paragraphs',[content.get('runs',[])])
               for run in paragraph if 'ast' in run]
    def signature(item):
        # Font runs and control properties have their own exact native-style
        # checks. All Math operators, delimiters, indices and literal tokens stay.
        ignored={'{'+NS['a']+'}rPr','{'+NS['m']+'}ctrlPr'}
        return (item.tag,tuple(sorted(item.attrib.items())),item.text or '',
                tuple(signature(child) for child in item if child.tag not in ignored))
    for ast,style in spans:
        math=math_zone(ast,style['font_size'],style.get('font_faces',{}).get('math',style.get('math_font',style.get('font','Cambria Math'))),
                       inline=obj['render_type']=='text',color=style.get('color'),font_policy=style.get('math_font_policy','native_math'))
        wanted.extend(signature(item) for item in math.findall('.//m:oMath',NS))
    actual=[signature(item) for item in node.findall('.//m:oMath',NS)]
    if actual!=wanted:
        raise ValueError('TYPOGRAPHY_NATIVE_MATH_STRUCTURE_REQUIRED: '+obj['id'])
