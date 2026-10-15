"""Verify either direct EOT or provider resources against the exact full face."""
import io
import posixpath
import struct
from lxml import etree as E
from .common import digest
from .font_resources import font_names, name_key

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def slot(face):
    return ('boldItalic' if face['italic'] and face['weight'] >= 600 else
            'italic' if face['italic'] else 'bold' if face['weight'] >= 600 else 'regular')


def sfnt(data, content_type):
    if content_type == 'application/x-font-ttf':
        return data
    if content_type != 'application/x-fontdata' or len(data) < 82:
        raise ValueError('Unsupported embedded font representation')
    total, size, version, flags = struct.unpack_from('<4I', data)
    rights, magic = struct.unpack_from('<HH', data, 32)
    if total != len(data) or magic != 0x504C or flags & 5:
        raise ValueError('A complete uncompressed, non-subset EOT resource is required')
    if rights & 0x200 or not (rights & 8 or rights & 0xE == 0) or not 0 < size <= len(data)-82:
        raise ValueError('Embedded font payload/rights are incompatible with editable delivery')
    return data[-size:]


def verify_face(data, content_type, face):
    from fontTools.ttLib import TTFont
    if digest(face['path']) != face['file_sha256']:
        raise ValueError('Archived font face changed')
    source = TTFont(face['path'], fontNumber=face['face_index'], lazy=True)
    actual = TTFont(io.BytesIO(sfnt(data, content_type)), lazy=True)
    try:
        if name_key(face['family']) not in {name_key(n) for n in font_names(actual, (16, 1))}:
            raise ValueError('Provider serialized a different family')
        rights = int(getattr(actual.get('OS/2'), 'fsType', 2))
        if rights & 0x200 or not (rights & 8 or rights & 0xE == 0):
            raise ValueError('Embedded SFNT does not permit editable embedding')
        # Compare complete glyph, mapping, outline, shaping and metrics tables.
        # Only naming records, signatures and build timestamps may be rewritten.
        ignored = {'GlyphOrder', 'head', 'name', 'DSIG', 'FFTM'}
        keys = set(source.keys())-ignored
        if keys != set(actual.keys())-ignored:
            raise ValueError('Provider omitted or introduced a substantive font table')
        if any(source.getTableData(k) != actual.getTableData(k) for k in keys):
            raise ValueError('Provider full face differs from the archived glyph/metric identity')
        fields = ('unitsPerEm', 'xMin', 'yMin', 'xMax', 'yMax', 'macStyle', 'indexToLocFormat')
        if any(getattr(source['head'], k) != getattr(actual['head'], k) for k in fields):
            raise ValueError('Embedded font outline frame differs')
    finally:
        source.close(); actual.close()
    return True


def verify_package(package, bindings):
    presentation = E.fromstring(package.read('ppt/presentation.xml'))
    relationships = {n.get('Id'): n for n in E.fromstring(package.read('ppt/_rels/presentation.xml.rels'))}
    types = E.fromstring(package.read('[Content_Types].xml'))
    entries = presentation.findall('{'+P+'}embeddedFontLst/{'+P+'}embeddedFont')
    results = []
    faces = {b['resource']['id']: b['resource'] for b in bindings}
    for key, face in faces.items():
        matches = [e for e in entries if e.find('{'+P+'}font') is not None
                   and e.find('{'+P+'}font').get('typeface') == face['family']]
        if len(matches) != 1:
            raise ValueError('Exactly one embedded family entry is required: '+face['family'])
        node = matches[0].find('{'+P+'}'+slot(face))
        rel = relationships.get(node.get('{'+R+'}id')) if node is not None else None
        if rel is None or rel.get('Type') != R+'/font' or rel.get('TargetMode') == 'External':
            raise ValueError('Missing internal font relationship')
        part = posixpath.normpath(posixpath.join('ppt', rel.get('Target', '')))
        if not part.startswith('ppt/fonts/') or part not in package.namelist():
            raise ValueError('Font part leaves the declared package font domain')
        content_type = next((t.get('ContentType') for t in types if t.get('PartName') == '/'+part), None)
        content_type = content_type or next((t.get('ContentType') for t in types
                                            if t.get('Extension') == part.rsplit('.', 1)[-1]), None)
        if part=='ppt/fonts/lotra-'+key[:24]+'.fntdata':
            from .font_embedding import eot
            if package.read(part)!=eot(face):raise ValueError('Direct embedded font differs from the complete bound resource')
        else:verify_face(package.read(part), content_type, face)
        results.append({'resource_id': key, 'part': part, 'slot': slot(face), 'passed': True})
    if faces and (presentation.get('embedTrueTypeFonts') != '1' or presentation.get('saveSubsetFonts') != '0'):
        raise ValueError('Complete editable font settings are required')
    return results
