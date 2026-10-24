"""Font requirements, complete native slots and independent text-style spans."""
from .common import identity

POLICY = 'font-workflow-1.37.4'
SLOTS = ('latin', 'ea', 'cs')
LEGACY_FIELDS = ('owner', 'location', 'role', 'characters', 'literal_hash', 'bold', 'italic', 'proposed_family')


def enabled(state=None, scene=None):
    return ((state or {}).get('font_workflow_policy') == POLICY or
            (scene or {}).get('font_workflow_policy') == POLICY or
            (scene or {}).get('font_plan', {}).get('policy') == POLICY)


def merge_style(base, leaf=None):
    leaf = leaf or {}
    result = {**base, **leaf}
    if base.get('font_faces') or leaf.get('font_faces'):
        result['font_faces'] = {**base.get('font_faces', {}), **leaf.get('font_faces', {})}
    return result


def resolve_faces(base, leaf=None):
    """One deterministic rule for both native emission and expected attributes."""
    style = merge_style(base, leaf)
    faces = style.get('font_faces', {})
    primary = next((faces[k] for k in SLOTS if faces.get(k)), style.get('font', 'DejaVu Sans'))
    result = {slot: faces.get(slot, primary) for slot in SLOTS}
    if faces.get('math'):
        result['math'] = faces['math']
    return result


def request_value(request):
    if request.get('identity_policy') != POLICY:
        return {key: request[key] for key in LEGACY_FIELDS}
    return {key: request[key] for key in LEGACY_FIELDS if key != 'proposed_family'} | {
        'identity_policy': POLICY, 'required_family': request.get('required_family'),
        'intent_revision': request.get('intent_revision')}


def request_key(request):
    return identity(request_value(request))


def style_feasible(face, request, synthetic=False):
    if face.get('variable') or not face.get('editable_embedding'):
        return False
    if not request['bold'] and face['weight'] >= 600 or not request['italic'] and face['italic']:
        return False
    return bool(synthetic) or (face['weight'] >= 600) == request['bold'] and bool(face['italic']) == request['italic']


def style_value(style,native=False):
    """Logical emphasis is independent of native run subdivision and font hint."""
    return {'color': style.get('color', '17324D').upper(),
            'bold': bool(style.get('native_bold',style.get('bold',False)) if native else style.get('bold',False)),
            'italic': bool(style.get('native_italic',style.get('italic',False)) if native else style.get('italic',False))}


def paragraph_spans(runs, style,native=False):
    text = ''; spans = []
    for run in (native_runs(runs,style) if native else runs):
        literal = '\ufffc' if 'ast' in run else run.get('text', '')
        if not literal:
            continue
        start = len(text); text += literal
        value = style_value(merge_style(style, run),native) if 'ast' not in run else {'math': True}
        if spans and spans[-1]['style'] == value:
            spans[-1]['end'] = len(text)
        else:
            spans.append({'start': start, 'end': len(text), 'style': value})
    return {'text': text, 'spans': spans}


def native_runs(runs,style):
    """Split only physical emphasis at script boundaries; logical runs survive."""
    from .font_contract import script
    result=[]
    for run in runs:
        flags=merge_style(style,run).get('native_script_styles')
        if not flags or 'ast' in run:
            result.append(run);continue
        groups=[]
        for character in run.get('text',''):
            role=script(character) if not character.isspace() else None
            selected=flags.get(role) if role else (groups[-1][1] if groups else next(iter(flags.values())))
            selected=selected or next(iter(flags.values()))
            if groups and groups[-1][1]==selected:groups[-1][0]+=character
            else:groups.append([character,selected])
        result.extend({**run,'text':text,**{'native_'+k:v for k,v in flags.items()}}
                      for text,flags in groups)
    return result


def source_spans(scene,native=False):
    result = {}
    for obj in scene['objects']:
        style, content = obj['style'], obj['content']
        if obj['render_type'] == 'text':
            paragraphs = content.get('paragraphs')
            if paragraphs is None:
                paragraphs = [content['runs']] if 'runs' in content else [[{'text': line}] for line in content.get('text', '').split('\n')]
            result[obj['id']] = {'paragraphs': [paragraph_spans(row, style,native) for row in paragraphs]}
        elif obj['render_type'] == 'table':
            formats = content.get('cell_styles', [[{} for _ in row] for row in content['rows']])
            result[obj['id']] = {'cells': [[
                [paragraph_spans([{'text': line}], merge_style(style, formats[ri][ci]),native) for line in literal.split('\n')]
                for ci, literal in enumerate(row)] for ri, row in enumerate(content['rows'])]}
    return result


def saved_spans(shape, kind):
    """Read saved XML directly; no writer or inferred font plan supplies colour."""
    from lxml import etree as E
    from .mathml import NS
    def paragraph(node):
        defaults = node.find('a:pPr/a:defRPr', NS)
        runs = []
        for child in node:
            local = E.QName(child).localname
            if local == 'm':
                runs.append({'ast': True}); continue
            if local != 'r':
                continue
            props = child.find('a:rPr', NS)
            def attribute(name):
                return props.get(name, defaults.get(name, '0') if defaults is not None else '0') if props is not None else defaults.get(name, '0') if defaults is not None else '0'
            color = props.find('a:solidFill/a:srgbClr', NS) if props is not None else None
            if color is None and defaults is not None:
                color = defaults.find('a:solidFill/a:srgbClr', NS)
            runs.append({'text': ''.join(child.itertext('{'+NS['a']+'}t')),
                         'color': color.get('val') if color is not None else 'UNRESOLVED',
                         'bold': attribute('b') in ('1', 'true'), 'italic': attribute('i') in ('1', 'true')})
        return paragraph_spans(runs, {})
    if kind == 'text':
        return {'paragraphs': [paragraph(p) for p in shape.findall('p:txBody/a:p', NS)]}
    return {'cells': [[[paragraph(p) for p in cell.findall('a:txBody/a:p', NS)]
                       for cell in row.findall('a:tc', NS)]
                      for row in shape.findall('a:graphic/a:graphicData/a:tbl/a:tr', NS)]}


def verify_source_spans(task, state, scene):
    """Compare with the frozen, currently authorized source scene before fonts."""
    if not enabled(state) or not state.get('component_workflow'):
        return
    from . import component_workflow as workflow
    from .common import read_json
    contract, _ = workflow._load(task, state)
    frozen = read_json(workflow._resource(task, contract['source_scene']))
    expected, actual = source_spans(frozen), source_spans(scene)
    for owner in set(expected) & set(actual):
        if expected[owner] != actual[owner]:
            raise ValueError('FONT_TEXT_STYLE_CHANGE: preserve frozen text and colour/emphasis intervals: '+owner)
