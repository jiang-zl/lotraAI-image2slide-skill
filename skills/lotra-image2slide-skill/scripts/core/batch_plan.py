"""Validate the complete finite same-task batch before the first action."""
import re
from pathlib import Path
from .common import digest,safe_path

ALLOWED={
    'context-control':{'status'},'context-usage':{'status'},
    'source-detail':{'scan','report'},'source-repeat':{'scan','report'},
    'neighbor-check':{'compile','report'},'containment-check':{'report'},
    'icon-clarity':{'report'},'office-math':{'report'},
    'quality-loop':{'run','report'},'source-reading':{'report'},
    'object-loop':{'observations','report'},'global-quality':{'observations','report'},
    'connection-geometry':{'report'},'recursive-check':{'report','execute'},
    'frame-plan':{'report','apply'},'semantic-composition':{'report','capture'},
    'workflow-control':{'plan','preflight','profile'},
    'execute-rules':None,'source-text-repair':None,'source-layout-repair':None,
    'source-structure-repair':None,'native-text-fit':None,'native-text-lines':None,
    'next':None,'submit':None,
}
FLAGS={'--request','--out','--configuration'}
PATH_FIELDS=('request','configuration','result')


def owned(task,raw):
    raw=Path(raw)
    path=raw.resolve()if raw.is_absolute()else safe_path(task,str(raw))
    if not path.is_relative_to(task):raise ValueError('Batch cannot read/write another task')
    return path


def prepare(task,request):
    import sci_rebuild
    operations=request.get('operations')
    if not isinstance(operations,list)or not 1<=len(operations)<=32:
        raise ValueError('Finite batch of 1..32 operations required; remaining work stays pending')
    rows=[];seen=set();outputs={};inputs={}
    for row in operations:
        if not isinstance(row,dict)or set(row)-{'id','argv','depends_on','requires_status'}:
            raise ValueError('Explicit finite batch row required')
        name=row.get('id');argv=row.get('argv');needs=row.get('depends_on',[])
        required=row.get('requires_status',{})
        if not isinstance(name,str)or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',name)or name in seen:
            raise ValueError('Unique portable batch ID required')
        if not isinstance(argv,list)or not argv or not all(isinstance(v,str)and v for v in argv):
            raise ValueError('Explicit CLI argument array required')
        if not isinstance(needs,list)or any(not isinstance(v,str)for v in needs)or len(needs)!=len(set(needs))or not set(needs)<=seen:
            raise ValueError('Dependencies must name distinct earlier operations; unknown/cyclic/forward dependencies are invalid')
        if not isinstance(required,dict)or not set(required)<=set(needs)or any(not isinstance(v,str)or not v for v in required.values()):
            raise ValueError('Domain prerequisites need an earlier declared dependency and exact status')
        seen.add(name);expanded=[]
        for arg in argv:
            if arg.startswith('--')and '='in arg:expanded.extend(arg.split('=',1))
            else:expanded.append(arg)
        flags=[a for a in expanded if a.startswith('--')]
        if len(flags)!=len(set(flags))or set(flags)-FLAGS:
            raise ValueError('Only unique supported batch flags are allowed')
        if expanded[0]not in ALLOWED or len(expanded)<2 or owned(task,expanded[1])!=task:
            raise ValueError('Only current-task supported finite operations can be batched')
        expanded[1]=str(task)
        try:args=sci_rebuild.parser().parse_args(expanded)
        except SystemExit as error:raise ValueError('Invalid batch CLI shape for '+name)from error
        allowed=ALLOWED[args.command]
        if allowed is not None and args.operation not in allowed:
            raise ValueError('Batch cannot expand the public finite operation scope')
        refs={}
        for field in PATH_FIELDS:
            raw=getattr(args,field,None)
            if raw is None:continue
            path=owned(task,raw)
            if not path.is_file():raise ValueError('Batch inputs must exist; prepare changed-baseline requests after their actual producer')
            refs[str(path)]=digest(path);setattr(args,field,path);inputs[str(path)]=name
        output=getattr(args,'out',None)
        if output is not None:
            output=owned(task,output)
            if not output.is_relative_to(task/'scratch')or output.exists()or str(output)in outputs:
                raise ValueError('Every output must be a distinct new current-task scratch file')
            outputs[str(output)]=name;args.out=output
        normalized=list(expanded)
        for flag,field in (('--request','request'),('--out','out'),('--configuration','configuration')):
            if flag in normalized:normalized[normalized.index(flag)+1]=str(getattr(args,field))
        if args.command in ('submit','execute-rules','source-text-repair','source-layout-repair','source-structure-repair','native-text-fit','native-text-lines'):
            normalized[2]=str(args.result if args.command=='submit'else args.request)
        rows.append({'id':name,'argv':normalized,'depends_on':needs,'requires_status':required,
                     'inputs':refs,'output':str(output)if output else None})
    if set(inputs)&set(outputs):raise ValueError('A batch cannot overwrite an input or use a not-yet-produced request')
    return rows
