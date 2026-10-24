"""Finite visual-family gates; physical font identities remain exact resources."""
from .common import digest
from .font_resources import name_key, matches

POLICY = 'font-family-gate-1.37.5'

# Display labels do not create native aliases, install fonts or merge font bytes.
# Only resources already eligible for the language/style/glyph request can enter.
CHINESE_NAMES = {
    '宋体': ('SimSun',), '新宋体': ('NSimSun',), '黑体': ('SimHei',),
    '楷体': ('KaiTi',), '仿宋': ('FangSong',),
    '微软雅黑': ('Microsoft YaHei',), '微软雅黑界面': ('Microsoft YaHei UI',),
    '微軟正黑體': ('Microsoft JhengHei',),
    '微軟正黑體界面': ('Microsoft JhengHei UI',),
    '新細明體': ('PMingLiU',), '細明體': ('MingLiU',), '等线': ('DengXian',),
    '华文宋体': ('STSong',), '华文黑体': ('STHeiti',),
    '华文楷体': ('STKaiti',), '华文仿宋': ('STFangsong',),
    '诺托宋体（简体中文）': ('Noto Serif CJK SC',),
    '诺托黑体（简体中文）': ('Noto Sans CJK SC',),
    '诺托宋体（繁体中文）': ('Noto Serif CJK TC',),
    '诺托黑体（繁体中文）': ('Noto Sans CJK TC',),
    '思源宋体（简体中文）': ('Source Han Serif SC', 'Source Han Serif CN'),
    '思源黑体（简体中文）': ('Source Han Sans SC', 'Source Han Sans CN'),
    '思源宋体（繁体中文）': ('Source Han Serif TC',),
    '思源黑体（繁体中文）': ('Source Han Sans TC',),
    '苹方（简体）': ('PingFang SC',), '苹方（繁体）': ('PingFang TC',),
    '宋体（简体）': ('Songti SC',), '宋体（繁体）': ('Songti TC',),
    '黑体（简体）': ('Heiti SC',), '黑体（繁体）': ('Heiti TC',),
    '文泉驿正黑': ('WenQuanYi Zen Hei',), '文泉驿微米黑': ('WenQuanYi Micro Hei',),
}
VISUAL_FAMILIES = {
    '雅黑': ('雅黑', '微软雅黑', '微软雅黑 UI', '微软雅黑界面',
           'Microsoft YaHei', 'Microsoft YaHei UI', '华文雅黑'),
}


def enabled(state):
    return state.get('font_family_policy') == POLICY


def has_chinese(value):
    return any('\u3400' <= char <= '\u9fff' for char in value)


def display_name(face, language):
    if language != 'zh':
        return face['family']
    names = [face['family'], *face.get('aliases', [])]
    localized = next((name for name in names if has_chinese(name)), None)
    if localized:
        return localized
    aliases = {name_key(name) for name in names}
    return next((label for label, values in CHINESE_NAMES.items()
                 if aliases & {name_key(name) for name in (label, *values)}), None)


def family_key(state, request, face):
    if not enabled(state):
        return face['family']
    language = 'zh' if request['role'] == 'ea' else 'en'
    label = display_name(face, language)
    if not label:
        raise ValueError('FONT_CHINESE_NAME_REQUIRED: provide a finite curated Chinese display name for this real resource')
    if language == 'zh':
        names = (face['family'], label, *face.get('aliases', []))
        # Inspect actual names only inside the finite already eligible catalogue.
        # This is a user-approved visual grouping, not a native-name alias.
        if any('雅黑' in name for name in names if has_chinese(name)):
            return '雅黑'
        aliases = {name_key(name) for name in names}
        for family, values in VISUAL_FAMILIES.items():
            if aliases & {name_key(name) for name in values}:
                return family
    return label


def selected_key(state, request, faces, selected):
    """Accept a displayed group or a real family alias, then store the coarse key."""
    keys = {family_key(state, request, face) for face in faces
            if family_key(state, request, face) == selected or matches(face, selected)
            or display_name(face, 'zh' if request['role'] == 'ea' else 'en') == selected}
    if len(keys) != 1:
        raise ValueError('Choose one current finite language-specific visual family')
    return next(iter(keys))


def labels(state, request, face):
    if not enabled(state):
        return {}
    return {'display_family': display_name(face, 'zh' if request['role'] == 'ea' else 'en'),
            'visual_family': family_key(state, request, face)}


def context(state):
    return {'policy': POLICY, 'implementation': digest(__file__)} if enabled(state) else None


def refinement(state, request, value, current, ranking, faces, observed):
    """Require located semantic evidence, never an uncalibrated probability alone."""
    fine = value.get('fine_family')
    if not fine:
        return {}
    if not enabled(state) or not ranking.get('extended'):
        raise ValueError('FONT_FINE_REVIEW_REQUIRED: refine only in the one deferred comparison')
    from .font_resources import name_key
    candidates = [face for face in faces if family_key(state, request, face) == current['family']]
    winners = {face['family'] for face in candidates if matches(face, fine)}
    if len(winners) != 1:
        raise ValueError('Fine family must be a currently eligible member of the adopted visual family')
    fine = next(iter(winners))
    if current.get('fine_family'):
        if current['fine_family'] != fine:
            raise ValueError('FONT_FINE_BUDGET_EXHAUSTED: retain the evidenced fine-family decision')
        return {}
    proof = observed.get('family_refinement', {})
    if (proof.get('confidence') != 'high' or not proof.get('reason') or
            proof.get('comparison_ref') != value.get('comparison_ref') or
            name_key(proof.get('family', '')) != name_key(value['fine_family'])):
        raise ValueError('High-confidence refinement needs the current comparison and a located explanation')
    features = proof.get('features', [])
    samples = ranking.get('samples', {}).get('samples', [])
    alternatives = {alias for face in candidates if face['family'] != fine
                    for alias in (face['family'], *face.get('aliases', []))}
    if len(features) < 2 or len({feature.get('character') for feature in features}) < 2:
        raise ValueError('Fine refinement requires at least two distinct observed diagnostic glyphs')
    for feature in features:
        if (not feature.get('distinction') or
                not any(feature.get('character') == sample.get('character') and
                        feature.get('roi') == sample.get('roi') for sample in samples) or
                not any(name_key(peer) in {name_key(alias) for alias in alternatives}
                        for peer in feature.get('distinguished_from', []))):
            raise ValueError('Fine-family evidence must locate current samples and distinguish actual same-family alternatives')
    return {'fine_family': fine, 'fine_family_evidence': value['evidence'],
            'fine_family_comparison': value['comparison_ref'], 'fine_refinements': 1,
            'certainty': 'high_confidence_raster_inference'}
