"""Logical text and explicit native layout breaks are distinct source facts."""
from .mathml import NS

DIRECTIONS={'horizontal':'horz','east_asian_vertical':'eaVert','vertical':'vert','vertical_270':'vert270'}


def source_native_text(content):
    if 'paragraphs' in content:
        return '\n'.join(''.join(run.get('text','') for run in row) for row in content['paragraphs'])
    if 'runs' in content:return ''.join(run.get('text','') for run in content['runs'])
    return content.get('text','')


def logical(native,layout):
    boundaries=layout.get('soft_breaks',[])
    if (not isinstance(boundaries,list) or len(boundaries)!=len(set(boundaries)) or
            any(type(value) is not int or value<0 for value in boundaries)):
        raise ValueError('Explicit distinct soft-break character offsets required')
    result=[];observed=[]
    for character in native:
        offset=len(result)
        if character=='\n' and offset in boundaries:
            observed.append(offset)
        else:result.append(character)
    if sorted(observed)!=sorted(boundaries):
        raise ValueError('SOFT_BREAK_MAPPING_REQUIRED: every declared layout break must exist at its exact native boundary')
    return ''.join(result)


def validate(content):
    layout=content.get('text_layout')
    if layout is None:return
    if not isinstance(layout,dict) or set(layout)-{'direction','soft_breaks','source_evidence'}:
        raise ValueError('Text layout contains direction, soft_breaks and source_evidence only')
    if layout.get('direction','horizontal') not in DIRECTIONS or not layout.get('source_evidence'):
        raise ValueError('Source-supported text direction required')
    expected=content.get('logical_text')
    if not isinstance(expected,str) or logical(source_native_text(content),layout)!=expected:
        raise ValueError('LOGICAL_TEXT_MISMATCH: layout cannot change original characters or hard paragraph breaks')


def saved_text(shape,content):
    native='\n'.join(''.join(item.text or '' for item in p.iter('{'+NS['a']+'}t'))
                     for p in shape.findall('p:txBody/a:p',NS))
    if content.get('text_layout'):
        validate(content)
        return logical(native,content['text_layout'])
    return native


def expected_text(content):
    if content.get('text_layout'):
        validate(content);return content['logical_text']
    return content.get('text',source_native_text(content))
