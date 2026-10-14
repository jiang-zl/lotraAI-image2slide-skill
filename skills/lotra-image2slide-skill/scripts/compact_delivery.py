"""Run the lossless size operator; numerical storage proof is not acceptance."""
import argparse,json
from pathlib import Path
from core.delivery_size import optimize_pptx,optimize_pdf
from core.common import write_json
p=argparse.ArgumentParser();p.add_argument('kind',choices=('pptx','pdf'));p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--receipt',type=Path,required=True)
a=p.parse_args();result=(optimize_pptx if a.kind=='pptx' else optimize_pdf)(a.input,a.output);write_json(a.receipt,result)
print(json.dumps({k:v for k,v in result.items() if k in ('status','selection','before_bytes','after_bytes','removed_media','duplicate_media')}))
