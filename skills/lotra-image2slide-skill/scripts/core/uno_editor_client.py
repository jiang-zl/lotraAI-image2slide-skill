"""Run only with the renderer's bundled Python/UNO, after controller startup.

No dependencies on the project Python environment. Input is an explicit local
JSON contract; formulas come from Math's import of saved OMML, never OCR text.
"""
import argparse,hashlib,importlib.util,json,os,sys,time
from pathlib import Path
import uno
from com.sun.star.lang import DisposedException


def main(connection, directory, context=None, probe=False, terminate=True,on_complete=None):
    directory=Path(directory)
    if context is None:
        local=uno.getComponentContext()
        resolver=local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver',local)
        for _ in range(450):
            try:context=resolver.resolve('uno:'+connection+';urp;StarOffice.ComponentContext');break
            except Exception:time.sleep(.1)
    if context is None:raise RuntimeError('Bounded Math editor connection failed')
    desktop=context.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop',context)
    def prop(name,value):
        p=uno.createUnoStruct('com.sun.star.beans.PropertyValue');p.Name=name;p.Value=value;return p
    document=None
    try:
        if probe:
            document=desktop.loadComponentFromURL('private:factory/smath','_blank',0,(prop('Hidden',True),))
            if document is None:raise RuntimeError('Native Math document creation failed')
            formula='sum from {k=1} to n k^2'
            document.Formula=formula
            if document.Formula != formula:raise RuntimeError('Native Math formula was not preserved')
            (directory/'math-probe.json').write_text(json.dumps({'status':'PASS','native_math_service':True,
                'formula':document.Formula,'scope':'backend_startup_only','document_render':'NOT_RUN'})+'\n',encoding='utf-8')
            if on_complete:on_complete()
            return
        plan=json.loads((directory/'editor-plan.json').read_text(encoding='utf-8'))
        spec=importlib.util.spec_from_file_location('lotra_native_font_aliases',Path(__file__).with_name('native_font_aliases.py'))
        aliases=importlib.util.module_from_spec(spec);spec.loader.exec_module(aliases)
        toolkit=context.ServiceManager.createInstanceWithContext('com.sun.star.awt.Toolkit',context)
        device=toolkit.createScreenCompatibleDevice(1,1);device_info=device.getInfo()
        font_plan=plan.get('font_aliases',{'version':aliases.VERSION,'families':{}})
        imported,font_resolution=aliases.native_input(directory,font_plan,[f.Name for f in device.getFontDescriptors()])
        document=desktop.loadComponentFromURL(imported.as_uri(),'_blank',0,
            (prop('Hidden',True),prop('ReadOnly',True),prop('MacroExecutionMode',
             uno.getConstantByName('com.sun.star.document.MacroExecMode.NEVER_EXECUTE')),prop('UpdateDocMode',0)))
        if document is None:raise RuntimeError('Native PPTX import failed')
        observations=[]
        ordinary_fonts=aliases.ordinary_usage(document,font_plan,font_resolution)
        def text_extent(spec):
            # Native editor font advances are layout geometry, not image scores.
            factor=16;px_per_pt=device_info.PixelPerMeterY*.0254/72
            width=0.;parts=[]
            for char in spec['text']:
                script='ea' if ord(char)>=0x2E80 else 'latin'
                face=spec['fonts'].get(script,spec['fonts'].get('latin'))
                for family,row in font_plan['families'].items():
                    if aliases.name_key(face) in {aliases.name_key(n) for n in row['aliases']}:
                        face=font_resolution['resolved_families'][family] or face;break
                if parts and parts[-1][0]==face:parts[-1][1]+=char
                else:parts.append([face,char])
            for face,text in parts:
                fd=uno.createUnoStruct('com.sun.star.awt.FontDescriptor')
                fd.Name=face;fd.Height=round(spec['size']*px_per_pt*factor)
                fd.Weight=150. if spec['bold'] else 100.
                fd.Slant=uno.Enum('com.sun.star.awt.FontSlant','ITALIC' if spec['italic'] else 'NONE')
                width+=device.getFont(fd).getStringWidth(text)/factor*100000/device_info.PixelPerMeterX
            return max(1,round(width)),round(spec['size']*2540/72*1.2)
        def inventory(collection):
            result={}
            for i in range(collection.Count):
                shape=collection.getByIndex(i);result[shape.Name]=shape
                if shape.ShapeType=='com.sun.star.drawing.GroupShape':result.update(inventory(shape))
            return result
        slides={f'ppt/slides/slide{i+1}.xml':inventory(document.DrawPages.getByIndex(i)) for i in range(document.DrawPages.Count)}
        if 'native_saved_math' in plan:
            if plan.get('math_style_scope')!='APPLICATION_SAVED_NATIVE_IMPORT_NO_SOURCE_STYLE_CLAIM' or plan['groups']:
                raise ValueError('Exact application-saved Math import scope required')
            for slide,shapes in slides.items():
                for owner,shape in shapes.items():
                    if shape.ShapeType!='com.sun.star.drawing.OLE2Shape':continue
                    model=shape.Model;info=model.getPropertySetInfo()
                    if not all(info.hasPropertyByName(key) for key in ('Formula','BaseFontHeight','FontNameMath')):continue
                    formula=model.Formula
                    if not formula:raise ValueError('Saved native Math formula was lost')
                    style={key:model.getPropertyValue(key) for key in ('FontNameMath','FontNameVariables','FontNameNumbers','FontNameFunctions','FontNameText','BaseFontHeight')}
                    position=shape.Position;frame=shape.Size
                    imported_frame=[frame.Width,frame.Height]
                    # The application-saved text box extent is not the Math
                    # object's visual area. Painting the OLE into that frame
                    # stretches its glyphs. Use the imported model's intrinsic
                    # area in this private rendering document only; no source
                    # font, size or roundtrip geometry retention is inferred.
                    natural=model.getVisualAreaSize(1);unit=model.getMapUnit(1)
                    if unit==uno.getConstantByName('com.sun.star.util.MeasureUnit.TWIP'):factor=2540/1440
                    elif unit==uno.getConstantByName('com.sun.star.util.MeasureUnit.MM_100TH'):factor=1
                    else:raise RuntimeError('Unknown saved Math editor map unit '+str(unit))
                    natural.Width=round(natural.Width*factor);natural.Height=round(natural.Height*factor)
                    if natural.Width<=0 or natural.Height<=0:raise ValueError('Saved native Math has no positive intrinsic area')
                    shape.setSize(natural);shape.setPosition(position)
                    if model.Formula!=formula or any(model.getPropertyValue(key)!=value for key,value in style.items()):
                        raise ValueError('Saved native Math import altered its formula or style')
                    observations.append({'owner':owner,'slide':slide,'editor':'LibreOffice Math','imported_formula':formula,
                        'style_mode':'application_saved_native_import','source_style_retention':'NOT_QUALIFIED',
                        'source_geometry_retention':'NOT_QUALIFIED','native_imported_style':style,
                        'imported_frame_mm100':imported_frame,'native_size_mm100':[natural.Width,natural.Height],
                        'render_geometry':'INTRINSIC_NATIVE_MATH_AREA_IN_PRIVATE_DOCUMENT',
                        'scope':'Actual native saved-file formula and style unchanged; intrinsic display area is an adapter operation, not saved source geometry retention'})
            if len(observations)!=plan['native_saved_math']['expected_math_objects']:
                raise ValueError('Saved OMML count differs from actual native Math objects')
        for group in plan['groups']:
            shapes=slides[group['slide']]
            first=shapes[group['rows'][0]['segments'][0]['name']]
            position=first.Position;frame=first.Size
            rows=[]
            for row in group['rows']:
                segments=[]
                for spec in row['segments']:
                    shape=shapes[spec['name']]
                    if spec['math']:
                        if shape.ShapeType!='com.sun.star.drawing.OLE2Shape':raise RuntimeError('OMML was not imported into the Math editor')
                        model=shape.Model;formula=model.Formula
                        if not formula:raise RuntimeError('Math editor lost the formula')
                        # Preserve Math's structured serialization exactly inside
                        # outer style commands; never reinterpret it as text.
                        for key in ('FontNameMath','FontNameVariables','FontNameNumbers','FontNameFunctions','FontNameText'):
                            model.setPropertyValue(key,spec['font'])
                        model.BaseFontHeight=max(1,round(spec['size']))
                        model.IsTextMode=bool(group['mixed'])
                        model.Formula='size '+str(spec['size'])+' {color hex '+spec['color']+' {'+formula+'}}'
                        natural=model.getVisualAreaSize(1);unit=model.getMapUnit(1)
                        if unit==uno.getConstantByName('com.sun.star.util.MeasureUnit.TWIP'):factor=2540/1440
                        elif unit==uno.getConstantByName('com.sun.star.util.MeasureUnit.MM_100TH'):factor=1
                        else:raise RuntimeError('Unknown editor map unit '+str(unit))
                        natural.Width=round(natural.Width*factor);natural.Height=round(natural.Height*factor)
                        shape.setSize(natural)
                        observations.append({'owner':group['owner'],'segment':spec['name'],'editor':'LibreOffice Math',
                            'imported_formula':formula,'font':spec['font'],'size_pt':spec['size'],
                            'map_unit':unit,'native_size_mm100':[natural.Width,natural.Height]})
                    else:
                        shape.TextLeftDistance=0;shape.TextRightDistance=0
                        shape.TextUpperDistance=0;shape.TextLowerDistance=0
                        shape.TextWordWrap=False;shape.TextAutoGrowWidth=False;shape.TextAutoGrowHeight=False
                        size=uno.createUnoStruct('com.sun.star.awt.Size');size.Width,size.Height=text_extent(spec);shape.setSize(size)
                    segments.append((shape,shape.Size.Width,shape.Size.Height))
                rows.append((row,segments,sum(s[1] for s in segments),max(s[2] for s in segments)))
            total_height=sum(r[3] for r in rows)
            left,right,top,bottom=group['margins']
            y=position.Y+round(top)
            available_height=frame.Height-top-bottom
            if group['valign']=='ctr':y+=round((available_height-total_height)/2)
            elif group['valign']=='b':y+=round(available_height-total_height)
            for row,segments,width,height in rows:
                x=position.X+round(left);available=frame.Width-left-right
                if row['align']=='ctr':x+=round((available-width)/2)
                elif row['align']=='r':x+=round(available-width)
                for shape,w,h in segments:
                    pos=uno.createUnoStruct('com.sun.star.awt.Point');pos.X=x;pos.Y=y+round((height-h)/2)
                    shape.setPosition(pos);x+=w
                y+=height
        document.storeToURL((directory/'Final.pdf').as_uri(),(prop('FilterName','impress_pdf_Export'),prop('Overwrite',True)))
        if digest(imported)!=font_resolution['native_input_sha256']:raise ValueError('Native font import copy changed during export')
        (directory/'math-editor.json').write_text(json.dumps({'status':'PASS','observations':observations,
            'ordinary_fonts':ordinary_fonts,'font_resolution':font_resolution,
            'canonical_pptx_hash':plan['canonical_pptx_hash'],'editor_input_hash':plan['editor_input_hash'],
            'native_math_preserved':True,'canonical_pptx_modified':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # Closing an embedded-font document/UNO bridge can block after a valid
        # synchronous export. A request-bound acknowledgement lets the owning
        # controller verify exact outputs before stopping only its processes.
        if on_complete:on_complete()
    finally:
        # A headless instance may shut down while its last document closes.
        # This is cleanup only: any export error from the try still propagates.
        try:
            if document is not None:document.close(True)
            if terminate:desktop.terminate()
        except DisposedException:pass


def digest(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def cli():
    parser=argparse.ArgumentParser();parser.add_argument('connection');parser.add_argument('directory',type=Path)
    parser.add_argument('--probe',action='store_true');parser.add_argument('--job',type=Path,required=True);args=parser.parse_args()
    request=args.job.resolve(strict=True);directory=args.directory.resolve(strict=True)
    if request.stat().st_size>65536:raise ValueError('Math job exceeds byte limit')
    job=json.loads(request.read_bytes());operation='probe' if args.probe else 'export'
    expected={'editor-input.pptx','editor-plan.json'} if operation=='export' else set()
    if (job.get('schema')!='lotra-editor-job-1' or job.get('job_id')!=request.parent.name or
        job.get('operation')!=operation or Path(job.get('directory','')).resolve()!=directory or
        job.get('client_sha256')!=digest(__file__) or
        job.get('font_alias_helper_sha256')!=digest(Path(__file__).with_name('native_font_aliases.py')) or
        set(job.get('inputs',{}))!=expected):
        raise ValueError('Subprocess Math request does not match its fixed client/job')
    request_hash=digest(request)
    outputs=('math-probe.json',) if operation=='probe' else ('Final.pdf','math-editor.json')
    if any((directory/name).exists() or (directory/name).is_symlink() for name in outputs):
        raise ValueError('Preserve existing Math operation output')
    def complete():
        if digest(request)!=request_hash:raise ValueError('Math request changed during execution')
        if job['font_alias_helper_sha256']!=digest(Path(__file__).with_name('native_font_aliases.py')):
            raise ValueError('Native font alias helper changed during execution')
        for name,sha in job.get('inputs',{}).items():
            file=directory/name
            if file.is_symlink() or digest(file)!=sha:raise ValueError('Math immutable input changed')
        names=('math-probe.json',) if operation=='probe' else ('Final.pdf','math-editor.json')
        outputs={}
        for name in names:
            file=directory/name
            if file.is_symlink() or not file.is_file() or not file.stat().st_size:raise ValueError('Math output is absent or linked')
            outputs[name]={'sha256':digest(file),'bytes':file.stat().st_size}
        result={'schema':'lotra-editor-job-result-1','job_id':job['job_id'],'operation':operation,
            'request_sha256':request_hash,'status':'PASS','outputs':outputs,
            'completion':'SYNCHRONOUS_OPERATION_COMPLETE_BEFORE_OWNED_CLEANUP'}
        temporary=request.parent/'result.json.part'
        with temporary.open('xb') as stream:
            stream.write((json.dumps(result,sort_keys=True)+'\n').encode());stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,request.parent/'result.json')
    main(args.connection,directory,probe=args.probe,on_complete=complete)


if __name__=='__main__':cli()
