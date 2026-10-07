#!/usr/bin/env python3
"""Build a monochrome TTF font from the 256 Semantic Alphabet SVG pictograms.

Each pictogram is mapped to a Private Use Area codepoint so that byte value N
is rendered as chr(0xE000 + N). The PUA is used (rather than U+0000..U+00FF)
because standard text stacks choke on control-character codepoints (NUL, TAB,
LF, etc.) even when a font defines glyphs for them. Translate bytes -> PUA
codepoints at render time.

Usage:
    # From this directory, with the .venv already set up:
    .venv/bin/python build_font.py

    # Or install deps yourself:
    pip install fonttools picosvg
    python3 build_font.py

Produces: SemanticAlphabet.ttf next to this script.
"""

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.misc.transform import Transform
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib.tables.O_S_2f_2 import Panose
from picosvg.svg import SVG


HERE = Path(__file__).parent
SVG_DIR = HERE / "svg"
OUTPUT = HERE / "SemanticAlphabet.ttf"

# TrueType conventions: 1000 units per em, ascent + |descent| == UPM.
UPM = 1000
ASCENT = 800
DESCENT = -200
GLYPH_BOX_HEIGHT = ASCENT - DESCENT  # 1000

# Scale is shared across all glyphs and is derived at build time from the
# reference SVG's viewBox height, so heights are assumed to be consistent.
# Advance width is computed per glyph from each SVG's own viewBox width.
REFERENCE_INDEX = 0

# Warn if another glyph's viewBox height differs from the reference by more
# than this (in SVG user units). Shared scale means mismatches render at
# the wrong visual size.
HEIGHT_TOLERANCE = 0.01

# Max error (in font units) when approximating cubic Beziers with quadratics.
# The `glyf` table only stores quadratics; 1.0 on a 1000 UPM font is visually
# indistinguishable from the source.
CU2QU_MAX_ERR = 1.0

# Byte value N -> U+E100 + N. Private Use Area avoids collisions with
# control chars, ASCII, and Latin-1 in any text rendering stack. The
# E100 block (rather than E000) also avoids the Powerline Symbols range
# used by JetBrains Mono and other programming fonts at U+E0A0-E0B3,
# so the same base works whether this font is used standalone or merged
# into a font that already uses the E0 block.
PUA_BASE = 0xE100
NUM_GLYPHS = 256

FAMILY = "Semantic Alphabet"
STYLE = "Regular"
PSNAME = "SemanticAlphabet-Regular"
VERSION = "1.000"


def svg_path_for_index(i: int) -> Path:
    # Irrational set only. The rational (DecaCode) set is wired into
    # build_merged_font.py as a second PUA block; this standalone font
    # stays single-set for now.
    return SVG_DIR / f"the standard semantic alphabet_irrational - {i}.svg"


def glyph_name_for_index(i: int) -> str:
    # Adobe Glyph List convention for PUA codepoints: "uniXXXX".
    return f"uni{PUA_BASE + i:04X}"


def build_glyph(svg_file: Path, scale: float):
    """Parse one SVG file and return (glyph, advance_width, viewbox_height).

    `scale` is the shared SVG-user-unit -> font-unit factor; advance width
    is the glyph's own viewBox width times that scale.
    """
    # picosvg normalizes rect/polygon/path/etc. into a single flat list of
    # <path> elements, so downstream code only has to handle path `d` strings.
    svg = SVG.parse(str(svg_file))
    view_box = svg.view_box()
    normalized = svg.topicosvg()

    # Pen chain (outer layers wrap inner ones; SVG commands flow through
    # them in order):
    #   parse_path
    #     -> TransformPen     scale + Y-flip (SVG is y-down, font y-up),
    #                         with a Y-offset chosen to center each glyph
    #                         vertically in the em box regardless of its
    #                         viewBox height (so variable-height glyphs
    #                         get balanced whitespace above/below)
    #     -> ReverseContourPen  undo the winding reversal Y-flip introduces
    #     -> Cu2QuPen         convert cubic Beziers -> quadratics for `glyf`
    #     -> TTGlyphPen       record the final quad-only glyph
    target = TTGlyphPen(None)
    quad_pen = Cu2QuPen(target, CU2QU_MAX_ERR)
    reversing_pen = ReverseContourPen(quad_pen)

    # Center the glyph vertically: translate so the viewBox's vertical
    # midpoint lands on the em box's midpoint (ASCENT + DESCENT) / 2.
    em_center = (ASCENT + DESCENT) / 2
    y_translation = em_center + (view_box.h / 2) * scale
    transform = Transform().translate(0, y_translation).scale(scale, -scale)
    transformed_pen = TransformPen(reversing_pen, transform)

    for shape in normalized.shapes():
        parse_path(shape.d, transformed_pen)

    advance = round(view_box.w * scale)
    return target.glyph(), advance, view_box.h


def empty_glyph():
    """.notdef glyph — required at index 0 of every font."""
    return TTGlyphPen(None).glyph()


def main() -> None:
    missing = [i for i in range(NUM_GLYPHS) if not svg_path_for_index(i).exists()]
    if missing:
        raise SystemExit(
            f"Missing {len(missing)} source SVG(s). First few indices: {missing[:10]}"
        )

    # Derive the shared scale from the reference glyph's viewBox height;
    # all other glyphs are assumed (and checked below) to share that height.
    reference_vb = SVG.parse(str(svg_path_for_index(REFERENCE_INDEX))).view_box()
    scale = GLYPH_BOX_HEIGHT / reference_vb.h

    glyph_order = [".notdef"] + [glyph_name_for_index(i) for i in range(NUM_GLYPHS)]

    glyphs = {".notdef": empty_glyph()}
    # .notdef uses the reference width so its advance is consistent with a
    # typical glyph.
    metrics = {".notdef": (round(reference_vb.w * scale), 0)}
    cmap = {}

    # Shorter-than-reference glyphs are fine — the centering transform
    # pads them with whitespace top/bottom. Only taller-than-reference
    # glyphs are a problem: they scale past the em box and bleed into
    # the ascender/descender regions of adjacent lines.
    overflows = []
    for i in range(NUM_GLYPHS):
        name = glyph_name_for_index(i)
        glyph, advance, source_height = build_glyph(svg_path_for_index(i), scale)
        if source_height > reference_vb.h + HEIGHT_TOLERANCE:
            overflows.append((i, source_height))
        glyphs[name] = glyph
        metrics[name] = (advance, 0)  # (advance width, left side bearing)
        cmap[PUA_BASE + i] = name

    if overflows:
        print(
            f"warning: {len(overflows)} glyph(s) have viewBox height > "
            f"reference ({reference_vb.h}); they'll overflow the em box "
            f"symmetrically above/below. Either make SVG 0 the tallest "
            f"glyph (so it anchors the scale), or reduce these heights:"
        )
        for i, h in overflows[:5]:
            print(f"  index {i}: height={h}")
        if len(overflows) > 5:
            print(f"  ...and {len(overflows) - 5} more")

    # Monospace invariant: every advance must match the reference, or the
    # `isFixedPitch` / PANOSE flags we set below would be lying to the OS.
    # Terminals (macOS Terminal in particular) only offer fonts marked
    # monospace in their font picker, so an honest flag matters.
    reference_advance = metrics[glyph_order[1]][0]
    width_mismatches = [
        (name, adv) for name, (adv, _lsb) in metrics.items() if adv != reference_advance
    ]
    if width_mismatches:
        raise SystemExit(
            f"Monospace invariant violated: {len(width_mismatches)} glyph(s) have "
            f"an advance != reference ({reference_advance}). First few: "
            f"{width_mismatches[:3]}. Make SVG viewBox widths uniform, or drop "
            f"the monospace declaration below."
        )

    # PANOSE: describes classification for font pickers. bFamilyType=2
    # (Latin Text) is the family under which bProportion=9 means
    # "Monospaced" — other family types don't define a monospace value.
    panose = Panose()
    panose.bFamilyType = 2   # Latin Text
    panose.bProportion = 9   # Monospaced

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    fb.setupOS2(
        sTypoAscender=ASCENT,
        sTypoDescender=DESCENT,
        usWinAscent=ASCENT,
        usWinDescent=-DESCENT,
        panose=panose,
    )
    fb.setupNameTable({
        "familyName": FAMILY,
        "styleName": STYLE,
        "psName": PSNAME,
        "version": VERSION,
    })
    # isFixedPitch=1 is the flag OSes and terminals actually key off for
    # monospace detection. The enforcement check above keeps this honest.
    fb.setupPost(isFixedPitch=1)

    fb.save(str(OUTPUT))
    first = f"U+{PUA_BASE:04X}"
    last = f"U+{PUA_BASE + NUM_GLYPHS - 1:04X}"
    print(f"Wrote {OUTPUT.name}: {NUM_GLYPHS} glyphs, {first}..{last}")


if __name__ == "__main__":
    main()
