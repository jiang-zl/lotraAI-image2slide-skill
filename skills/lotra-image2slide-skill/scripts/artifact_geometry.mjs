// Optional official Artifact Tool provider. It constructs only declared
// native shapes at source coordinates; it never owns typography or layout.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [requestPath, outputPrefix, modulePath] = process.argv.slice(2);
if (![requestPath, outputPrefix, modulePath].every(p => p && path.isAbsolute(p)))
  throw new Error('Absolute request, new output prefix and official module paths required');
const bytes = await fs.readFile(requestPath);
const request = JSON.parse(bytes.toString('utf8'));
const presets = new Set(['rect','roundRect','ellipse','triangle','diamond','rightArrow','leftRightArrow','wedgeRoundRectCallout','can','cloud','hexagon','parallelogram','trapezoid','chevron','cube']);
if (!request.source_hash || !request.canvas || !Array.isArray(request.shapes) || !request.shapes.length || request.shapes.length > 128)
  throw new Error('Bounded source-specific geometry request required');
const {Presentation, PresentationFile} = await import(pathToFileURL(modulePath).href);
const p = Presentation.create({slideSize:{width:request.canvas.width,height:request.canvas.height}});
const slide = p.slides.add(); slide.background.fill='#FFFFFF';
const names=new Set();
for (const item of request.shapes) {
  if (!presets.has(item.preset) || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(item.id) || names.has(item.id))
    throw new Error('Unique native preset shape required');
  names.add(item.id);
  const [left,top,width,height]=item.bbox;
  if (![left,top,width,height].every(Number.isFinite) || Math.min(left,top)<0 || Math.min(width,height)<=0 || left+width>request.canvas.width || top+height>request.canvas.height)
    throw new Error('Declared shape outside source canvas');
  const style=item.style ?? {};
  const adj=item.guides?.map(([name,formula])=>({name,formula}));
  slide.shapes.add({geometry:item.preset,name:item.id,position:{left,top,width,height},
    fill:style.fill ? '#'+style.fill : 'none',
    line:{fill:style.stroke ? '#'+style.stroke:'none',width:(style.line_width ?? 1)*96/72},
    adjustmentList:adj});
}
const pptx=outputPrefix+'.pptx';const receipt=outputPrefix+'.receipt.json';
await fs.mkdir(path.dirname(outputPrefix),{recursive:true});
for (const file of [pptx,receipt]) {
  try {await fs.stat(file);throw new Error('Output already exists: '+file);} catch(e) {if(e.code!=='ENOENT')throw e;}
}
await (await PresentationFile.exportPptx(p)).save(pptx);
const hash=data=>crypto.createHash('sha256').update(data).digest('hex');
await fs.writeFile(receipt,JSON.stringify({provider:'official_artifact_tool',request_hash:hash(bytes),
  pptx_hash:hash(await fs.readFile(pptx)),source_hash:request.source_hash,
  scope:'declared_native_geometry_only',shape_ids:[...names],canvas:request.canvas},null,2),'utf8');
process.stdout.write(JSON.stringify({pptx,receipt,scope:'declared_native_geometry_only'})+'\n');
