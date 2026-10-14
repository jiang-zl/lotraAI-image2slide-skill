"""One shared logical-owner traversal of native Office compatibility branches.

Choice and Fallback are alternate representations of an owner, not duplicated
slide objects. Retain every branch for integrity/export, and select supported
DrawingML/math only for logical inventory. Unknown unresolved markup fails
closed instead of silently shrinking the reconstruction/checking scope.
"""
import hashlib,copy
from lxml import etree as E
from .mathml import NS

SHAPES={'sp','grpSp','cxnSp','pic','graphicFrame'}
SUPPORTED={NS[k] for k in ('a','p','m','a14')}


def _branch_owners(tree,parent=None):
    result=[]
    for child in active_children(tree):
        meta=child.find('.//p:cNvPr',NS)
        if meta is None:raise ValueError('Compatibility owner has no native identity')
        owner=(meta.get('id'),meta.get('name'),E.QName(child).localname,parent)
        result.append(owner)
        if E.QName(child).localname=='grpSp':result.extend(_branch_owners(child,(meta.get('id'),meta.get('name'))))
        if len(result)>50000:raise ValueError('Compatibility logical inventory budget exhausted')
    return sorted(result,key=repr)


def active_children(tree):
    for node in tree:
        q=E.QName(node)
        if q.namespace==NS['mc'] and q.localname=='AlternateContent':
            # Alternate representations may differ in geometry, but must not
            # hide additional semantic owners in an unselected branch.
            inventories=[]
            for branch in node:
                if branch.tag not in ('{'+NS['mc']+'}Choice','{'+NS['mc']+'}Fallback'):
                    raise ValueError('Unknown Office compatibility branch')
                inventories.append(_branch_owners(branch))
            if inventories and any(owners!=inventories[0] for owners in inventories[1:]):
                raise ValueError('Office compatibility branches contain different logical owners; reconcile every representation before proceeding')
            branches=node.findall('mc:Choice',NS)
            selected=next((b for b in branches if b.get('Requires','').split() and
                all(b.nsmap.get(t) in SUPPORTED for t in b.get('Requires').split())),None)
            if selected is None:selected=node.find('mc:Fallback',NS)
            if selected is None:raise ValueError('Unresolved Office compatibility branch; no complete native inventory is possible')
            yield from active_children(selected)
        elif q.namespace==NS['p']:
            if q.localname in SHAPES:yield node
            elif q.localname not in ('nvGrpSpPr','grpSpPr','extLst'):
                raise ValueError('Unsupported native tree content cannot be omitted from full coverage: '+q.localname)


def semantic_parent(node):
    parent=node.getparent()
    while parent is not None and E.QName(parent).namespace==NS['mc']:
        parent=parent.getparent()
    return parent


def variants(node):
    """Protect all serialized variants without treating Fallback as a second icon."""
    parent=node.getparent()
    if parent is None or E.QName(parent).namespace!=NS['mc']:return None
    wrapper=parent.getparent()
    if wrapper is None or wrapper.tag!='{'+NS['mc']+'}AlternateContent':return None
    rows=[]
    for branch in wrapper:
        rows.append({'branch':E.QName(branch).localname,'requires':branch.get('Requires'),
            'owners':[{'name':n.find('.//p:cNvPr',NS).get('name'),
                       'id':n.find('.//p:cNvPr',NS).get('id'),'tag':E.QName(n).localname}
                      for n in branch if E.QName(n).namespace==NS['p'] and E.QName(n).localname in SHAPES],
            'sha256':hashlib.sha256(E.tostring(branch,method='c14n',exclusive=True)).hexdigest()})
    return {'selected':E.QName(parent).localname,'selected_requires':parent.get('Requires'),
        'wrapper_sha256':hashlib.sha256(E.tostring(wrapper,method='c14n',exclusive=True)).hexdigest(),'branches':rows}


def prune_owners(tree,keep_ids):
    """Private observation/extraction copy; keep every variant of selected IDs."""
    kept=False
    for node in list(tree):
        q=E.QName(node)
        if q.namespace==NS['mc'] and q.localname in ('AlternateContent','Choice','Fallback'):
            own=prune_owners(node,keep_ids)
            if not own:tree.remove(node)
            kept=kept or own
        elif q.namespace==NS['p'] and q.localname in SHAPES:
            if q.localname=='grpSp':own=prune_owners(node,keep_ids)
            else:
                meta=node.find('.//p:cNvPr',NS);own=meta is not None and int(meta.get('id')) in keep_ids
            if not own:tree.remove(node)
            kept=kept or own
    return kept
