"""Run only with the renderer's bundled Python/UNO, after controller startup.

No dependencies on the project Python environment. Input is an explicit local
JSON contract; formulas come from Math's import of saved OMML, never OCR text.
"""
import json,sys,time
from pathlib import Path
import uno
from com.sun.star.lang import DisposedException


def main(connection, directory, context=None, probe=False, terminate=True):
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
            return
        plan=json.loads((directory/'editor-plan.json').read_text(encoding='utf-8'))
        document=desktop.loadComponentFromURL((directory/'editor-input.pptx').as_uri(),'_blank',0,
            (prop('Hidden',True),prop('ReadOnly',True),prop('MacroExecutionMode',
             uno.getConstantByName('com.sun.star.document.MacroExecMode.NEVER_EXECUTE')),prop('UpdateDocMode',0)))
        if document is None:raise RuntimeError('Native PPTX import failed')
        observations=[]
        toolkit=context.ServiceManager.createInstanceWithContext('com.sun.star.awt.Toolkit',context)
        device=toolkit.createScreenCompatibleDevice(1,1);device_info=device.getInfo()
        def text_extent(spec):
            # Native editor font advances are layout geometry, not image scores.
            factor=16;px_per_pt=device_info.PixelPerMeterY*.0254/72
            width=0.;parts=[]
            for char in spec['text']:
                script='ea' if ord(char)>=0x2E80 else 'latin'
                face=spec['fonts'].get(script,spec['fonts'].get('latin'))
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
        (directory/'math-editor.json').write_text(json.dumps({'status':'PASS','observations':observations,
            'canonical_pptx_hash':plan['canonical_pptx_hash'],'editor_input_hash':plan['editor_input_hash'],
            'native_math_preserved':True,'canonical_pptx_modified':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:
        # A headless instance may shut down while its last document closes.
        # This is cleanup only: any export error from the try still propagates.
        try:
            if document is not None:document.close(True)
            if terminate:desktop.terminate()
        except DisposedException:pass


if __name__=='__main__':main(*sys.argv[1:3],probe=sys.argv[3:]==['--probe'])
