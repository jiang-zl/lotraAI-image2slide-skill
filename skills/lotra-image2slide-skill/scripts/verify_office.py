#!/usr/bin/env python3
"""Independent, read-only validation of actual M0 saved Office probe artifacts."""

import argparse
import copy
from pathlib import Path
import unicodedata
from lxml import etree as E
from core.common import digest, read_json, write_json
from core.fixtures import formulas
from core.inspect import inventory, xml, parse_math_container, NS


def italic_identifiers(ast):
    """PowerPoint serializes ASCII Latin as mathematical italic on professionalize.

    Only the known italic Latin/Greek alphabets are normalized here. Bold, double-struck,
    superscript/subscript characters and arbitrary compatibility glyphs are not.
    This is an explicit probe-notation equivalence, not general AST normalization.
    """
    if isinstance(ast,dict):
        value={k:italic_identifiers(v) for k,v in ast.items()}
        if value.get("op")=="seq" and all(v.get("op")=="token" for v in value["items"]):
            return {"op":"token","text":"".join(v["text"] for v in value["items"])}
        return value
    if isinstance(ast,list):
        return [italic_identifiers(v) for v in ast]
    if isinstance(ast,str):
        return "".join(unicodedata.normalize("NFKC",c) if 0x1D434<=ord(c)<=0x1D467 or 0x1D6E2<=ord(c)<=0x1D71B else c for c in ast)
    return ast


def verify(original, native_dir, equation_dir, output):
    native_dir,equation_dir=Path(native_dir),Path(equation_dir)
    raw=read_json(native_dir/"operations.json")
    editor=read_json(equation_dir/"operations.json")
    native_deck=native_dir/"Office_roundtrip.pptx"
    equation_deck=equation_dir/"Equation_editor_roundtrip.pptx"
    records=[]
    def add(id,passed,detail):
        records.append({"check_id":id,"status":"PASS" if passed else "FAIL","evidence":detail})
    for name,data,path in [("native",raw,native_deck),("editor",editor,equation_deck)]:
        add(name+"_hash",data.get("input_sha256")==digest(original) and data.get("output_sha256")==digest(path),str(path))
    nodes,_=inventory(xml(native_deck))
    ops={r.get("operation"):r for r in raw["operations"]}
    title="".join(nodes["Title"]["node"].xpath(".//a:t/text()",namespaces=NS))
    add("text_saved_reopened",title=="Native API edit persisted",str(native_deck)+"#Title")
    original_group=nodes["Device"]["node"]
    add("group_original_preserved",E.QName(original_group).localname=="grpSp",str(native_deck)+"#Device")
    copied_parts=[r for r in raw["reopened"] if r["name"] in ("Chassis","FrontPanel")]
    add("natural_parts_after_ungroup",{p["name"]:p["type"] for p in copied_parts}=={"Chassis":1,"FrontPanel":6},copied_parts)
    # Duplicate part names can exist after ungroup; look for the copied root chassis.
    tree=xml(native_deck).find("p:cSld/p:spTree",NS)
    copied_chassis=next((n for n in tree.findall("p:sp",NS) if n.find("p:nvSpPr/p:cNvPr",NS).get("name")=="Chassis"),None)
    fill=None if copied_chassis is None else copied_chassis.find("p:spPr/a:solidFill/a:srgbClr",NS)
    add("part_fill_saved",fill is not None and fill.get("val")=="FF0000",str(native_deck)+"#Chassis")
    link=ops.get("connector_move_follow",{})
    detail=link.get("detail",{})
    add("connector_follow",link.get("status")=="EXECUTED" and detail.get("source")=="EndpointA" and detail.get("target")=="EndpointB" and detail.get("before")!=detail.get("after"),detail)
    old_nodes,_=inventory(xml(original))
    old_curve=old_nodes["Curve"]["node"].find("p:spPr/a:custGeom",NS)
    new_curve=nodes["Curve"]["node"].find("p:spPr/a:custGeom",NS)
    add("bezier_saved_change",new_curve is not None and E.tostring(new_curve)!=E.tostring(old_curve) and new_curve.find(".//a:cubicBezTo",NS) is not None,str(native_deck)+"#Curve")
    eq_nodes,_=inventory(xml(equation_deck))
    expected=copy.deepcopy(formulas())
    expected["scripts"]["base"]["text"]="g"
    expected["fraction"]["denominator"]["denominator"]["text"]="z"
    expected["sum"]["body"]["text"]="β"
    expected["root"]["body"]["text"]="β+2"
    expected["accent"]["body"]["text"]="w"
    expected["matrix"]["rows"][1][1]["text"]="e"
    expected["cases"]["rows"][1][0]["text"]="1"
    exercised={r.get("object","").removeprefix("Equation_") for r in editor["operations"] if r.get("editor")=="PowerPoint native EquationProfessional"}
    for suffix in expected:
        if suffix not in exercised:continue
        obj="Equation_"+suffix
        omath=eq_nodes[obj]["node"].find("p:txBody/a:p/a14:m/m:oMathPara/m:oMath",NS)
        try:
            actual=italic_identifiers(parse_math_container(omath))
            passed=actual==expected[suffix]
        except (ValueError,TypeError,AttributeError) as exc:
            actual={"error":str(exc)}
            passed=False
        add(obj+"_native_editor_structure",passed,{"expected":expected[suffix],"actual":actual,"path":str(equation_deck)})
    report={"checker_version":"office-probe-verifier-0.1.0","status":"PASS" if all(r["status"]=="PASS" for r in records) else "FAIL",
            "scope":"M0 probe operations only; not arbitrary icon/formula coverage or reconstruction acceptance",
            "platform":"Windows","office_version":raw.get("office_version"),"office_build":raw.get("office_build"),"checks":records,
            "binding":{"original_hash":digest(original),"native_deck_hash":digest(native_deck),"equation_deck_hash":digest(equation_deck),
                       "native_operations_hash":digest(native_dir/"operations.json"),"editor_operations_hash":digest(equation_dir/"operations.json"),
                       "native_preview_hash":digest(native_dir/"After.png"),"equation_preview_hash":digest(equation_dir/"After.png")},
            "formula_families_exercised":sorted(exercised),
            "remaining":["Unexercised math families: "+", ".join(sorted(set(expected)-exercised)),"macOS not tested","Independent scientific-source quality not accepted"]}
    write_json(output,report)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("original",type=Path)
    p.add_argument("native_dir",type=Path)
    p.add_argument("equation_dir",type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    r=verify(a.original,a.native_dir,a.equation_dir,a.out)
    print(r["status"])
    raise SystemExit(0 if r["status"]=="PASS" else 2)
