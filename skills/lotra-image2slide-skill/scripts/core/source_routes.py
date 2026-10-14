"""Short source-profile operator routes, separate from authorization/acceptance."""
def route(state,issue):
    unit=state.get('quality',{}).get('units',{}).get(issue.get('quality_unit'))
    if not unit:return {'reference':'references/agent-runtime.md','action':'Locate the source unit before choosing a drawing operator'}
    profile=unit['profile'];base='references/source-operators.md';out={'unit':unit['id'],'profile':profile,'original_roi':unit['roi'],'rule':'Read only this route; proposals still need the exact native grant and actual independent source/part/relationship observation.'}
    out['native_units']={'bbox/contours':'source coordinate frame','line_width/font_size/tracking':'PowerPoint points; convert measured source pixels through the saved native canvas','operator':'core.native_source_units.outline_proposal'}
    if issue.get('property','').endswith('/source_measurement_domain'):
        out.update(reference=base+'#source-measurement-frame',operators=[{'command':'source_correction',
            'when':'Actually view the enlarged original sampling window. Use source_pixel_box for masks, source-owned context for thin strokes, and a finite original background. Preserve old definitions, targets and the saved drawing; never resize a mask or repaint against invalid input.'}])
        return out
    if profile=='text':
        out['mixed_content_rule']='Read math embedded in definitions, legends and cells; Unicode script/accent shortcuts require an independently source-confirmed structured repair. Native table cell_styles preserve per-cell horizontal/vertical alignment, weight and spacing; do not apply a blanket style.'
        out.update(reference=base+'#original-words-and-native-glyphs',operators=[{'command':'source-word-anchors','when':'Literal/locator is unconfirmed; use cached original OCR or enlarged original evidence; record explicit content.literal, never a generic type'},{'command':'native-text-content','when':'Confirmed source literal differs from actual saved native text; correct only the existing plain-text content'},{'command':'native-text-fit','when':'Confirmed native literal has a located pose mismatch; source_style needs original typography evidence'},
            {'command':'font-gallery / rank-fonts','when':'Complete word pose is known but its own ink weight/family fails: pass the saved quality_unit and keep fixed original masks/targets; a pose-only shrink cannot compensate lighter strokes'},
            {'command':'native-text-weight','when':'Two saved full-context native word responses bracket its source weight, with unchanged target/context/family: reuse them to estimate a bounded outline opacity, preserving all satisfactory peers'}])
        if unit.get('protocol',{}).get('table_cell') is not None:
            out['operators'].insert(0,{'command':'native-table-cells','when':'An independently read source cell differs in native alignment/weight. Compile observed per-cell formats from source units; preserve exact literal, grid, merges and every ungranted cell.'})
        out['operators'].append({'command':'native-definitions' ,'when':'A source-confirmed variable definition box mixes indexed/accented symbols with prose. Compile ordinary native prose and separate inline Office Math spans; every span needs its original AST and actual renderer observation. If inline display fails, use independently bound native equations, preserving the exact row frame.'})
        out['operators'].append({'command':'native-text-lines',
            'when':'An independently confirmed two-to-six-line native caption has a located row/advance/pitch mismatch. Keep exact original literal/family/paragraph count, original glyph mask and native owner; reuse saved actual row ink for one bounded pose/size/pitch proposal, then assess each actual caption and affected neighbor.',
            'reference':'references/native-caption-rows.md'})
        out['operators'].append({'command':'native-word-paper',
            'when':'Saved native text is satisfactory but actual paper font/pose/weight is not. Use original source units and cached actual Office glyph/advance receipts with unchanged word/parent frames. The program fits bounded output-only weight, removes only located old PDF text, preserves native icon graphics, and returns independent word/gap outcomes; native PPT stays frozen.',
            'reference':'references/native-word-paper.md'})
    elif profile=='formula':
        out.update(reference=base+'#original-words-and-native-glyphs',operators=[{'command':'source-formulas','when':'Confirm exact original AST, independently owned glyphs and typography; generic equation labels cannot satisfy content'},{'command':'native-math-fit','when':'Source-confirmed Office Math has a located structure/font/size/pose discrepancy; retain exact AST and independently measure each changed formula and affected gap'}])
    elif profile=='three_dimensional':
        out.update(reference=base+'#projected-native-surfaces-and-3d-components',operators=[{'command':'source-material with surfaces','when':'Original projected planes/visibility and independent face units are already identified'},{'command':'native preset/cubic/gradient or matched pure SVG','when':'Source curved lens/body/support requires natural shape/shading; observe all important leaves'}])
    elif profile in ('flat','structured','curve','detail'):
        out.update(reference=base+'#flat-source-materials',operators=[{'command':'native preset/continuous path','when':'One native contour expresses the source part'},{'command':'source-material','when':'Small identified material family has explicit original ownership; projected faces use the surfaces program'}])
    elif profile=='relation':
        out.update(reference='references/source-part-loop.md#fixed-independent-targets',operators=[{'command':'native relation/placement repair','when':'Use the declared original gap, containment, topology or paint order; an icon appearance score cannot compensate it'}])
    else:
        out.update(reference=base+'#rich-artwork-hd-and-export',operators=[{'command':'source-owned native/SVG/artwork method','when':'Observed rich surfaces retain original semantic ownership and independent text/math/relations; HD choices require actual important-quality gain'}])
    if profile in ('flat','structured','curve'):
        out['operators'].append({'command':'source_fit conditional analytic primitives',
            'when':'Original simple regular arcs are observed, but level-set curves follow blurred pixel-grid undulations. Read #regular-source-primitives; an independently confirmed complete two-wave antenna can use open_radial_mast. A separately owned parallel colored curved pair without a mast can use parallel_curved_bands with original rim/inner/outer paints, two independent material masks and an original-only domain. An independently observed hollow right-arrow on a uniform ground uses native_hollow_right_arrow to fit one native preset, with automatic saved/planned source-pixel-to-native-point calibration. Never substitute a family from the icon name.'})
    if profile in ('flat','structured','curve','detail','three_dimensional'):
        out['operators'].append({'command':'source-material-response',
            'when':'A uniform native material alone differs after actual rendering while contour/pose are satisfactory. Use observed source paint/backgrounds and fixed foreground masks; one bounded predicted proposal still needs an actual protected draw.'})
    if profile in ('flat','structured','curve','detail','three_dimensional'):
        out['operators'].append({'command':'source-material-grid','when':'Actual owned lens/support/surface has source-absent horizontal row bands. Reuse exact original RGB/masks, preserve native frames and approved adjacent parts; only independently revisited SVG material owners may change. Actual host/PDF outcomes remain separate.','reference':'references/source-colour-grid.md'})
    if profile in ('flat','structured','curve','detail','three_dimensional') and unit.get('reference_mask'):
        out['operators'].insert(0,{'command':'source-fragments / source-fragment-plan',
            'when':'Mask-based missing/fragmented natural material, false ground holes or a foreground/background alias is observed. Before another mask trace, inspect cached original-vs-owned fragment board; explicitly own/exclude/leave uncertain every named fragment, preserving foreign boundaries and real gaps. Submit source mask amendments through ordinary correction; no automatic colour-based semantic decisions.',
            'reference':'references/source-fragments.md'})
    if unit.get('layering'):
        out['operators'].insert(0,{'command':'source-layer-domain','when':'The source part is an underlay with upper occlusions or outside context; retain fixed original masks and source-frame ownership before geometry/material fitting'})
        out['ownership_rule']='A declared layer lacking bound visible masks is unmeasured, never a successful whole-ROI score. Source correction and drawing gain are separate.'
        if profile in ('flat','structured','curve'):
            out['operators'].append({'command':'source-occluded-band','when':'A source-observed natural road/material band has three ordered anchors, measured narrow width, an original ellipse clip and bounded hidden continuity; other curve families require a different source plan'})
    if profile not in ('text','formula','relation') and unit.get('reference_mask'):
        out['operators'].insert(0,{'command':'source-residuals',
            'when':'A saved visual part has an unmet edge/presence/material score but the source cause is unlocated. Read the bounded fixed-coordinate source/actual/mask/residual board before another drawing; foreign original layers and source ownership asymmetry can create an apparent icon defect. Numeric positions do not prove semantics or authorize a mask/target change.',
            'reference':'references/source-residuals.md'})
    return out
