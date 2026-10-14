"""Small explicit math AST → DrawingML math; no LaTeX or image fallback."""

from lxml import etree as E
import re
import unicodedata


def encoded_math_letter(char):
    name=unicodedata.name(char,'')
    return (name.startswith('MATHEMATICAL ') or name.startswith(('SCRIPT ','BLACK-LETTER ','DOUBLE-STRUCK '))) and char.isalpha()

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
      "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
      "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def el(qualified_name, **attrs):
    prefix, local = qualified_name.split(":")
    return E.Element(f"{{{NS[prefix]}}}{local}", attrib={k: str(v) for k, v in attrs.items()})


def child(parent, qualified_name, **attrs):
    node = el(qualified_name, **attrs)
    parent.append(node)
    return node


def canonical_ast(value):
    """Normalize layout-only syntax without changing operators or token order.

    A seq emits consecutive OMML siblings: its nesting and singleton wrapper
    are not serialized. Preserve script/fraction/delimiter boundaries instead.
    """
    if isinstance(value,list):return [canonical_ast(v) for v in value]
    if not isinstance(value,dict):return value
    result={k:canonical_ast(v) for k,v in value.items()}
    if result.get('op')=='token' and result.get('normal') is False:
        # OMML absence of m:nor is the mathematical default, not a different
        # AST from an explicitly declared normal=False source variable.
        result.pop('normal')
    if result.get('op')=='token' and not result.get('literal'):
        text=result['text']
        # A comma's run boundary/font is typography, not a new mathematical
        # operand. Preserve its exact position and all script boundaries while
        # comparing an original mixed index k,i with native k / comma / i runs.
        if not result.get('normal',False) and ',' in text and any(c.isalpha() for c in text):
            pieces=re.split('(,)',text)
            return canonical_ast({'op':'seq','items':[{**result,'text':piece,
                **({'normal':True} if piece==',' else {})} for piece in pieces if piece]})
        if not result.get('normal',False) and re.search(r'[0-9]',text) and not re.fullmatch(r'[0-9., ]+',text):
            # Office can merge adjacent mathematical runs (K / + / 1 -> K+1).
            # Digits remain upright mathematical tokens regardless of that
            # serialization boundary. Keep operators, order and script scope;
            # do not normalize an explicitly normal prose/identifier run.
            pieces=re.split(r'([0-9]+(?:[.,][0-9]+)*)',text)
            return canonical_ast({'op':'seq','items':[{**result,'text':piece} for piece in pieces if piece]})
        if text and re.fullmatch(r'[0-9., ]+',text):result['normal']=True
    if result.get('op')=='token' and not result.get('normal',False):
        result['text']=re.sub(r'\s+','',result['text'])
    if result.get('op')=='seq':
        items=[]
        for item in result['items']:
            items.extend(item['items'] if item.get('op')=='seq' else [item])
        result['items']=items
        if len(items)==1:return items[0]
    return result


def math_node(ast, font="Cambria Math", size=20, font_policy="native_math"):
    if font_policy not in ("native_math","source_typeface","isolated_script_comma"):
        raise ValueError("Explicit native math font policy required")
    op = ast["op"]
    if op == "token":
        if not isinstance(ast.get("text"), str) or not ast["text"]:
            raise ValueError("Math token must be nonempty")
        text=re.sub(r'\s+','',ast['text']) if not ast.get('normal',False) else ast['text']
        if font_policy=='isolated_script_comma' and not ast.get('normal',False) and ',' in text and any(c.isalpha() for c in text):
            # Never change the input AST. Isolate the observed comma as one
            # upright, normal-font native run inside the same OMML argument.
            # Variables retain native mathematical metrics and script layout.
            output=[]
            for segment in re.split('(,)',text):
                if not segment:continue
                token={**ast,'text':segment}
                if segment==',':token['normal']=True
                output.extend(math_node(token,'Times New Roman' if segment==',' else font,size,
                    'native_math'))
            return output
        # OMML stores an ASCII letter plus its mathematical script. Encoded
        # supplementary-plane script letters may silently disappear in Office
        # when emitted as unqualified m:t. Preserve the input AST; split only
        # the serialization, never the scientific token or its coordinates.
        runs=[]
        for char in text:
            name=unicodedata.name(char,'')
            base=unicodedata.normalize('NFKD',char)
            script='script' if encoded_math_letter(char) and 'SCRIPT' in name and len(base)==1 and base.isascii() else None
            style='b' if script and 'BOLD' in name else 'p' if script else None
            if runs and runs[-1][1:]==(script,style):runs[-1]=(runs[-1][0]+base if script else runs[-1][0]+char,script,style)
            else:runs.append((base if script else char,script,style))
        if any(script for _,script,_ in runs):
            output=[]
            for segment,script,style in runs:
                token={**ast,'text':segment}
                nodes=math_node(token,font,size,font_policy)
                for node in nodes:
                    if script:
                        props=node.find('m:rPr',NS)
                        if props is None:props=el('m:rPr');node.insert(0,props)
                        normal=props.find('m:nor',NS)
                        if normal is not None:props.remove(normal)
                        child(props,'m:scr').set('{'+NS['m']+'}val',script)
                        child(props,'m:sty').set('{'+NS['m']+'}val',style)
                    output.append(node)
            return output
        n = el("m:r")
        if ast.get('normal',False):
            # Upright numerals/punctuation are mathematical runs. Normal-text
            # mode bypasses Office's mathematical script sizing and produces
            # oversized digits beside variables in e.g. w_{1,t}.
            prop='m:sty' if re.fullmatch(r'[0-9., ]+',text) else 'm:nor'
            child(child(n,'m:rPr'),prop).set('{'+NS['m']+'}val','p' if prop=='m:sty' else '1')
        if ast.get('literal') or ast['text'] in ('*','∗'):
            props=n.find('m:rPr',NS)
            if props is None:props=child(n,'m:rPr')
            child(props,'m:lit').set('{'+NS['m']+'}val','1')
        source_italic=(font_policy=='source_typeface' and not ast.get('normal',False)
                       and any(c.isalpha() and not encoded_math_letter(c) for c in text))
        if source_italic:
            # m:nor keeps the original plain codepoints on their source font.
            # Explicit DrawingML italic preserves the observed variable style;
            # the script/fraction/accent structure stays native Office Math.
            props=n.find('m:rPr',NS)
            if props is None:props=child(n,'m:rPr')
            child(props,'m:nor').set('{'+NS['m']+'}val','1')
        pr = child(n, "a:rPr", lang="en-US", sz=round(size * 100))
        if source_italic:pr.set('i','1')
        child(pr, "a:latin", typeface=font)
        if not text:raise ValueError('Empty mathematical token after whitespace normalization')
        child(n, "m:t").text = text
        return [n]
    if op == "seq":
        if not ast["items"]:
            raise ValueError("Empty math sequence")
        return [n for item in ast["items"] for n in math_node(item, font, size, font_policy)]
    specs = {"scripts": ("sSubSup", [("e", "base"), ("sub", "sub"), ("sup", "sup")]),
             "sub": ("sSub", [("e", "base"), ("sub", "sub")]),
             "sup": ("sSup", [("e", "base"), ("sup", "sup")]),
             "limit_lower": ("limLow", [("e", "base"), ("lim", "lower")]),
             "fraction": ("f", [("num", "numerator"), ("den", "denominator")]),
             "sqrt": ("rad", [("e", "body")]),
             "sum": ("nary", [("sub", "lower"), ("sup", "upper"), ("e", "body")]),
             "product": ("nary", [("sub", "lower"), ("sup", "upper"), ("e", "body")]),
             "accent": ("acc", [("e", "body")])}
    if op in specs:
        tag, args = specs[op]
        n = el("m:" + tag)
        if op == "sqrt":
            child(child(n, "m:radPr"), "m:degHide").set(f"{{{NS['m']}}}val", "1")
            child(n, "m:deg")
        if op in ("sum","product"):
            pr = child(n, "m:naryPr")
            child(pr, "m:chr").set(f"{{{NS['m']}}}val", "∑" if op=="sum" else "∏")
            child(pr, "m:limLoc").set(f"{{{NS['m']}}}val", "undOvr")
        if op == "accent":
            child(child(n, "m:accPr"), "m:chr").set(f"{{{NS['m']}}}val", ast["mark"])
        for tag, field in args:
            child(n, "m:" + tag).extend(math_node(ast[field], font, size, font_policy))
        return [n]
    if op == "matrix":
        rows = ast["rows"]
        if not rows or not rows[0] or len({len(r) for r in rows}) != 1:
            raise ValueError("Matrix rows must be nonempty and rectangular")
        n = el("m:m")
        for row in rows:
            r = child(n, "m:mr")
            for cell in row:
                child(r, "m:e").extend(math_node(cell, font, size, font_policy))
        return [n]
    if op == "cases":
        n = el("m:d")
        pr = child(n, "m:dPr")
        child(pr, "m:begChr").set(f"{{{NS['m']}}}val", "{")
        child(pr, "m:endChr").set(f"{{{NS['m']}}}val", "")
        child(n, "m:e").extend(math_node({"op": "matrix", "rows": ast["rows"]}, font, size, font_policy))
        return [n]
    if op=='delimited':
        n=el('m:d');pr=child(n,'m:dPr')
        child(pr,'m:begChr').set('{'+NS['m']+'}val',ast['left'])
        child(pr,'m:endChr').set('{'+NS['m']+'}val',ast['right'])
        child(n,'m:e').extend(math_node(ast['body'],font,size,font_policy))
        return [n]
    raise ValueError(f"Unsupported math AST operator: {op}")


def math_zone(ast, size=20, font="Cambria Math", inline=False, color=None, font_policy="native_math"):
    math=el("a14:m")
    container=math if inline else child(math,"m:oMathPara")
    child(container,"m:oMath").extend(math_node(ast,font,size,font_policy))
    if color:
        for props in math.findall('.//a:rPr',NS):
            props.insert(0,el('a:solidFill'))
            child(props[0],'a:srgbClr',val=color)
    return math


def insert_math(shape, ast, size=20, font="Cambria Math", color=None, font_policy="native_math"):
    paragraph = shape._element.find("p:txBody/a:p", NS)
    paragraph.clear()
    paragraph.append(math_zone(ast,size,font,color=color,font_policy=font_policy))
    end=child(paragraph, "a:endParaRPr", lang="en-US", sz=round(size * 100))
    if color:
        props=child(el('a:pPr'),'a:defRPr')
        child(child(props,'a:solidFill'),'a:srgbClr',val=color)
        paragraph.insert(0,props.getparent())
        child(child(end,'a:solidFill'),'a:srgbClr',val=color)
    # The math extension is valid directly in a:p. MC Choice is tested separately.
    # No visual fallback can be mistaken for the native primary branch.


def linear_math(ast):
    """UnicodeMath sent to the real Office editor, with explicit script boundaries.

    UnicodeMath uses ASCII spaces to terminate operands (Unicode Technical Note
    28, section 2). Without the terminal space, D_(theta)(y) can build both
    parenthesized groups inside the subscript. Keep the marker through sequence
    concatenation and nested serialization; it is not an AST normalization rule.
    """
    op=ast["op"]
    if op=="token":
        if ast.get('literal') or (ast.get('normal') and not all(encoded_math_letter(c) for c in ast['text'])):
            return '"'+ast['text'].replace('"','\\"')+'"'
        return ast["text"]
    if op=="seq":return "".join(linear_math(v) for v in ast["items"])
    if op in ('sub','sup','scripts'):
        base=ast['base'];encoded=linear_math(base)
        # UTN28 section 3.18: invisible grouping preserves a multi-letter base.
        # Without it, Value_k becomes Valu(e_k), which changes the saved AST.
        if base['op']=='seq' or (base['op']=='token' and len(base['text'])>1):encoded='〖'+encoded+'〗'
        sub='_('+linear_math(ast['sub'])+')' if op in ('sub','scripts') else ''
        sup='^('+linear_math(ast['sup'])+')' if op in ('sup','scripts') else ''
        return encoded+sub+sup+' '
    if op=="limit_lower":return "("+linear_math(ast["base"])+")⊥("+linear_math(ast["lower"])+") "
    if op=="accent":return linear_math(ast['body'])+ast['mark']
    if op=="fraction":return '('+linear_math(ast['numerator'])+')/('+linear_math(ast['denominator'])+')'
    if op=="sqrt":return '√('+linear_math(ast['body'])+')'
    if op=='delimited':return ast['left']+linear_math(ast['body'])+ast['right']
    if op in ('sum','product'):return ('∑' if op=='sum' else '∏')+'_('+linear_math(ast['lower'])+')^('+linear_math(ast['upper'])+') '+linear_math(ast['body'])
    if op in ("matrix","cases"):
        matrix='■('+'@'.join('&'.join(linear_math(c) for c in row) for row in ast['rows'])+')'
        return '{'+matrix+'┤' if op=='cases' else matrix
    raise ValueError("Unsupported native editor serialization: "+op)
