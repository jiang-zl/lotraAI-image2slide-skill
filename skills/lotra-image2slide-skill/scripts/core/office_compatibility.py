"""Office-specific package rules beyond XML/schema validity; never repairs inputs."""
from pathlib import Path
import zipfile
from lxml import etree as E
from .common import digest
from .mathml import NS


def validate(pptx):
    failures=[]; slides=0; shapes=0
    with zipfile.ZipFile(pptx) as package:
        names=package.namelist()
        if len(names)!=len(set(names)):raise ValueError('Ambiguous duplicate PPTX members')
        if package.testzip():raise ValueError('PPTX CRC check failed')
        for name in names:
            if not name.startswith('ppt/slides/slide') or not name.endswith('.xml'):continue
            root=E.fromstring(package.read(name));slides+=1
            # Office writes editable Math in MC Choice with a raster fallback.
            # IDs repeated across mutually exclusive branches are one logical object.
            for alternate in root.xpath('//mc:AlternateContent',namespaces=NS):
                branches=list(alternate)
                chosen=next((n for n in branches if E.QName(n).localname=='Choice'),branches[0] if branches else None)
                for branch in branches:
                    if branch is not chosen:alternate.remove(branch)
            ids=root.xpath('//p:cNvPr/@id',namespaces=NS);shapes+=len(ids)
            if len(ids)!=len(set(ids)):failures.append({'part':name,'rule':'unique-native-object-ids'})
            for node in root.xpath('//p:cxnSp[p:spPr/a:custGeom]',namespaces=NS):
                info=node.find('p:nvCxnSpPr/p:cNvPr',NS)
                failures.append({'part':name,'object':info.get('name') if info is not None else None,
                    'rule':'Office connectors require preset geometry; use an unfilled native freeform for an unbound arbitrary path'})
    if failures:raise ValueError('OFFICE_COMPATIBILITY_BLOCKED: '+str(failures))
    return {'status':'PASS','policy':'office-package-compatibility-1.36.0','pptx_sha256':digest(pptx),
            'slides':slides,'objects':shapes,'scope':'known Office package constraints; actual application roundtrip is separate'}


def freeform_route(shape):
    """Keep identity/style/path; never silently remove live endpoint connections."""
    node=shape._element
    if node.tag!='{'+NS['p']+'}cxnSp':return
    nv=node.find('p:nvCxnSpPr',NS);props=nv.find('p:cNvCxnSpPr',NS)
    if len(props):raise ValueError('SOURCE_DECISION_REQUIRED: arbitrary route with attached ports needs a supported preset route')
    node.tag='{'+NS['p']+'}sp';nv.tag='{'+NS['p']+'}nvSpPr';props.tag='{'+NS['p']+'}cNvSpPr'
    sp=node.find('p:spPr',NS)
    for item in list(sp):
        if E.QName(item).localname in ('solidFill','gradFill','pattFill','blipFill','grpFill','noFill'):sp.remove(item)
    index=next((i for i,n in enumerate(sp) if E.QName(n).localname in ('ln','effectLst','effectDag','scene3d','sp3d','extLst')),len(sp))
    sp.insert(index,E.Element('{'+NS['a']+'}noFill'))
