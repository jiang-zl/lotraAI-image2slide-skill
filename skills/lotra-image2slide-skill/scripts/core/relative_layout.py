"""Source-bound relationships of saved painted contours, not group frames.

The host confirms original ownership/intent. Programs bind, solve and gate
independent relations. Unsupported geometry stays unmeasured; it is never
certified by a convenient frame or a whole-page similarity score.
"""
import copy
import math
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import digest, identity, read_json, safe_path, write_json
from .mathml import NS
from .native_commit import _nodes, _sp

VERSION = "relative-layout-1"
KINDS = {"separation", "containment", "alignment", "intentional_overlap"}


def _interval(value):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)
            or value[0] > value[1]):
        raise ValueError("Freeze a finite ordered source interval")
    return value


def validate(contract, state):
    if (contract.get("schema") != VERSION or contract.get("kind") not in KINDS
            or contract.get("source_hash") != state["source"]["sha256"]
            or contract.get("canvas") != state["source_size"]
            or not contract.get("id") or not contract.get("source_evidence")
            or not contract.get("source_view") or not contract.get("source_bounds")):
        raise ValueError("A relation needs its original hash, canvas, ownership and observed evidence")
    names = contract.get("objects")
    if not isinstance(names, list) or len(names) != 2 or len(set(names)) != 2:
        raise ValueError("Bind two distinct actual semantic owners")
    if any(n not in contract["source_bounds"] for n in names):
        raise ValueError("Both participants need original owned paint bounds")
    for box in contract["source_bounds"].values():
        if (not isinstance(box, list) or len(box) != 4
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in box)
                or min(box[2:]) <= 0):
            raise ValueError("Original paint bounds are positive xywh")
    _interval(contract["interval"])
    if contract["kind"] in ("separation", "alignment") and contract.get("axis") not in ("x", "y"):
        raise ValueError("A directional relation needs its source axis")
    if contract["kind"] == "separation" and contract["interval"][0] < 0:
        raise ValueError("Separate source ink cannot have a negative minimum gap")
    if contract["kind"] == "containment":
        if contract.get("body", {}).get("shape") not in ("rect", "rounded_rect"):
            raise ValueError("Declare the actual body domain; tail/group extent is not an interior")
        radius = contract["body"].get("radius_ratio", 0)
        if type(radius) not in (int, float) or not 0 <= radius <= .5:
            raise ValueError("Freeze the source-supported rounded body ratio")
        if contract["interval"][0] < 0:
            raise ValueError("Content must clear the body's painted inner border")
    if contract["kind"] == "alignment" and any(
            contract.get(k) not in ("min", "center", "max") for k in ("anchor_a", "anchor_b")):
        raise ValueError("Bind explicit source anchors")
    if contract["kind"] == "intentional_overlap" and contract.get("paint_order") not in ("a_before_b", "b_before_a"):
        raise ValueError("Observed overlap needs its source paint order")
    return contract


def contracts(task, state):
    rows = []
    for ref in state.get("relative_layout", {}).get("contracts", []):
        path = safe_path(task, ref["path"])
        if digest(path) != ref["sha256"]:
            raise ValueError("Frozen source relationship changed")
        row = validate(read_json(path), state)
        view = safe_path(task, row["source_view"]["path"])
        if digest(view) != row["source_view"]["sha256"]:
            raise ValueError("Original relationship observation changed")
        from .external_sync import native_contract
        rows.append(native_contract(state, row))
    for unit in state.get("quality", {}).get("units", {}).values():
        measure = unit.get("relation", {}).get("measurement", {})
        if measure.get("kind") == "relative_layout":
            row=validate(measure["contract"],state)
            if digest(safe_path(task,row["source_view"]["path"]))!=row["source_view"]["sha256"]:
                raise ValueError("Original compiled relationship observation changed")
            rows.append(row)
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Distinct relationship identities required")
    # Source-only program measurements outrank a manually transcribed box.
    # Preserve the declared tolerance width and raw source contract; expose
    # the correction basis instead of moving valid native geometry to bad data.
    if state.get('source_connection_graph') and state.get('connection_contract'):
        rows=copy.deepcopy(rows)
        from .source_connections import load,original_filled_bounds
        from .connection_geometry import _load_contract
        graph=load(task,state);parts={p['id']:p for p in graph['parts']}
        mapping={n:parts[p] for r in _load_contract(task,state)['items'] for n,p in zip(r['objects'],r['source_parts'])}
        measured={}
        for row in rows:
            if row['kind']!='alignment':continue
            original=copy.deepcopy(row);proof=[]
            for name in row['objects']:
                part=mapping.get(name)
                points=part.get('source_points',[]) if part else []
                axis_aligned=len(points)==2 and min(abs(points[1][i]-points[0][i]) for i in (0,1))<.01
                if part and part['kind']=='filled_arrow' and axis_aligned:
                    if name not in measured:measured[name]=original_filled_bounds(task,state,part)
                    observation=measured[name];row['source_bounds'][name]=observation['bounds'];proof.append(observation)
            if proof:
                axis=0 if row['axis']=='x' else 1
                def anchor(name,kind):
                    box=row['source_bounds'][name];return box[axis]+{'min':0,'center':.5,'max':1}[kind]*box[axis+2]
                expected=anchor(row['objects'][1],row['anchor_b'])-anchor(row['objects'][0],row['anchor_a'])
                tolerance=(original['interval'][1]-original['interval'][0])/2
                row['interval']=[expected-tolerance,expected+tolerance]
                row['derived_source_measurement']={'source_graph':state['source_connection_graph'],'observations':proof,
                    'prior_source_bounds':original['source_bounds'],'prior_interval':original['interval'],
                    'scope':'Original-only numeric source correction; prior tolerance is retained and raw frozen source requirements remain available.'}
    return rows


def historical_raw(row):
    """Recover the exact frozen input for replay, never for current acceptance."""
    raw=copy.deepcopy(row);derived=raw.pop('derived_source_measurement',None)
    if derived:
        raw['source_bounds']=derived['prior_source_bounds'];raw['interval']=derived['prior_interval']
    return raw

def _bind_locked(task, request):
    from . import agent_runtime as a
    task, state = a._state(task)
    if state.get("active_candidate") or state.get("packet") or not state.get("selected"):
        raise ValueError("Bind new source relations between completed actual drawing actions")
    if request.get("baseline_hash") != state["selected"]["pptx"]["sha256"]:
        raise ValueError("Bind the authoritative selected result")
    rows = request.get("contracts", [])
    if not 1 <= len(rows) <= 16:
        raise ValueError("Bind at most16 independently observed relations at a time")
    ledger = state.setdefault("relative_layout", {"contracts": [], "history": []})
    known = {r["id"] for r in contracts(task, state)}
    selected = safe_path(task, state["selected"]["pptx"]["path"])
    frames = painted_bounds(selected, state["source_size"])
    folder = task / "source" / "relative-layout"; folder.mkdir(exist_ok=True)
    for row in rows:
        validate(row, state)
        if row["id"] in known: raise ValueError("Keep original contracts immutable; correct with a new identity")
        if any(n not in frames for n in row["objects"]):
            raise ValueError("Original intent must bind existing saved semantic owners")
        ref = row["source_view"]; path = safe_path(task, ref["path"])
        if digest(path) != ref["sha256"]: raise ValueError("Use the actually viewed original window")
        file = folder / (identity(row) + ".json"); write_json(file, row)
        ledger["contracts"].append(a._file(task, file)); known.add(row["id"])
    ledger["history"].append({"event": "source_bound", "baseline": request["baseline_hash"],
                             "relations": [r["id"] for r in rows]})
    a._save(task, state)
    return report(task, state, state["selected"], force=True)


def bind(task, request):
    from . import agent_runtime as a
    with a.writer(Path(task).resolve()):
        return _bind_locked(task,request)


def _union(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes: return None
    x = min(b[0] for b in boxes); y = min(b[1] for b in boxes)
    return [x, y, max(b[0]+b[2] for b in boxes)-x, max(b[1]+b[3] for b in boxes)-y]


def _curve_axis(points):
    """Exact extrema of one quadratic/cubic axis, including real endpoints."""
    values = [points[0], points[-1]]; roots = []
    if len(points) == 4:
        p0,p1,p2,p3 = points
        aa = -p0+3*p1-3*p2+p3; bb = 2*(p0-2*p1+p2); cc = p1-p0
        if abs(aa) < 1e-14:
            if abs(bb) > 1e-14: roots = [-cc/bb]
        elif bb*bb-4*aa*cc >= 0:
            d = math.sqrt(bb*bb-4*aa*cc); roots = [(-bb+d)/(2*aa),(-bb-d)/(2*aa)]
    elif len(points) == 3:
        p0,p1,p2 = points
        if abs(p0-2*p1+p2)>1e-14: roots = [(p0-p1)/(p0-2*p1+p2)]
    for t in roots:
        if 0 < t < 1:
            values.append(sum(math.comb(len(points)-1,i)*(1-t)**(len(points)-1-i)*t**i*p
                              for i,p in enumerate(points)))
    return min(values), max(values)


def _path_box(geometry):
    boxes = []
    for path in geometry.findall("a:pathLst/a:path", NS):
        width,height = float(path.get("w",1)),float(path.get("h",1))
        if width <= 0 or height <= 0: return None
        points = []; current = None; start = None
        for command in path:
            tag = E.QName(command).localname
            pts = [(float(p.get("x"))/width,float(p.get("y"))/height) for p in command]
            if tag in ("moveTo", "lnTo"):
                current = pts[0]; start = current if tag=="moveTo" else start; points.append(current)
            elif tag in ("cubicBezTo", "quadBezTo") and current is not None:
                control = [current]+pts
                xs = _curve_axis([p[0] for p in control]); ys = _curve_axis([p[1] for p in control])
                points.extend([(xs[0],ys[0]),(xs[1],ys[1])]); current = pts[-1]
            elif tag == "close": current = start
            else: return None  # arc/guide expressions need another observed provider
        if not points: return None
        boxes.append([min(p[0] for p in points),min(p[1] for p in points),
                      max(p[0] for p in points)-min(p[0] for p in points),
                      max(p[1] for p in points)-min(p[1] for p in points)])
    return _union(boxes)


def painted_bounds(pptx, size):
    """Actual saved contour bounds incl. stroke, composed parent transforms.

    No fallback from unsupported text/pictures/presets to a nominal group box.
    Pixel appearance and semantic ownership remain actual host observations.
    """
    with ZipFile(pptx) as z:
        root = E.fromstring(z.read("ppt/slides/slide1.xml"))
        canvas = E.fromstring(z.read("ppt/presentation.xml")).find("p:sldSz",NS)
    px,py = size[0]/int(canvas.get("cx")),size[1]/int(canvas.get("cy"))
    result = {}; order = 0
    def visit(parent, mapping, unsupported=False):
        nonlocal order
        sx,sy,tx,ty = mapping
        from .native_markup import active_children
        for node in active_children(parent):
            tag = E.QName(node).localname
            if tag not in ("sp","grpSp","cxnSp","graphicFrame","pic"): continue
            name = node.find(".//p:cNvPr",NS).get("name"); order += 1
            props = _sp(node); xf = None if props is None else props.find("a:xfrm",NS)
            entry = {"box": None, "frame": None, "stroke_px": 0., "order": order,
                     "members": [name], "error": None}; result[name] = entry
            if xf is None:
                entry["error"] = "UNSUPPORTED_SAVED_GEOMETRY"; continue
            off,ext = xf.find("a:off",NS),xf.find("a:ext",NS)
            x,y = tx+sx*float(off.get("x")),ty+sy*float(off.get("y"))
            w,h = sx*float(ext.get("cx")),sy*float(ext.get("cy"))
            frame = [x*px,y*py,w*px,h*py]; entry["frame"] = frame
            rotated = unsupported or int(xf.get("rot",0))%21600000 != 0
            if tag == "grpSp":
                co,ce = xf.find("a:chOff",NS),xf.find("a:chExt",NS)
                if co is None or ce is None or min(int(ce.get("cx")),int(ce.get("cy")))<=0:
                    entry["error"]="UNSUPPORTED_GROUP_FRAME"; continue
                nsx,nsy = w/float(ce.get("cx")),h/float(ce.get("cy"))
                visit(node,(nsx,nsy,x-nsx*float(co.get("x")),y-nsy*float(co.get("y"))),rotated)
                children = [result[c.find(".//p:cNvPr",NS).get("name")] for c in node
                            if E.QName(c).localname in ("sp","grpSp","cxnSp","graphicFrame","pic")]
                entry["members"] += [n for c in children for n in c["members"]]
                entry["box"] = _union(c["box"] for c in children)
                if any(c["error"] for c in children): entry["error"]="UNMEASURED_OWNED_CHILD"
                continue
            if rotated or xf.get("flipH")=="1" or xf.get("flipV")=="1":
                entry["error"]="UNSUPPORTED_ROTATED_OR_FLIPPED_PAINT"; continue
            has_text=any((t.text or "").strip() for t in node.findall("p:txBody//a:t",NS)) or bool(node.xpath(".//a14:m",namespaces=NS))
            if tag in ("pic","graphicFrame") or has_text:
                entry["error"]="NEEDS_BOUND_ACTUAL_INK_MASK"; continue
            line = props.find("a:ln",NS)
            preset=props.find('a:prstGeom',NS)
            if preset is not None:entry['preset']=preset.get('prst')
            if line is not None and line.find('a:noFill',NS) is None:
                entry['stroke_px']=float(line.get('w',12700))*max(abs(sx)*px,abs(sy)*py)
            # Centerline extrema do not describe arrowheads, gaps in dashed
            # paint or effects. Route these to actual native owner mattes.
            if (props.find('a:effectLst',NS) is not None or props.find('a:effectDag',NS) is not None
                    or line is not None and (any(n.get('type','none')!='none' for n in line
                        if E.QName(n).localname in ('headEnd','tailEnd'))
                        or line.find('a:custDash',NS) is not None
                        or line.find('a:prstDash',NS) is not None and line.find('a:prstDash',NS).get('val')!='solid')):
                entry['error']='NEEDS_BOUND_ACTUAL_INK_MASK';continue
            stroke = line is not None and line.find("a:noFill",NS) is None
            filled = any(props.find("a:"+t,NS) is not None for t in ("solidFill","gradFill","pattFill","grpFill"))
            if not filled and not stroke: continue
            sw = float(line.get("w",12700))*max(abs(sx)*px,abs(sy)*py) if stroke else 0.
            entry["stroke_px"]=sw
            preset = props.find("a:prstGeom",NS)
            if preset is not None: entry["preset"]=preset.get("prst")
            geom = props.find("a:custGeom",NS); norm = None
            if geom is not None: norm = _path_box(geom)
            else:
                preset = props.find("a:prstGeom",NS)
                if preset is not None and preset.get("prst") in ("rect","roundRect","ellipse","triangle","rtTriangle","line"):
                    norm=[0.,0.,1.,1.]
            if norm is None: entry["error"]="UNSUPPORTED_PAINTED_CONTOUR"; continue
            # Paint envelopes are exact for supported path extrema/straight
            # shapes; a stroked round/ellipse envelope is not its filled area.
            entry["box"]=[frame[0]+norm[0]*frame[2]-sw/2,frame[1]+norm[1]*frame[3]-sw/2,
                          norm[2]*frame[2]+sw,norm[3]*frame[3]+sw]
            if props.find("a:prstGeom",NS) is not None:
                entry["preset"]=props.find("a:prstGeom",NS).get("prst")
    visit(root.find("p:cSld/p:spTree",NS),(1.,1.,0.,0.))
    return result


def _rounded_clearance(box, body, radius):
    cx,cy = body[0]+body[2]/2,body[1]+body[3]/2
    rx,ry = body[2]/2-radius,body[3]/2-radius
    distances=[]
    for x in (box[0],box[0]+box[2]):
        for y in (box[1],box[1]+box[3]):
            qx,qy=abs(x-cx)-rx,abs(y-cy)-ry
            distances.append(math.hypot(max(qx,0),max(qy,0))+min(max(qx,qy),0)-radius)
    return -max(distances)


def _measure(row, frames):
    a,b = row["objects"]; kind = row["kind"]
    if a not in frames or b not in frames: return {"status":"required_unmeasured","error":"SAVED_OWNER_MISSING"}
    first,second=frames[a],frames[b]
    if kind=="containment":
        box=first["box"]; frame=second["frame"]
        # Callout tail is deliberately excluded: only its actual preset body.
        if first["error"] or frame is None: return {"status":"required_unmeasured","error":first["error"] or "BODY_MISSING"}
        if second.get("preset") not in ("rect","roundRect","wedgeRoundRectCallout") or (
                second["error"] and second["error"]!="UNSUPPORTED_PAINTED_CONTOUR"):
            return {"status":"required_unmeasured","error":"BODY_SHAPE_MISMATCH"}
        # Wedge presets do not have a general paint envelope; the saved
        # unchanged native frame/line define their explicitly bound body.
        stroke=second["stroke_px"]
        body=[frame[0]+stroke/2,frame[1]+stroke/2,frame[2]-stroke,frame[3]-stroke]
        preset=second.get("preset")
        if (row["body"]["shape"]=="rect" and preset!="rect" or
                row["body"]["shape"]=="rounded_rect" and preset not in ("roundRect","wedgeRoundRectCallout")):
            return {"status":"required_unmeasured","error":"BODY_DOMAIN_DIFFERS_FROM_SAVED_PRESET"}
        radius=min(body[2:])*row["body"].get("radius_ratio",0)
        value=_rounded_clearance(box,body,radius)
        values={"clearance_px":value,"outside_ink_extent_px":max(0.,-value)}
    else:
        if first["error"] or second["error"] or first["box"] is None or second["box"] is None:
            return {"status":"required_unmeasured","error":first["error"] or second["error"] or "EMPTY_PAINT"}
        aa,bb=first["box"],second["box"]
        if kind=="separation":
            axis=0 if row["axis"]=="x" else 1; value=bb[axis]-aa[axis]-aa[axis+2]
            values={"gap_px":value}
        elif kind=="alignment":
            axis=0 if row["axis"]=="x" else 1; factors={"min":0.,"center":.5,"max":1.}
            value=(bb[axis]+factors[row["anchor_b"]]*bb[axis+2]-
                   aa[axis]-factors[row["anchor_a"]]*aa[axis+2])
            values={"anchor_offset_px":value}
        else:
            value=max(0,min(aa[0]+aa[2],bb[0]+bb[2])-max(aa[0],bb[0]))*max(
                0,min(aa[1]+aa[3],bb[1]+bb[3])-max(aa[1],bb[1]))
            order=first["order"]<second["order"] if row["paint_order"]=="a_before_b" else second["order"]<first["order"]
            values={"paint_envelope_overlap_px2":value,"correct_paint_order":int(order)}
    lower,upper=row["interval"]; violation=max(0.,lower-value,value-upper)
    values.update(interval_violation_px=violation,
                  source_relative_error_px=abs(value-(lower+upper)/2))
    passed=violation<=1e-7 and values.get("correct_paint_order",1)==1
    return {"id":row["id"],"kind":kind,"objects":row["objects"],"values":values,
            "interval":row["interval"],"status":"minimum_met" if passed else "below_minimum",
            "measurement_domain":"actual_saved_native_painted_contour_envelope"}


def measure(row,frames):
    result=_measure(row,frames)
    return {"id":row["id"],"kind":row["kind"],"objects":row["objects"],**result}


def _touched(row, frames, allowed):
    return bool(set(allowed)&{n for name in row["objects"] for n in frames.get(name,{}).get("members",[name])})


def guard_saved(task,state,pptx,baseline=None,allowed=None):
    rows=contracts(task,state)
    if not rows: return {"status":"NO_BOUND_SOURCE_RELATIONS","relations":[]}
    frames=painted_bounds(pptx,state["source_size"])
    required=[r for r in rows if baseline is None or _touched(r,frames,allowed or {})]
    from .frame_plan import layout_target
    values=[layout_target(task,state,pptx,r,frames) or measure(r,frames) for r in required]
    report_={"status":("LAYOUT_BLOCKED" if any(v["status"]=="below_minimum" for v in values)
                       else "REQUIRES_ACTUAL_INK_EVIDENCE" if any(v["status"]=="required_unmeasured" for v in values)
                       else "BOUND_RELATIONS_MET"),
             "pptx_hash":digest(pptx),"relations":values,"scoped_relation_ids":[r["id"] for r in required],
             "limits":"Saved native contour gate; actual appearance and source intent still need bounded host observation."}
    write_json(Path(pptx).parent/"relative-layout-guard.json",report_)
    if report_["status"]=="LAYOUT_BLOCKED":
        bad=[r.get("id",r.get("error")) for r in values if r["status"]!="minimum_met"]
        raise ValueError("Source-relative layout blocks this proposal: "+", ".join(bad))
    return report_



def evaluate_contract(task,state,candidate,row,frames=None):
    validate(row,state)
    frames=frames or painted_bounds(safe_path(task,candidate["pptx"]["path"]),state["source_size"])
    from .frame_plan import layout_target
    authorized=layout_target(task,state,safe_path(task,candidate['pptx']['path']),row,frames)
    if authorized is not None:return authorized
    result=measure(row,frames)
    if result["status"]!="required_unmeasured":return result
    from .layout_ink import evaluate as actual_ink
    observed=actual_ink(task,state,candidate,row,frames)
    if observed is not None:return observed
    manifest=safe_path(task,candidate["pptx"]["path"]).parent/"relative-layout-masks.json"
    if not manifest.is_file():return result
    data=read_json(manifest)
    if (data.get("schema")!="relative-layout-ink-provider-1"
            or data.get("source_hash")!=state["source"]["sha256"]
            or data.get("candidate_hash")!=candidate["pptx"]["sha256"]):
        raise ValueError("Actual ink provider must bind this original and saved PPTX")
    binding=[r for r in data.get("bindings",[]) if r.get("id")==row["id"]]
    if not binding:return result
    if len(binding)!=1 or not binding[0].get("ownership_evidence"):
        raise ValueError("One source-observed ink ownership binding per relation")
    ref=binding[0]["ink_spacing"];file=safe_path(task,ref["path"])
    if digest(file)!=ref["sha256"]:raise ValueError("Actual ink contract changed")
    contract=read_json(file)
    if not candidate.get("render") or contract.get("candidate_pptx",{}).get("sha256")!=candidate["pptx"]["sha256"]:
        raise ValueError("Mask provider requires the rendered actual saved owner")
    receipt=safe_path(task,candidate["render"]["path"])
    if contract.get("candidate_render_receipt",{}).get("sha256")!=digest(receipt):
        raise ValueError("Actual mask renderer binding differs")
    from .ink_spacing import check,_bound_file,_mask
    from .saved_ppt_diff import snapshot
    from PIL import Image
    import numpy as np
    checked=check(contract,file.parent)
    if checked["status"] not in ("PASS_ALTERNATIVE_RENDER_SPACING_ONLY","PASS_POWERPOINT_RENDER_SPACING_ONLY"):
        raise ValueError("Resolve actual mask provenance/spacing before retention")
    source_image=_bound_file(file.parent,contract["source_preview"])
    with Image.open(safe_path(task,state["source"]["path"])) as original,Image.open(source_image) as normalized:
        size=normalized.size
        expected=original.convert("RGB").resize(size,Image.Resampling.LANCZOS)
        if normalized.convert("RGB").tobytes()!=expected.tobytes():
            raise ValueError("The ink reference must be exact full-canvas original sampling")
    scale=(size[0]/state["source_size"][0],size[1]/state["source_size"][1])
    if abs(scale[0]-scale[1])*max(state["source_size"])>1:
        raise ValueError("Actual mask provider changed the original canvas mapping")
    pairs=[pair for pair in contract["pairs"] if pair["id"]==row["id"]]
    if len(pairs)!=1:raise ValueError("Locate this exact independent relation mask pair")
    pair=pairs[0];saved=snapshot(safe_path(task,candidate["pptx"]["path"]))
    patched=copy.deepcopy(frames)
    for suffix,name in zip(("a","b"),row["objects"]):
        paths=pair["candidate_object_paths"][suffix]
        allowed=set(frames[name]["members"])
        if any(path not in saved["objects"] or not any(path.endswith("/"+n) for n in allowed) for path in paths):
            raise ValueError("Actual mask owner expanded beyond its frozen semantic participant")
        source_mask=_mask(file.parent,pair["masks"]["source_"+suffix],size)
        ys,xs=np.nonzero(source_mask)
        source_box=[xs.min()/scale[0],ys.min()/scale[1],
                    (xs.max()-xs.min()+1)/scale[0],(ys.max()-ys.min()+1)/scale[1]]
        if row["kind"]!="containment" or suffix=="a":
            if any(abs(x-y)>2 for x,y in zip(source_box,row["source_bounds"][name])):
                raise ValueError("Original mask differs from its frozen owned paint extent")
        mask=_mask(file.parent,pair["masks"]["candidate_"+suffix],size)
        ys,xs=np.nonzero(mask)
        patched[name]["box"]=[xs.min()/scale[0],ys.min()/scale[1],
                            (xs.max()-xs.min()+1)/scale[0],(ys.max()-ys.min()+1)/scale[1]]
        patched[name]["error"]=None
    result=measure(row,patched)
    result["measurement_domain"]="actual_saved_owner_ink_masks_on_one_original_canvas"
    result["ink_provider_hash"]=digest(manifest)
    return result


def mirror_native_positions(scene,pptx,allowed):
    """Synchronize exact authorized positions, preserving all other scene data."""
    result=copy.deepcopy(scene)
    frames=painted_bounds(pptx,[scene["canvas"]["width"],scene["canvas"]["height"]])
    indices={"bbox.left":0,"bbox.top":1,"bbox.width":2,"bbox.height":3}
    for node in result["objects"]:
        for field in allowed.get(node["id"],[]):
            if field in indices and frames.get(node["id"],{}).get("frame") is not None:
                axis=indices[field];node["bbox"][axis]=frames[node["id"]]["frame"][axis]
    return result


def report(task,state,candidate,force=False):
    rows=contracts(task,state);pptx=safe_path(task,candidate["pptx"]["path"])
    if digest(pptx)!=candidate["pptx"]["sha256"]: raise ValueError("Saved layout candidate changed")
    actual=False
    if candidate.get('preview') and candidate.get('render'):
        preview=safe_path(task,candidate['preview']['path']);render=safe_path(task,candidate['render']['path'])
        if digest(preview)!=candidate['preview']['sha256'] or digest(render)!=candidate['render']['sha256']:
            raise ValueError('Actual layout preview or renderer receipt bytes changed')
        receipt=read_json(render)
        if receipt.get('pptx_hash')!=candidate['pptx']['sha256'] or receipt.get('preview_hash')!=candidate['preview']['sha256']:
            raise ValueError('Actual layout render no longer binds the native drawing and preview')
        actual=True
    from .semantic_composition import _cached_capture
    capture_validity={key:_cached_capture(task,row,state) for key,row in state.get('semantic_composition',{}).get('captures',{}).items()}
    manifest=Path(pptx).parent/"relative-layout-masks.json"
    basis={"pptx":digest(pptx),"contracts":identity(rows),"implementation":digest(Path(__file__)),
           "frame_plan":state.get('frame_plan'),
           "preview":candidate.get('preview'),"render":candidate.get('render'),
           "host_contexts":state.get('semantic_composition',{}).get('actual_host_contexts'),
           "route":state.get('capabilities',{}).get('fingerprint'),
           "environment_epoch":state.get('semantic_composition',{}).get('environment_epoch',0),
           "capture_validity":capture_validity,
           "capture_inventory":identity(state.get('semantic_composition',{}).get('captures',{})),
           "ink_implementation":digest(Path(__file__).with_name('layout_ink.py')),
           "actual_ink_provider":digest(manifest) if manifest.is_file() else None}
    file=Path(pptx).parent/("relative-layout-"+identity(basis)[:12]+".json")
    if file.is_file() and not force: return read_json(file)
    frames=painted_bounds(pptx,state["source_size"]);values=[evaluate_contract(task,state,candidate,r,frames) for r in rows]
    result={"schema":"relative-layout-report-1","basis":basis,"actual_host_render_bound":actual,
            "relations":values,"status":"minimum_met" if all(v["status"]=="minimum_met" for v in values) else "below_or_unmeasured",
            "limits":"Each source-bound relation is independent. Envelopes are not pixel-mask IoU or a semantic/full-page certificate."}
    write_json(file,result);return result


def retention_guard(task,state,candidate,allowed):
    guard_saved(task,state,safe_path(task,candidate["pptx"]["path"]),state.get("selected"),allowed)
    actual=report(task,state,candidate,force=True)
    affected=set((candidate.get("relative_layout_guard") or {}).get("scoped_relation_ids",[]))
    unresolved=[r for r in actual["relations"] if r.get("id") in affected and r["status"]!="minimum_met"]
    if unresolved:
        raise ValueError("Resolve each affected source relation before retention; missing geometry cannot be waived")
    if contracts(task,state) and not actual["actual_host_render_bound"]:
        raise ValueError("Retain layout only after its actual saved result has been rendered")
    return actual


def propose(task,request):
    """Solve one existing native leaf translation against all its bound peers."""
    from . import agent_runtime as a
    task,state=a._state(task);selected=state.get('active_candidate') or state["selected"]
    if request.get("baseline_hash")!=selected["pptx"]["sha256"]: raise ValueError("Stale proposal baseline")
    target=request["object"];axes=request.get("axes",["y"])
    if not axes or not set(axes)<={"x","y"}: raise ValueError("Explicit position axes required")
    pptx=safe_path(task,selected["pptx"]["path"]);frames=painted_bounds(pptx,state["source_size"])
    # Use the same fixed-canvas actual owner evidence as the final gate.
    # The solver translates a measured envelope; it never guesses text ink.
    for row in contracts(task,state):
        observed=evaluate_contract(task,state,selected,row,frames)
        for proof in observed.get('ink_evidence',[]):
            frames[proof['object']]['box']=proof['paint_bounds']
            frames[proof['object']]['error']=None
    if target not in frames or frames[target]["error"] or frames[target]["box"] is None:
        raise ValueError("Resolve this owner's painted geometry before position solving")
    rows=[r for r in contracts(task,state) if target in r["objects"]]
    if not rows: raise ValueError("No original-bound relation for this target")
    limit=request.get("max_translation_px",12)
    if type(limit) not in (int,float) or not math.isfinite(limit) or limit<=0:
        raise ValueError("Finite positive translation scope required")
    ranges={axis:[-float(limit),float(limit)] for axis in axes}
    desired={axis:0. for axis in axes};supported=0
    for row in rows:
        kind=row["kind"];aa,bb=row["objects"];value=measure(row,frames)
        if value["status"]=="required_unmeasured": raise ValueError("A bound relationship is unmeasured")
        if kind in ("separation","alignment") and row["axis"] in axes:
            axis=row["axis"];current=value["values"]["gap_px" if kind=="separation" else "anchor_offset_px"]
            sign=1 if target==bb else -1;lo,hi=[(x-current)/sign for x in row["interval"]]
            low,high=min(lo,hi),max(lo,hi);ranges[axis]=[max(ranges[axis][0],low),min(ranges[axis][1],high)]
            desired[axis]=(low+high)/2;supported+=1
        elif kind=="containment" and target==aa:
            box=frames[aa]["box"];frame=frames[bb]["frame"];margin=frames[bb]["stroke_px"]/2+sum(row["interval"])/2
            for axis in axes:
                k=0 if axis=="x" else 1
                low=frame[k]+margin-box[k];high=frame[k]+frame[k+2]-margin-box[k]-box[k+2]
                ranges[axis]=[max(ranges[axis][0],low),min(ranges[axis][1],high)]
                anchor=row.get("target_top_left")
                if anchor is not None: desired[axis]=anchor[k]-box[k]
            supported+=1
        else:
            raise ValueError("This relation needs a source-specific bounded pose proposal, not a translation guess")
    if not supported or any(lo>hi for lo,hi in ranges.values()):
        return {"status":"INFEASIBLE_WITH_CURRENT_WRITE_SCOPE","object":target,"feasible_intervals":ranges,
                "next":"Keep frozen peers; explain the conflicting source constraints before expanding a user grant."}
    deltas={axis:min(max(desired[axis],lo),hi) for axis,(lo,hi) in ranges.items()}
    proposed=copy.deepcopy(frames);entry=proposed[target]
    for axis,delta in deltas.items():
        k=0 if axis=="x" else 1;entry["box"][k]+=delta;entry["frame"][k]+=delta
    if any(measure(r,proposed)["status"]!="minimum_met" for r in rows):
        # A containment interval can also have an upper clearance bound.
        # Search only the finite solver-owned feasible interval endpoints and
        # midpoint, never candidate pixels or arbitrary host coordinates.
        import itertools
        choices={axis:sorted({lo,(lo+hi)/2,hi,deltas[axis]}) for axis,(lo,hi) in ranges.items()}
        valid=[]
        for values in itertools.product(*(choices[axis] for axis in axes)):
            trial=copy.deepcopy(frames)
            for axis,delta in zip(axes,values):
                k=0 if axis=='x' else 1;trial[target]['box'][k]+=delta;trial[target]['frame'][k]+=delta
            if all(measure(r,trial)['status']=='minimum_met' for r in rows):valid.append(dict(zip(axes,values)))
        if not valid:
            return {"status":"NEEDS_SOURCE_SPECIFIC_PROPOSAL","object":target,"reason":"No finite endpoint/midpoint translation meets every source relation."}
        deltas=min(valid,key=lambda v:(sum(x*x for x in v.values()),tuple(v[a] for a in axes)))
    return {"status":"BOUNDED_TRANSLATION_PROPOSAL_NOT_APPLIED","baseline_hash":request["baseline_hash"],
            "object":target,"source_delta_px":deltas,"feasible_intervals":ranges,"relation_ids":[r["id"] for r in rows],
            "required_grants":["bbox.left" if axis=="x" else "bbox.top" for axis in axes],
            "next":"Use the existing exact native proposal or authorized local edit; this never grants itself write authority."}


def discover(state):
    """Bounded original-part adjacency suggestions; never infer source intent."""
    units=[u for u in state.get("quality",{}).get("units",{}).values() if u["profile"]!="relation" and u.get("objects")]
    rows=[]
    for owner in sorted({u["owner"] for u in units}):
        own=[u for u in units if u["owner"]==owner]
        for first in own:
            x,y,w,h=first["roi"];neighbors=[]
            for second in own:
                if second["id"]==first["id"] or set(first["objects"])&set(second["objects"]): continue
                xx,yy,ww,hh=second["roi"]
                xgap=max(0,x-xx-ww,xx-x-w);ygap=max(0,y-yy-hh,yy-y-h)
                gap=math.hypot(xgap,ygap)
                if gap<=12:neighbors.append((gap,second))
            for gap,second in sorted(neighbors,key=lambda pair:(pair[0],pair[1]["id"]))[:2]:
                pair=sorted([first["id"],second["id"]])
                if not any(r["parts"]==pair for r in rows):
                    rows.append({"owner":owner,"parts":pair,"objects":[first["objects"],second["objects"]],
                                 "basis":"nearby original natural-part ROIs; not painted bounds",
                                 "status":"SOURCE_INTENT_REQUIRES_CONFIRMATION"})
    return {"schema":"relative-layout-discovery-1","candidates":rows,
            "next":"View source pairs in batches<=8. Bind only critical observed separation/interior/alignment/intentional-overlap; do not create blanket anti-overlap rules."}
