"""Shipped conditional construction defaults, independent of task history."""
import copy
import math
from .common import ROOT,read_json,digest,safe_path,identity
from .source_contract import finite

def validate_current(value, source_hash, source_size, owner_roi):
    """A catalog locator is evidence for this original and this source owner."""
    if not isinstance(value,dict) or not isinstance(value.get('model',{}),dict):
        raise ValueError('Typed natural recipe parameters and model required')
    locators=[]
    if 'source_traits' in value:locators.append(value['source_traits'])
    evidence=value.get('model',{}).get('source_evidence')
    if isinstance(evidence,dict) and 'current_source' in evidence:
        locators.append(evidence['current_source'])
    for traits in locators:
        if not isinstance(traits,dict) or traits.get('source_hash')!=source_hash:
            raise ValueError('Natural source traits must bind the current original')
        roi=traits.get('source_roi')
        if (not isinstance(roi,(list,tuple)) or len(roi)!=4
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in roi)):
            raise ValueError('A finite current source ROI is required')
        x,y,w,h=roi;ox,oy,ow,oh=owner_roi;epsilon=1e-6
        if (min(w,h)<=0 or min(x,y)<-epsilon or x+w>source_size[0]+epsilon
                or y+h>source_size[1]+epsilon or x<ox-epsilon or y<oy-epsilon
                or x+w>ox+ow+epsilon or y+h>oy+oh+epsilon):
            raise ValueError('Natural source ROI must lie inside its current source owner')
    return value

def compatible(traits):
    finite(traits,'source_traits')
    if (not isinstance(traits,dict) or not isinstance(traits.get('source_hash'),str)
            or len(traits['source_hash'])!=64 or not traits.get('source_roi') or not traits.get('evidence')
            or traits.get('status') not in ('observed','inferred')):
        raise ValueError('Current source-bound anatomy, pose and uncertainty are required')
    catalog=read_json(ROOT/'config/natural-components.json')
    return [r for r in catalog['items'] if r['family']==traits.get('family')
        and r['roles']==traits.get('roles') and all(traits.get(k)==v for k,v in r['properties'].items() if k!='construction')
        and traits.get('purpose') in r['purpose'] and not traits.get('explicit_style_override')]

def parameters(value):
    """An explicit source model wins. Otherwise select a compatible default."""
    if value.get('model'):return copy.deepcopy(value)
    traits=value.get('source_traits',{});choices=compatible(traits)
    if len(choices)!=1:raise ValueError('No unique source-compatible default; declare a source-supported natural model')
    row=choices[0];path=safe_path(ROOT,row['path'])
    if digest(path)!=row['sha256']:raise ValueError('Shipped natural mother changed')
    model=read_json(path)
    model['source_evidence']={'current_source':copy.deepcopy(traits),'catalog_id':row['id'],
        'catalog_version':row['version'],'catalog_sha256':row['sha256'],
        'basis':'Current source classification selects a compatible regular construction reference'}
    # Anatomy is fixed by compatibility. Current source palette may override
    # the reference per role without changing shared geometry.
    palette=traits.get('palette',{})
    for part in model['parts']:
        if part['role'] in palette:
            colour=palette[part['role']]
            if not isinstance(colour,str) or len(colour.lstrip('#'))!=6 or any(c not in '0123456789abcdefABCDEF' for c in colour.lstrip('#')):
                raise ValueError('Use a measured six-digit RGB palette')
            part['style']['fill']=colour.lstrip('#')
    return {**copy.deepcopy(value),'model':model,'fit':'contain','stroke_units':'local_pixels'}

def packet(component):
    matched=component.get('semantic_class') in ('wireless_vehicle','top_view_vehicle','vehicle_icon')
    catalog=read_json(ROOT/'config/natural-components.json')
    if not catalog['items']:
        return {'catalog_version':catalog['schema'],'candidates':[],
            'basis':'No personal task model is shipped. Use the current original or an explicitly selected project-private constructor; neither supplies current source evidence.'}
    return {'catalog_version':catalog['schema'],'current_owner_matches':matched,
        'scope':'Current-source compatible natural owners or recursive children of a mixed component; the catalog does not classify the whole owner.',
        'execution_rule':'Every declared vehicle body/window leaf needs its own constructed natural family root, including mixed scenes and cache reuse. Graphic wireless signals require native/vector contours. Saved native anatomy is reconciled again at the whole-inventory gate.',
        'candidates':[{k:r[k] for k in ('id','family','roles','properties','purpose')} for r in catalog['items']],
        'return':('method' if matched else 'Compatible recursive child method, or mixed raw method recipe_instances[{id,source_roi,source_note,parts,method}]')+'{recipe:wireless_vehicle,parameters:{source_traits:{source_hash,source_roi,evidence,status,family,roles,view,signal_layout,purpose},pose_degrees,source_container?,source_anchor?}}',
        'basis':'Classify the current source. The program selects, verifies and instantiates the compatible shipped mother; no historical approval phrase or local asset lookup is required.'}
