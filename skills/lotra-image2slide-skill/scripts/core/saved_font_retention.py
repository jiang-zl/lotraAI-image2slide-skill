"""Exact saved text/font retention for native edits containing no new text."""
from zipfile import ZipFile
from lxml import etree as E
from .mathml import NS
from .common import digest


def verify(before,after):
    from .inspect import xml,inventory
    old,dup0=inventory(xml(before));new,dup1=inventory(xml(after))
    if dup0 or dup1:raise ValueError('Ambiguous saved font owner')
    def text(nodes):
        return {name:E.tostring(row['node'],method='c14n',exclusive=True)
                for name,row in nodes.items() if row['node'].tag.endswith('}sp')
                and (row['node'].find('.//a:t',NS) is not None or row['node'].find('.//m:t',NS) is not None)}
    a,b=text(old),text(new)
    if a!=b:raise ValueError('A non-text donor changed/added/removed saved native text or math')
    with ZipFile(before) as z0,ZipFile(after) as z1:
        fonts={n:z0.read(n) for n in z0.namelist() if n.startswith('ppt/fonts/')}
        if fonts!={n:z1.read(n) for n in z1.namelist() if n.startswith('ppt/fonts/')}:
            raise ValueError('Native component commit changed existing embedded font resources')
        for name in ('ppt/presentation.xml','ppt/_rels/presentation.xml.rels'):
            if z0.read(name)!=z1.read(name):raise ValueError('Saved presentation/font references changed')
    return {'binding':{'passed':True,'status':'EXACT_SAVED_NATIVE_TEXT_AND_FONT_REFERENCES_RETAINED',
                       'owners':len(a),'baseline_sha256':digest(before)},
            'embedding':{'status':'EXISTING_EMBEDDED_FONT_BYTES_PRESERVED','font_parts':len(fonts),
                         'scope':'Byte preservation plus subsequent actual rendering; no independent compressed EOT decoding claim'}}
