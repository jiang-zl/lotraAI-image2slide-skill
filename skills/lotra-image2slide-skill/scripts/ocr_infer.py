"""Offline OCR worker. All inference inputs/models are hash-bound local files."""
import argparse, hashlib, json, os, platform, time
from pathlib import Path

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def infer(request,progress=None):
    def mark(phase):
        if progress is not None:progress.write_text(json.dumps({'pid':os.getpid(),'phase':phase,'monotonic':time.monotonic()}),encoding='utf-8')
    mark('STARTING')
    import numpy as np
    import onnxruntime as ort
    from PIL import Image
    from rapidocr import RapidOCR, OCRVersion, ModelType
    import socket
    def offline(*a,**kw):raise RuntimeError('OCR inference is offline; network acquisition is forbidden')
    socket.create_connection=offline
    socket.socket.connect=offline;socket.socket.connect_ex=offline
    if __import__('importlib.metadata').metadata.version('rapidocr')!='3.10.0' or ort.__version__!='1.23.0':
        raise ValueError('Use the shipped and inference-tested OCR engine versions')
    from core.source_contract import finite
    from core.ocr_geometry import inverse_points
    finite(request,'OCR.request')
    models=request['models'];tier=request.get('tier','medium')
    if tier not in ('tiny','small','medium'):raise ValueError('Unknown OCR tier')
    if set(models)!={'det-'+tier,'rec-'+tier}:raise ValueError('Use one complete matched detection/recognition tier')
    for record in models.values():
        if not Path(record['path']).is_file() or sha(record['path'])!=record['sha256']:
            raise ValueError('OCR model missing or hash changed')
    wanted=request.get('provider','CPUExecutionProvider')
    if wanted not in ('CPUExecutionProvider','DmlExecutionProvider','CUDAExecutionProvider','CoreMLExecutionProvider'):
        raise ValueError('Unsupported OCR execution provider')
    if wanted not in ort.get_available_providers():raise ValueError('Requested provider is unavailable: '+wanted)
    batch=request.get('recognition_batch',1)
    if type(batch) is not int or not 1<=batch<=8:raise ValueError('Bounded recognition batch 1..8 required')
    threads=request.get('threads',max(1,min(4,os.cpu_count() or 1)))
    max_side=request.get('max_side_len',4096);max_pixels=request.get('max_pixels',8000000)
    if type(threads) is not int or not 1<=threads<=8 or not 128<=max_side<=4096 or not 16384<=max_pixels<=16000000:
        raise ValueError('Invalid bounded OCR resource budget')
    model_type={'tiny':ModelType.TINY,'small':ModelType.SMALL,'medium':ModelType.MEDIUM}[tier]
    params={'Global.use_cls':False,'Global.log_level':'warning','Global.text_score':0.,
        'Global.max_side_len':max_side,'Global.min_side_len':30,
        'Det.model_path':models['det-'+tier]['path'],'Det.ocr_version':OCRVersion.PPOCRV6,'Det.model_type':model_type,
        'Det.limit_side_len':1280,'Det.limit_type':'max',
        'Rec.model_path':models['rec-'+tier]['path'],'Rec.ocr_version':OCRVersion.PPOCRV6,'Rec.model_type':model_type,
        'Rec.rec_batch_num':batch,
        'EngineConfig.onnxruntime.intra_op_num_threads':threads,
        'EngineConfig.onnxruntime.inter_op_num_threads':1,
        'EngineConfig.onnxruntime.use_dml':wanted=='DmlExecutionProvider',
        'EngineConfig.onnxruntime.use_cuda':wanted=='CUDAExecutionProvider',
        'EngineConfig.onnxruntime.use_coreml':wanted=='CoreMLExecutionProvider'}
    engine=RapidOCR(params=params);items=[];start=time.monotonic();mark('ENGINE_READY')
    for item in request['images']:
        image=Path(item['path'])
        if sha(image)!=item['sha256']:raise ValueError('OCR image binding changed')
        with Image.open(image) as im:
            if im.width*im.height>request.get('max_decoded_pixels',16000000):raise ValueError('Decoded source exceeds memory budget; use source-only host views')
            roi=item.get('roi',[0,0,*im.size]);x,y,w,h=roi
            if min(w,h)<=0 or min(x,y)<0 or x+w>im.width or y+h>im.height:
                raise ValueError('OCR crop must stay inside the source')
            scale=float(item.get('scale',2.))
            if not 1<=scale<=8:raise ValueError('Use bounded source-only enlargement')
            dimensions=(max(1,round(w*scale)),max(1,round(h*scale)))
            if max(dimensions)>max_side or dimensions[0]*dimensions[1]>max_pixels:
                raise ValueError('Enlargement exceeds preallocation budget; execute the program tile plan')
            edges=(x,y,x+w,y+h)
            if all(float(v).is_integer() for v in edges):
                crop=im.crop(edges).convert('RGB').resize(dimensions,Image.Resampling.LANCZOS)
            else:
                # Pillow.crop rounds fractional edges. EXTENT retains the
                # declared source domain; inverse uses actual sampled axes.
                crop=im.convert('RGB').transform(dimensions,Image.Transform.EXTENT,edges,Image.Resampling.BICUBIC)
            scaled_width,scaled_height=crop.size
            axis_scale=[scaled_width/w,scaled_height/h]
            angle=int(item.get('rotation',0))
            if angle not in (0,90,180,270):raise ValueError('Use a declared right-angle text rotation')
            if angle:crop=crop.rotate(angle,expand=True)
            pixels=np.asarray(crop)
        mark('INFERENCE_RUNNING');result=engine(pixels,use_cls=False,return_word_box=False)
        lines=[]
        for box,txt,score in zip(result.boxes if result.boxes is not None else [],result.txts or [],result.scores or []):
            points=np.asarray(box,dtype=float)
            original=np.asarray(inverse_points(points.tolist(),angle,scaled_width,scaled_height,axis_scale,[x,y]))
            if original is not None:
                lo=original.min(0);hi=original.max(0);bounds=[*lo.tolist(),*(hi-lo).tolist()]
            else:bounds=None
            lines.append({'text':txt,'score':float(score),'score_is_probability':False,
                'roi':bounds,'crop_polygon':points.tolist(),
                'words':[{'text':txt,'score':float(score),'roi':bounds}] if bounds else []})
        items.append({'id':item['id'],'image_hash':item['sha256'],'source_roi':roi,'scale':scale,'actual_axis_scale':axis_scale,
            'rotation':angle,'lines':lines,'seconds':result.elapse})
    sessions=[engine.text_det.session.session,engine.text_rec.session.session]
    actual=[s.get_providers() for s in sessions]
    if wanted!='CPUExecutionProvider' and any(wanted not in s for s in actual):
        raise ValueError('Requested accelerator silently fell back before inference')
    mark('DONE')
    return {'schema':'lotra-offline-ocr-1','status':'INFERENCE_EXECUTED','requested_provider':wanted,
        'actual_session_providers':actual,'available_providers':ort.get_available_providers(),
        'tier':tier,'execution_limits':{'crop_batch':1,'recognition_batch':engine.text_rec.rec_batch_num,'max_side_len':max_side,'max_pixels':max_pixels,'threads':threads,'detection_side_len':1280},
        'engine':{'rapidocr':__import__('importlib.metadata').metadata.version('rapidocr'),'onnxruntime':ort.__version__,
                  'python':platform.python_version(),'platform':platform.platform()},
        'model_hashes':{k:v['sha256'] for k,v in models.items()},'items':items,'seconds':time.monotonic()-start,
        'limits':'Recognition scores are not calibrated probabilities. Source readings require spatial binding and host confirmation; OCR is not an acceptance oracle.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();request=json.loads(Path(args.request).read_text(encoding='utf-8-sig'))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    result=infer(request,output.with_suffix('.progress.json'))
    output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'provider':result['requested_provider'],'images':len(result['items']),'seconds':round(result['seconds'],3)}))
