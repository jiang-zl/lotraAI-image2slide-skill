# Finite language collections and visual-family first decisions

New tasks bind `font-family-gate-1.37.5`. Old tasks do not inherit it merely
because the installed source changes. This supplements font-workflow-1.37.4;
physical resource identity, exact user/source authority and native/render checks
remain independent. This remains candidate code; current test/host/artwork
qualification has its own byte-bound evidence in the release validation report.

## Language and Chinese names

Use the finite current eligible resource IDs from the prepared collections.
Chinese (`ea`) requests compare only Chinese resources; English (`latin`)
requests compare only English resources. Mixed text is split by script, keeping
literal/emphasis spans. Native Math retains its own font/OMML route. ASCII glyph
coverage does not admit a Chinese font into the English collection.

For Chinese requests, `display_family` and visual-family choices use Chinese
names such as 雅黑/微软雅黑. Prefer actual localized family metadata or a finite
curated display label. Missing Chinese naming metadata needs a bounded resource
decision, never an English-language fallback or an invented native alias.
`family`, aliases, font-file hash and face index remain technical identities.
A display translation does not rename font bytes or prove a native alias valid.
No font is downloaded, installed or assumed to exist because its name occurs in
the label table. Keep eligible real weights/slants and glyph coverage checks.

## Pass the visual-family decision without a vendor contest

Within the finite current eligible catalogue, the 雅黑 group includes real
localized family names containing 雅黑, such as 微软雅黑/界面 or 华文雅黑, and
the explicitly maintained technical aliases. This is an
inference group, not a claim that those files have identical glyphs. Other
Chinese families keep their Chinese display identity unless a separate explicit
finite group is maintained. Do not merge all sans-serif fonts or infer 雅黑 from
a filename, the generic word Hei/Sans or fuzzy spelling. A shared name fragment
never changes physical bytes or establishes exact source identity.

The first family decision stores `family:雅黑`, `decision_level:visual_family`.
All feasible group members may enter this first gate. A single remaining visual
family skips an unnecessary vendor-level family-choice packet. Construction
still binds one exact existing resource, measures size with that resource and
preserves alternatives. The first binding records the family even when no extra
family-choice step was necessary. Source style groups share the inferred family;
real resources, weight/slant and each run/cell continue to be checked separately.

The one deferred comparison stays inside the adopted group. Keep the current
physical face by default; tiny numeric changes do not trigger another vendor or
variant search. Passing this inference gate permits the next preparation step;
it never supplies source-appearance, font-size or final-delivery PASS.

## Optional high-confidence fine refinement

Refinement is optional. If a photograph only supports 雅黑, retain 雅黑 and the
current eligible implementation. Never block progress merely because the vendor
cannot be distinguished. Exact frozen user requests or supplied source font
metadata keep their existing stronger authority.

For an unusually clear distinction during the deferred review, use the existing
`phase:prepare` and `font_constraints` route, retaining `family:雅黑` and adding
`fine_family` with a real ranked family alias. The hash-bound source observation
referenced by `evidence` additionally contains:

```
family_refinement: {
  confidence: high,
  family: <same real family alias as fine_family>,
  comparison_ref: <current extended ranking reference>,
  reason: <why the original distinguishes these variants>,
  features: [
    {character: <current sample>, roi: <exact current sample ROI>,
     distinction: <visible diagnostic glyph feature>,
     distinguished_from: [<actual same-group alternative family alias>]},
    <a second distinct diagnostic character>
  ]
}
```

The current model/human makes this semantic decision from the unchanged source.
The program requires a current deferred comparison, eligible group member and
two distinct located diagnostic glyphs distinguishing real alternatives. An
uncalibrated confidence number, font availability or slight ranking advantage
alone cannot refine. This is an auditable semantic evidence contract, not a
calibrated probabilistic guarantee. Permit at most one fine-family refinement
per unchanged source style group. Keep its evidence and current binding until
normal staged native adoption; exact source identity remains inferred. A new
source decision still follows normal scoped revision, prior hashes and locks.

Font size remains a separate decision on the half-point grid. Do not equate
visual-family membership with equal glyph metrics, or alter size/spacing to
hide an appearance failure. Read typography-before-render-v1375.md for units,
size screening and the independent saved/actual-render obligations.
