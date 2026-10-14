"""Release only closed, registered Office text-projection PPTX copies."""
from pathlib import Path
from .common import read_json,write_json,digest
from .transient_export import VERSION,_safe

def dispose(root):
    root=Path(root).resolve();rows=[]
    for marker in root.rglob('Pdf-lifecycle.json'):
        if marker.is_symlink() or not marker.resolve().is_relative_to(root):raise ValueError('Projection owner escaped its scope')
        owner=read_json(marker);folder=marker.parent
        if owner.get('schema')!=VERSION or owner.get('status')!='DISPOSED':continue
        proof=folder/'text-ownership.json';pptx=folder/'Text-owners-only.pptx'
        if not pptx.is_file():continue
        if not proof.is_file():raise ValueError('Unbound text projection is protected')
        fact=read_json(proof);candidate=_safe(pptx,folder)
        if (fact.get('schema')!='office-native-text-ownership-1' or fact.get('pptx_hash')!=owner.get('pptx_sha256')
                or digest(owner['pptx'])!=owner['pptx_sha256'] or digest(candidate)!=fact.get('isolated_pptx_hash')):
            raise ValueError('Text projection/source changed before disposal')
        preview=_safe(folder/fact['preview_path'],folder)
        if digest(preview)!=fact.get('preview_hash'):raise ValueError('Actual glyph observation changed before projection disposal')
        row={'status':'DISPOSED_AFTER_DEPENDENTS','sha256':digest(candidate),'bytes_released':candidate.stat().st_size,
            'source_sha256':owner['pptx_sha256'],'producer_sha256':digest(proof),'preview_sha256':digest(preview),
            'recovery':'Actual immutable source PPTX can produce a new projection; retain scalar/glyph observations'}
        candidate.unlink();write_json(folder/'Projection-disposal.json',row);rows.append(row)
    return {'status':'PASS','disposed':rows,'bytes_released':sum(r['bytes_released'] for r in rows)}
