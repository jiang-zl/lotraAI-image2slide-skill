"""Private, host-aware font identities. Discovery never installs any resource."""
import os
import platform
import struct
import unicodedata
from functools import lru_cache
from pathlib import Path
from .common import digest, identity, read_json, write_json

VERSION = 'font-resources-1'


def name_key(value):
    # Normalize spelling only. Never alias different designs or strip weights.
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def font_names(font, ids):
    records = [n for n in font['name'].names if n.nameID in ids]
    records.sort(key=lambda n: (n.nameID != ids[0], n.langID != 0x409, n.platformID != 3))
    values = []
    for record in records:
        try:
            value = record.toUnicode().strip()
        except (UnicodeError, LookupError):
            continue
        if value and value not in values:
            values.append(value)
    return values


def font_count(path):
    with Path(path).open('rb') as handle:
        header = handle.read(12)
    return struct.unpack('>I', header[8:12])[0] if header[:4] == b'ttcf' else 1


def describe(path, index=0, file_hash=None):
    from fontTools.ttLib import TTFont
    path = Path(path).resolve()
    font = TTFont(path, fontNumber=index, lazy=True)
    try:
        families = font_names(font, (16, 1))
        if not families:
            raise ValueError('Font has no family identity')
        os2 = font.get('OS/2')
        selection = int(getattr(os2, 'fsSelection', 0))
        permissions = int(getattr(os2, 'fsType', 2))
        editable = not permissions & 0x200 and (permissions & 8 != 0 or permissions & 0xE == 0)
        panose=getattr(os2,'panose',None)
        serif=getattr(panose,'bSerifStyle',0)
        style_class='sans' if serif in (11,12,13) else 'serif' if 2<=serif<=10 else 'unknown'
        return {'path': str(path), 'file_sha256': file_hash or digest(path), 'face_index': index,
                'family': families[0], 'aliases': families, 'subfamily': (font_names(font, (17, 2)) or ['Regular'])[0],
                'postscript_name': (font_names(font, (6,)) or [None])[0],
                'version': (font_names(font, (5,)) or [None])[0],
                'weight': int(getattr(os2, 'usWeightClass', 400)), 'italic': bool(selection & 1),
                'style_class':style_class,
                'fs_type': permissions, 'editable_embedding': editable,
                'no_subsetting': bool(permissions & 0x100), 'variable': 'fvar' in font,
                'outline': 'truetype' if 'glyf' in font else 'cff' if 'CFF ' in font else 'unsupported'}
    finally:
        font.close()


def matches(face, family):
    return name_key(family) in {name_key(n) for n in face['aliases']}


@lru_cache(maxsize=32)
def _characters(path,index,file_hash):
    from fontTools.ttLib import TTFont
    font = TTFont(path, fontNumber=index, lazy=True)
    try:
        return frozenset((font.getBestCmap() or {}).keys())
    finally:
        font.close()


def coverage(face,text):
    characters=_characters(face['path'],face['face_index'],face['file_sha256'])
    return sorted({c for c in text if not c.isspace() and ord(c) not in characters})


def roots(caps, configuration=None):
    configuration = configuration or {}
    local = platform.system()
    result = []
    def add(path, host):
        path = Path(path).expanduser()
        if path.is_dir():
            result.append({'path': str(path.resolve()), 'host': host})
    if local == 'Windows':
        add(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts', 'windows_office')
        add(Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local'))) / 'Microsoft/Windows/Fonts', 'windows_office')
    elif local == 'Darwin':
        for path in ('/System/Library/Fonts', '/Library/Fonts', str(Path.home()/'Library/Fonts'),
                     '/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts'):
            add(path, 'macos')
    else:
        for path in ('/usr/share/fonts', '/usr/local/share/fonts', str(Path.home()/'.fonts'), str(Path.home()/'.local/share/fonts')):
            add(path, 'linux')
        # A readable cross-host font directory does not require a COM/Office
        # renderer. Font identities, glyphs and embedding permissions are
        # independently inspected below; missing mounts remain absent.
        add('/mnt/c/Windows/Fonts', 'windows_office')
        users = Path('/mnt/c/Users')
        if users.is_dir():
            for user in users.iterdir():
                add(user/'AppData/Local/Microsoft/Windows/Fonts', 'windows_office')
    for row in configuration.get('font_roots', [])[:32]:
        add(row['path'], row.get('host', 'configured'))
    for path in configuration.get('font_dirs', [])[:16]:
        add(path, 'configured')
    return list({(r['path'], r['host']): r for r in result}.values())


def catalogue(project, caps, configuration=None):
    """Reuse unchanged file identities; a font edit updates the environment key."""
    configuration = configuration or {}
    root = Path(project)/'.lotraAI-build/toolchain'
    cache = root/'font-resources.json'
    prior = read_json(cache) if cache.is_file() else {}
    old = prior.get('files', {}) if prior.get('version') == VERSION else {}
    found = {};directories={}
    discovered_roots=roots(caps, configuration)
    for directory in discovered_roots:
        directories[directory['path']]=Path(directory['path']).stat().st_mtime_ns
        for path in Path(directory['path']).rglob('*'):
            if path.is_dir():directories[str(path.resolve())]=path.stat().st_mtime_ns
            if path.suffix.lower() not in ('.ttf', '.otf', '.ttc', '.otc') or not path.is_file():
                continue
            key = str(path.resolve())
            stat = path.stat()
            stamp = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
            row = old.get(key, {})
            if row.get('stamp') != stamp:
                try:
                    file_hash = digest(path)
                    count = font_count(path)
                    if not 1 <= count <= 256:
                        raise ValueError('Font collection exceeds the bounded face count')
                    row = {'stamp': stamp, 'faces': [describe(path, i, file_hash) for i in range(count)]}
                except (ValueError, OSError, ImportError, KeyError, struct.error) as error:
                    row = {'stamp': stamp, 'faces': [], 'status': 'FONT_METADATA_UNAVAILABLE', 'reason': str(error)}
                except Exception as error:
                    # fontTools exposes malformed-font failures outside the
                    # standard exceptions. Preserve that one file's pending
                    # state, not a discovery-wide failure or a fallback font.
                    from fontTools.ttLib import TTLibError
                    if not isinstance(error,TTLibError):raise
                    row = {'stamp': stamp, 'faces': [], 'status': 'FONT_METADATA_UNAVAILABLE', 'reason': str(error)}
            row = {**row, 'hosts': sorted(set(found.get(key, {}).get('hosts', [])+[directory['host']]))}
            found[key] = row
    faces = []
    for row in found.values():
        for face in row.get('faces', []):
            face = {**face, 'hosts': row['hosts']}
            face['id'] = identity({k: face[k] for k in ('file_sha256', 'face_index', 'family')})
            faces.append(face)
    selected_host = ('windows_office' if caps.get('windows_office', {}).get('available')
                     and caps.get('render_preference', 'powerpoint') == 'powerpoint' else
                     'macos' if platform.system() == 'Darwin' else 'linux' if platform.system() == 'Linux' else 'windows_office')
    key = identity({'os': platform.system(), 'machine': platform.machine(), 'host': selected_host,
                    'route': {k: caps.get(k) for k in ('render_preference', 'windows_office', 'macos_office', 'host_tools')},
                    'files': {p: {'stamp': r['stamp'], 'identities': [f['file_sha256'] for f in r['faces']]} for p, r in found.items()}})
    record = {'version': VERSION, 'environment_key': key, 'host': selected_host, 'files': found, 'faces': faces,'directories':directories,
              'discovery': 'Existing private resources only; no installation or font redistribution'}
    if record != prior:
        write_json(cache, record)
    # Discovery is shared by task, render and backend commands. A descriptor
    # must retain its exact catalogue when another command uses a different
    # renderer configuration in the same project.
    snapshot=root/'font-resource-catalogues'/(identity(record)+'.json')
    if snapshot.is_file():
        if read_json(snapshot)!=record:raise ValueError('Frozen font resource catalogue changed')
    else:write_json(snapshot,record)
    return {'version': VERSION, 'environment_key': key, 'host': selected_host, 'catalogue': str(snapshot),
            'catalogue_sha256':digest(snapshot),
            'face_count': len(faces), 'unavailable_files': sum(not r['faces'] for r in found.values()),
            'font_config': configuration,'discovery_roots':discovered_roots}


def available(caps):
    descriptor = caps.get('fonts', {})
    path = Path(descriptor.get('catalogue', ''))
    if not path.is_file():
        return []
    if descriptor.get('catalogue_sha256') and digest(path)!=descriptor['catalogue_sha256']:
        raise ValueError('Frozen font resource catalogue changed')
    record = read_json(path)
    if record.get('environment_key') != descriptor.get('environment_key'):
        raise ValueError('Font resource catalogue belongs to another environment')
    return record['faces']
