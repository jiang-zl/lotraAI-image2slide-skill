"""Host-launchable finite render worker; no agent or model calls."""
import argparse,sys
from core import render_service
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['serve','job']);p.add_argument('--project',required=True)
    p.add_argument('--seconds',type=int,default=7200);p.add_argument('--request')
    a=p.parse_args()
    if a.operation=='serve':
        if not 1<=a.seconds<=14400:p.error('Owned service duration must be 1..14400 seconds')
        render_service.serve(a.project,a.seconds)
    else:
        if not a.request:p.error('One exact request file is required')
        render_service.execute(a.project,a.request)
