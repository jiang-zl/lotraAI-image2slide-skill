"""Task-local raw resource reuse. No predicate, receipt or semantic decision.

Every public lookup hashes the current file. Scope-owned handles and images are
bounded, pinned while borrowed and closed on exit. Persistent entries contain
only small, dependency-bound pixels; independent final scopes bypass them.
"""
import base64
import contextlib
import copy
import hashlib
import io
import json
import platform
import zlib
from collections import OrderedDict
from pathlib import Path
from .common import ROOT, canonical, digest, identity


class Facts:
    def __init__(self, scope):
        from .context_policy import configuration
        self.scope = scope
        policy = configuration()
        self.budget = scope['image_budget']
        self.max_entries = min(policy['cache']['max_entries'], 256)
        self.pixel_limit = min(1048576, self.budget // 8, policy['cache']['max_bytes'] // 16)
        self.entries = OrderedDict()
        self.pins = {}
        self.bytes = 0
        self.library = None
        self.counts = {name: 0 for name in (
            'memory_hits', 'memory_misses', 'persistent_pixel_hits',
            'image_header_reads', 'image_decodes', 'image_transforms', 'package_opens', 'package_part_reads', 'xml_parses',
            'pdf_opens', 'pdf_clip_rasters', 'compat_full_image_copies', 'evictions')}
        self.dependencies = {'resource_code': digest(__file__),
                             'common_code': digest(Path(__file__).with_name('common.py')),
                             'python': platform.python_version()}

    def close(self):
        try:
            with contextlib.ExitStack() as cleanup:
                for value, cost, close in self.entries.values():
                    if close:
                        cleanup.callback(close, value)
        finally:
            self.entries.clear()
            self.bytes = 0

    def get(self, key):
        row = self.entries.get(key)
        if row is None:
            self.counts['memory_misses'] += 1
            return None
        self.entries.move_to_end(key)
        self.counts['memory_hits'] += 1
        return row[0]

    def put(self, key, value, cost, close=None):
        if key in self.entries:
            # A second header/transform may already have admitted this key.
            # Never overwrite a live borrower or double-count its bytes.
            self.entries.move_to_end(key)
            return self.entries[key][0] is value
        if cost > self.budget:
            return False
        while self.entries and (self.bytes + cost > self.budget or len(self.entries) >= self.max_entries):
            victim = next((k for k in self.entries if not self.pins.get(k)), None)
            if victim is None:
                return False
            old, size, dispose = self.entries.pop(victim)
            self.bytes -= size
            self.counts['evictions'] += 1
            if dispose:
                dispose(old)
        self.entries[key] = (value, cost, close)
        self.bytes += cost
        return True

    @contextlib.contextmanager
    def borrow(self, key, create, cost, close=None):
        value = self.get(key)
        stored = value is not None
        if not stored:
            value = create()
            stored = self.put(key, value, cost(value), close)
        if stored:
            self.pins[key] = self.pins.get(key, 0) + 1
        try:
            yield value
        finally:
            if stored:
                self.pins[key] -= 1
                if not self.pins[key]:
                    del self.pins[key]
            elif close:
                close(value)

    def persistent(self):
        if self.scope.get('independent') or not self.scope.get('library_scope') or not self.scope.get('project'):
            return None
        if self.library is None:
            from .library_store import Library
            self.library = Library(self.scope['project'])
        return self.library

    def pixel_dependencies(self, resource_hash, recipe, libraries):
        # JSON normalization keeps tuple/enum recipes equal after DB roundtrip.
        return json.loads(canonical(dict(self.dependencies, scope=self.scope.get('library_scope'),
                           resource=resource_hash, recipe=recipe, libraries=libraries)))

    def load_pixels(self, key, dependencies):
        library = self.persistent()
        if library is None:
            return None
        payload = library.cache_get('resource-pixels:' + key, dependencies)
        if payload is None:
            return None
        from PIL import Image
        mode, size = payload.get('mode'), payload.get('size')
        if payload.get('format') != 'raw-pixels-1' or mode not in ('RGB', 'L') or not isinstance(size, list) or len(size) != 2 or any(type(n) is not int or n <= 0 for n in size):
            raise ValueError('Invalid raw pixel cache header')
        length = size[0] * size[1] * (3 if mode == 'RGB' else 1)
        if length > self.pixel_limit:
            return None  # A smaller current budget means recompute, never skip.
        encoded = payload.get('zlib')
        if not isinstance(encoded, str) or len(encoded) > self.pixel_limit * 2:
            raise ValueError('Unbounded raw pixel cache')
        decoder = zlib.decompressobj()
        raw = decoder.decompress(base64.b64decode(encoded, validate=True), length + 1)
        if len(raw) != length or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or hashlib.sha256(raw).hexdigest() != payload.get('raw_sha256'):
            raise ValueError('Changed raw pixel cache')
        image = Image.frombytes(mode, tuple(size), raw)
        image.info['_resource_metadata'] = payload.get('metadata', {})
        self.counts['persistent_pixel_hits'] += 1
        return image

    def store_pixels(self, key, dependencies, image):
        length = image.width * image.height * len(image.getbands())
        if image.mode not in ('RGB', 'L') or length > self.pixel_limit:
            return
        library = self.persistent()
        if library is None:
            return
        raw = image.tobytes()
        library.cache_put('resource-pixels:' + key, {
            'format': 'raw-pixels-1', 'mode': image.mode, 'size': list(image.size),
            'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'zlib': base64.b64encode(zlib.compress(raw, level=1)).decode('ascii'),
            'metadata': image.info.get('_resource_metadata', {})}, dependencies)


@contextlib.contextmanager
def _facts():
    from .execution_context import _active
    scope = _active.get()
    if scope is not None:
        yield scope['resources']
    else:
        from .context_policy import image_budget
        facts = Facts({'image_budget': image_budget(), 'independent': True})
        try:
            yield facts
        finally:
            facts.close()


def _hash(path, expected_hash=None):
    actual = digest(path)
    if expected_hash is not None and actual != expected_hash:
        raise ValueError('Actual resource changed before shared read')
    return actual


def _owned(image):
    result = image.copy()
    result.info = copy.deepcopy(image.info)
    return result


class ImageView:
    """Restricted read-only borrower; crop/resize always return owned images."""
    __slots__ = ('__image',)

    def __init__(self, image):
        self.__image = image

    @property
    def size(self):
        return self.__image.size

    @property
    def width(self):
        return self.__image.width

    @property
    def height(self):
        return self.__image.height

    @property
    def mode(self):
        return self.__image.mode

    def crop(self, box):
        result = self.__image.crop(box)
        result.info = copy.deepcopy(result.info)
        return result

    def resize(self, size, resample, box=None):
        result = self.__image.resize(size, resample, box=box)
        result.info = copy.deepcopy(result.info)
        return result


@contextlib.contextmanager
def _decoded(facts, path, actual, mode):
    from PIL import Image, __version__
    key = identity({'decoded': actual, 'mode': mode, 'Pillow': __version__})

    def create():
        with Image.open(path) as image:
            if mode == 'RGB_WHITE':
                from .common import raster_rgb
                result = raster_rgb(image)
            else:
                result = image.convert(mode) if mode else image.copy()
            result.load()
        if digest(path) != actual:
            result.close()
            raise ValueError('Image changed during decode')
        facts.counts['image_decodes'] += 1
        facts.put(identity({'image_dimensions':actual,'Pillow':__version__}),result.size,128)
        return result

    with facts.borrow(key, create, lambda im: im.width * im.height * max(4, len(im.getbands())), lambda im: im.close()) as image:
        yield image


def image_dimensions(path, expected_hash=None):
    """Header-only lookup lets a persisted ROI hit precede full decoding."""
    from PIL import Image, __version__
    actual = _hash(path, expected_hash)
    with _facts() as facts:
        key = identity({'image_dimensions':actual,'Pillow':__version__})
        size = facts.get(key)
        if size is None:
            with Image.open(path) as image:
                size = image.size
            if digest(path) != actual:
                raise ValueError('Image changed during header read')
            facts.counts['image_header_reads'] += 1
            facts.put(key,size,128)
        return tuple(size)


@contextlib.contextmanager
def image_view(path, expected_hash=None, *, mode='RGB'):
    actual = _hash(path, expected_hash)
    with _facts() as facts, _decoded(facts, path, actual, mode) as image:
        yield ImageView(image)


def image_copy(path, expected_hash=None, *, mode='RGB'):
    actual = _hash(path, expected_hash)
    with _facts() as facts, _decoded(facts, path, actual, mode) as image:
        facts.counts['compat_full_image_copies'] += 1
        return _owned(image)


def image_region(path, operations, expected_hash=None, *, mode='RGB'):
    """Lookup before decode/transform; preserve the caller's exact pixel recipe.

    Operations: ('crop', box), ('resize', size, resample[, sampling_box]),
    ('convert', mode). A
    recipe is not registered, searched, normalized or downsampled implicitly.
    """
    from PIL import __version__
    actual = _hash(path, expected_hash)
    with _facts() as facts:
        dependencies = facts.pixel_dependencies(actual, {'image': operations, 'mode': mode}, {'Pillow': __version__})
        key = identity(dependencies)
        hit = facts.get(key)
        if hit is not None:
            return _owned(hit)
        # Native palette/transparency metadata must not be flattened by the
        # persistent RGB/L format; retain it only in the current memory scope.
        result = facts.load_pixels(key, dependencies) if mode in ('RGB', 'L', 'RGB_WHITE') else None
        if result is None:
            with _decoded(facts, path, actual, mode) as source, contextlib.ExitStack() as prefixes:
                result = source
                for index, operation in enumerate(operations):
                    def transform(previous=result, op=operation):
                        if op[0] == 'crop' and len(op) == 2:
                            transformed = previous.crop(tuple(op[1]))
                        elif op[0] == 'resize' and len(op) in (3, 4):
                            transformed = previous.resize(tuple(op[1]), op[2], box=tuple(op[3]) if len(op) == 4 else None)
                        elif op[0] == 'convert' and len(op) == 2:
                            transformed = previous.convert(op[1])
                        else:
                            raise ValueError('Unknown finite image operation')
                        facts.counts['image_transforms'] += 1
                        return transformed
                    if index == len(operations) - 1:
                        result = transform()
                    else:
                        prefix = facts.pixel_dependencies(actual, {'image': operations[:index + 1], 'mode': mode}, {'Pillow': __version__})
                        # A common whole-canvas normalization is computed once,
                        # then all leaf crops borrow it without copying it.
                        result = prefixes.enter_context(facts.borrow(identity(prefix), transform,
                            lambda im: im.width * im.height * max(4, len(im.getbands())), lambda im: im.close()))
                if not operations:
                    result = _owned(source)
            if mode in ('RGB', 'L', 'RGB_WHITE'):
                facts.store_pixels(key, dependencies, result)
        if facts.put(key, result, result.width * result.height * max(4, len(result.getbands())), lambda im: im.close()):
            return _owned(result)
        return result


class PackageView:
    __slots__ = ('__archive', '__facts', '__hash')

    def __init__(self, archive, facts, actual):
        self.__archive = archive
        self.__facts = facts
        self.__hash = actual

    def read(self, name):
        from zipfile import ZipInfo
        info = name if isinstance(name, ZipInfo) else self.__archive.getinfo(name)
        key = identity({'package_part':self.__hash,'name':info.filename,
                        'offset':info.header_offset,'crc':info.CRC})
        raw = self.__facts.get(key)
        if raw is None:
            raw = self.__archive.read(info)
            self.__facts.counts['package_part_reads'] += 1
            self.__facts.put(key,raw,max(1,len(raw)))
        return raw

    def namelist(self):
        return self.__archive.namelist()

    def infolist(self):
        return [copy.copy(info) for info in self.__archive.infolist()]

    def getinfo(self, name):
        return copy.copy(self.__archive.getinfo(name))


@contextlib.contextmanager
def package_read(path, expected_hash=None):
    from zipfile import ZipFile
    actual = _hash(path, expected_hash)
    if Path(path).stat().st_size > 256 * 1024 * 1024:
        raise ValueError('PPTX exceeds file budget')
    with _facts() as facts:
        key = identity({'package': actual})

        def create():
            raw = Path(path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != actual:
                raise ValueError('Package changed during shared read')
            archive = ZipFile(io.BytesIO(raw))
            if sum(info.file_size for info in archive.infolist()) > 256 * 1024 * 1024:
                archive.close()
                raise ValueError('Expanded package exceeds budget')
            facts.counts['package_opens'] += 1
            return archive

        with facts.borrow(key, create, lambda _: max(1, Path(path).stat().st_size * 2), lambda z: z.close()) as archive:
            yield PackageView(archive,facts,actual)


def xml_part(path, name, expected_hash=None):
    from lxml import etree as E
    actual = _hash(path, expected_hash)
    with _facts() as facts:
        key = identity({'xml': actual, 'part': name, 'lxml': E.LXML_VERSION,
                        'parser': 'resolve_entities=false,no_network=true'})
        tree = facts.get(key)
        if tree is None:
            with package_read(path, actual) as archive:
                raw = archive.read(name)
            tree = E.fromstring(raw, E.XMLParser(resolve_entities=False, no_network=True))
            facts.counts['xml_parses'] += 1
            facts.put(key, tree, max(1, len(raw) * 8))
        # All existing mutating consumers keep their own tree.
        return copy.deepcopy(tree)


@contextlib.contextmanager
def pdf_document(path, expected_hash=None):
    import pymupdf
    actual = _hash(path, expected_hash)
    with _facts() as facts:
        key = identity({'pdf': actual, 'PyMuPDF': pymupdf.VersionBind})
        size = Path(path).stat().st_size

        def create():
            # Small cached documents are immutable snapshots. Large documents
            # stream afresh, remain fully checked and are closed after use.
            if size * 2 <= facts.budget:
                raw = Path(path).read_bytes()
                if hashlib.sha256(raw).hexdigest() != actual:
                    raise ValueError('PDF changed during shared read')
                doc = pymupdf.open(filename=str(path), stream=raw, filetype='pdf')
            else:
                doc = pymupdf.open(path)
                if digest(path) != actual:
                    doc.close()
                    raise ValueError('PDF changed during open')
            facts.counts['pdf_opens'] += 1
            return doc

        with facts.borrow(key, create, lambda _: max(1, size * 2), lambda doc: doc.close()) as doc:
            yield doc


def pdf_clip(path, canvas, roi, scale):
    """Exact independent raster at the requested scale; shared PDF/pixels only."""
    import numpy as np
    import pymupdf
    from PIL import Image
    actual = _hash(path)
    with _facts() as facts:
        dependencies = facts.pixel_dependencies(actual, {'pdf_clip': list(roi), 'canvas': list(canvas),
                                                         'scale': scale, 'alpha': False, 'colorspace': 'RGB'},
                                               {'PyMuPDF': pymupdf.VersionBind})
        key = identity(dependencies)
        image = facts.get(key)
        owned = image is None
        if image is None:
            image = facts.load_pixels(key, dependencies)
        if image is None:
            with pdf_document(path, actual) as doc:
                if len(doc) != 1:
                    raise ValueError('Actual HD PDF canvas mismatch')
                page = doc[0]
                fx, fy = page.rect.width / canvas[0], page.rect.height / canvas[1]
                if abs(page.rect.height - page.rect.width * canvas[1] / canvas[0]) > .500001 * fx:
                    raise ValueError('Actual HD PDF canvas mismatch')
                x, y, w, h = roi
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale / fx, scale / fy),
                                      clip=pymupdf.Rect(x * fx, y * fy, (x + w) * fx, (y + h) * fy),
                                      alpha=False, colorspace=pymupdf.csRGB)
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                image.info['_resource_metadata'] = {'origin': [pix.x / scale, pix.y / scale], 'scale': scale}
                facts.counts['pdf_clip_rasters'] += 1
            facts.store_pixels(key, dependencies, image)
        if owned:
            owned = not facts.put(key, image, image.width * image.height * 4, lambda im: im.close())
        try:
            return np.asarray(image, dtype=float) / 255, copy.deepcopy(image.info['_resource_metadata'])
        finally:
            if owned:
                image.close()


def resource_library(project):
    """Reuse a task-scoped Library constructor, not an open global DB cursor."""
    from .execution_context import _active
    from .library_store import Library
    scope = _active.get()
    if scope is None:
        return Library(project)
    facts = scope['resources']
    if facts.library is None:
        facts.library = Library(project)
    if facts.library.root != Path(project).expanduser().resolve() / '.lotraAI-build' / 'library':
        raise ValueError('Resource scope cannot change projects')
    return facts.library


def derived_value(path, expected_hash, recipe, create):
    """Scope-only JSON raw facts; never persist a checker's predicate/result."""
    actual = _hash(path, expected_hash)
    with _facts() as facts:
        key = identity(dict(facts.dependencies, raw_value=actual, recipe=recipe))
        value = facts.get(key)
        if value is None:
            value = create()
            facts.put(key, value, max(1, len(canonical(value)) * 4))
        return copy.deepcopy(value)
