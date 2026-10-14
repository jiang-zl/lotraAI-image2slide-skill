"""Copy only image relationships owned by the selected saved component.

SVG and its Office compatibility preview are transferred together. Other media,
active content and external links are not hidden symbol dependencies.
"""
from hashlib import sha256
from pptx.opc.package import Part
from pptx.opc.constants import RELATIONSHIP_TYPE as RT

R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'

def transfer(element, source, target, cache=None):
    if cache is None:
        cache=getattr(target.package,'_lotra_owned_resources',None)
        if cache is None:
            cache={};target.package._lotra_owned_resources=cache
    for node in element.iter():
        for attribute,value in list(node.attrib.items()):
            if not attribute.startswith('{'+R+'}'):
                continue
            if attribute.rsplit('}',1)[-1] not in ('embed','id'):
                raise ValueError('Saved component has an external relationship')
            rel=source.rels[value]
            from .vector_asset import MASTER_REL,MASTER_NS,inspect_svg,master_bytes
            if rel.is_external or rel.reltype not in (RT.IMAGE,MASTER_REL):
                raise ValueError('Reusable artwork accepts owned images or explicit pure vector masters only')
            part=rel.target_part
            if rel.reltype==MASTER_REL:
                if node.tag!='{'+MASTER_NS+'}vectorMaster' or part.content_type not in ('application/xml','application/gzip'):
                    raise ValueError('Self-contained pure SVG master binding required')
                master_bytes(part.blob,node.get('compression'),node.get('sha256'))
            assetkey=(rel.reltype,part.content_type,sha256(part.blob).hexdigest())
            key=(str(target.partname),*assetkey)
            if key not in cache:
                if part.content_type=='image/svg+xml' or rel.reltype==MASTER_REL:
                    from .vector_asset import inspect_svg
                    if rel.reltype!=MASTER_REL:inspect_svg(part.blob)
                    package=target.package
                    owned=cache.get(assetkey)
                    if owned is None:
                        name=('/ppt/lotra/vector%d.svgz' if part.content_type=='application/gzip' else '/ppt/lotra/vector%d.xml') if rel.reltype==MASTER_REL else '/ppt/media/vector%d.svg'
                        owned=Part(package.next_partname(name),part.content_type,package,blob=part.blob);cache[assetkey]=owned
                    cache[key]=target.relate_to(owned,rel.reltype)
                else:
                    import io
                    _,cache[key]=target.get_or_add_image_part(io.BytesIO(part.blob))
            node.set(attribute,cache[key])
    return cache
