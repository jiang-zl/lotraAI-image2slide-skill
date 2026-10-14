"""Exact inherited native typography, with fresh independent source content.

This route applies only to imported approved drawings. It cannot supply a
source reading for a first reconstruction or treat blurry glyph scores as an
approved font definition. Layout, fonts and original glyph diagnostics remain
independent whole-result checks.
"""
from lxml import etree as E
from .common import digest,safe_path
from .mathml import NS


def report(task,state,candidate):
    approved=state.get('quality_intent',{}).get('approved')
    if not state.get('native_import') or not approved:
        return {'applicable':False,'passed':False,'items':[],'status':'SOURCE_TEXTBOX_READING_REQUIRED'}
    from .inspect import xml,inventory
    from .source_reading import report as source_report
    from .source_text_actions import guard as text_guard
    from .quality_intent import _ref
    current=inventory(xml(safe_path(task,candidate['pptx']['path'])))[0]
    prior=inventory(xml(_ref(task,approved['pptx'])))[0]
    reading=source_report(task,state,candidate);content=reading['items'];rows=[]
    policies=state['quality_intent']['items']
    for name,owner in current.items():
        body=owner['node'].find('p:txBody',NS)
        if body is None or not (body.findall('.//a:t',NS) or body.findall('.//m:t',NS)):continue
        bound=[r for r in content if name in r.get('objects',[])]
        old=prior.get(name,{}).get('node');before=old.find('p:txBody',NS) if old is not None else None
        equal=before is not None and E.tostring(before,method='c14n',exclusive=True)==E.tostring(body,method='c14n',exclusive=True)
        correction=next((r for r in policies if r.get('appearance_target')=='source_content' and r.get('objects')==[name]),None)
        corrected=bool(correction and text_guard(task,state,candidate,correction,approved)['passed'])
        passed=bool(bound) and all(r['passed'] for r in bound) and (equal or corrected)
        rows.append({'object':name,'passed':passed,'source_units':[r['unit'] for r in bound],
          'exact_source_content':bool(bound) and all(r['passed'] for r in bound),
          'native_typography_bytes_preserved':equal,'independent_source_text_constructor':corrected,
          'status':'SOURCE_CONTENT_AND_NATIVE_TYPOGRAPHY_VERIFIED' if passed else 'SOURCE_TEXTBOX_READING_REQUIRED'})
    return {'applicable':True,'passed':reading['passed'] and all(r['passed'] for r in rows),'items':rows,
      'approved_sha256':approved['pptx']['sha256'],'candidate_sha256':candidate['pptx']['sha256'],
      'scope':'Fresh original-only characters/AST and exact saved text-body formatting, or the finite original-text correction. Absolute glyph metrics remain diagnostics; frames/layout/font assets are checked independently.'}
