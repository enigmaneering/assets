#!/usr/bin/env python3
"""Merge both Semantic Alphabet glyph sets into JetBrains Mono Regular.

Produces SemanticMono-Regular.ttf: a monospace TTF with JetBrains Mono's
full glyph set plus two 256-glyph alphabet tables:

    Byte N -> U+E100 + N  -> irrational pictogram (free-form symbols)
    Byte N -> U+E200 + N  -> rational pictogram  (DecaCode, pixel-perfect)

Consumers switch between sets by choosing the PUA base when rendering
(`rune(0xE100) + rune(b)` vs `rune(0xE200) + rune(b)`). No font swap.

Both sets are scaled so their SVG width matches JetBrains' 600-unit
monospace advance, preserving aspect ratio by uniform X/Y scaling and
filling any leftover vertical space with whitespace centered at the
cap-height midpoint. Concrete result in a 1000-UPM font:

    irrational (44x37 source) -> 600 wide x ~505 tall
    rational   (16x16 source) -> 600 wide x 600 tall

Rendering note for DecaCode (rational set): its 16x16 design renders at
its native pixel density when font-units map 1:1 to screen pixels, i.e.
when em = 16px. At 600 advance in a 1000-UPM font, that happens at
~20pt (12pt x 1000/600) rather than 12pt. At 12pt in this font, DecaCode
is ~9.6x9.6 px and loses information. Bump to 20pt+ for full fidelity,
or use a dedicated DecaCode font with 1000-unit (square) advance.

We use PUA blocks E100+ and E200+ specifically because JetBrains Mono
already maps U+E0A0..E0A2 and U+E0B0..E0B3 to Powerline glyphs; staying
above U+E100 avoids that collision entirely and Powerline keeps working.

JetBrains Mono is OFL-licensed. "JetBrains Mono" is a Reserved Font Name
under the OFL, so the output is renamed to "Semantic Mono" — reserved
names may not appear in derivative works. The OFL also requires
redistributing the original license text alongside derivatives; if you
plan to share this font, include the OFL.txt from the upstream
JetBrains Mono release.

Usage:
    ./build_merged_font.sh
    # or: .venv/bin/python build_merged_font.py
"""

from pathlib import Path
from typing import NamedTuple

from fontTools.misc.transform import Transform
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from picosvg.svg import SVG


HERE = Path(__file__).parent
BASE_FONT = HERE / "jetbrains mono" / "ttf" / "JetBrainsMono-Regular.ttf"
SVG_DIR = HERE / "svg"
OUTPUT = HERE / "SemanticMono-Regular.ttf"

NUM_GLYPHS = 256
REFERENCE_INDEX = 0

# Max error (font units) when converting SVG cubic Beziers to the
# quadratics required by the `glyf` table. 1.0 on a 1000-UPM font is
# visually indistinguishable from the source.
CU2QU_MAX_ERR = 1.0

# OFL Reserved Font Name: can't reuse "JetBrains Mono" in derivatives.
FAMILY_NAME = "Semantic Mono"
STYLE_NAME = "Regular"
PS_NAME = "SemanticMono-Regular"
VERSION = "1.000"


class GlyphSet(NamedTuple):
    """One of the 256-glyph alphabet tables we stitch into the font."""
    name: str            # human-readable label for logs
    pua_base: int        # codepoint for byte 0 in this set
    glyph_prefix: str    # prefix for internal glyph names (kept distinct
                         # per set so they never collide)
    svg_pattern: str     # filename template; must contain "{i}"


# Order matters only for logging; PUA base is authoritative for mapping.
GLYPH_SETS = [
    GlyphSet(
        name="irrational",
        pua_base=0xE100,
        glyph_prefix="irrational.",
        svg_pattern="the standard semantic alphabet_irrational - {i}.svg",
    ),
    GlyphSet(
        name="rational (DecaCode)",
        pua_base=0xE200,
        glyph_prefix="rational.",
        svg_pattern="the standard semantic alphabet_rational - {i}.svg",
    ),
]


def svg_path(glyph_set: GlyphSet, i: int) -> Path:
    return SVG_DIR / glyph_set.svg_pattern.format(i=i)


def glyph_name(glyph_set: GlyphSet, i: int) -> str:
    return f"{glyph_set.glyph_prefix}{i:02X}"


def build_glyph(svg_file: Path, scale: float, y_center: float):
    """Return (glyph, viewbox_height) for one SVG.

    Pictogram is scaled uniformly by `scale`, Y-flipped, and placed so
    its viewBox's vertical midpoint lands on `y_center` in the
    destination font's coordinate space.
    """
    svg = SVG.parse(str(svg_file))
    view_box = svg.view_box()
    normalized = svg.topicosvg()

    # Pen chain (outer wraps inner):
    #   parse_path
    #     -> TransformPen     scale + Y-flip + vertical centering
    #     -> ReverseContourPen  undo the winding reversal Y-flip introduces
    #     -> Cu2QuPen         cubic Beziers -> quadratics for `glyf`
    #     -> TTGlyphPen       record the final glyph
    target = TTGlyphPen(None)
    quad_pen = Cu2QuPen(target, CU2QU_MAX_ERR)
    reversing_pen = ReverseContourPen(quad_pen)

    y_translation = y_center + (view_box.h / 2) * scale
    transform = Transform().translate(0, y_translation).scale(scale, -scale)
    transformed_pen = TransformPen(reversing_pen, transform)

    for shape in normalized.shapes():
        parse_path(shape.d, transformed_pen)

    return target.glyph(), view_box.h


def set_name(name_table, string: str, name_id: int) -> None:
    """Write a name table entry on both Windows and Macintosh platforms."""
    name_table.setName(string, name_id, 3, 1, 0x409)  # Windows, Unicode BMP, en-US
    name_table.setName(string, name_id, 1, 0, 0)       # Macintosh, Roman, English


def process_set(
    glyph_set: GlyphSet,
    font: TTFont,
    jb_advance: int,
    y_center: float,
    glyph_order: list,
) -> None:
    """Add one GlyphSet's 256 glyphs to the font in-place."""
    missing = [i for i in range(NUM_GLYPHS) if not svg_path(glyph_set, i).exists()]
    if missing:
        raise SystemExit(
            f"{glyph_set.name}: missing {len(missing)} SVG(s); "
            f"first few indices: {missing[:10]}"
        )

    ref_vb = SVG.parse(str(svg_path(glyph_set, REFERENCE_INDEX))).view_box()
    scale = jb_advance / ref_vb.w
    scaled_h = ref_vb.h * scale
    print(
        f"  {glyph_set.name}: viewBox {ref_vb.w:g}x{ref_vb.h:g}, "
        f"scale={scale:.3f} -> {jb_advance}x{scaled_h:.0f} font units "
        f"(U+{glyph_set.pua_base:04X}..U+{glyph_set.pua_base + NUM_GLYPHS - 1:04X})"
    )

    glyf = font["glyf"]
    hmtx = font["hmtx"]

    for i in range(NUM_GLYPHS):
        name = glyph_name(glyph_set, i)
        glyph, _source_h = build_glyph(svg_path(glyph_set, i), scale, y_center)
        glyf[name] = glyph
        hmtx[name] = (jb_advance, 0)  # monospace — every advance identical
        glyph_order.append(name)

    # Rewrite every Unicode cmap subtable for this set's codepoints.
    for subtable in font["cmap"].tables:
        if not subtable.isUnicode():
            continue
        for i in range(NUM_GLYPHS):
            subtable.cmap[glyph_set.pua_base + i] = glyph_name(glyph_set, i)


def main() -> None:
    if not BASE_FONT.exists():
        raise SystemExit(f"Base font not found at {BASE_FONT}")

    font = TTFont(str(BASE_FONT))

    # Inherit all metrics from the base font — no invention, no risk of
    # breaking line spacing or vertical rhythm.
    upm = font["head"].unitsPerEm
    cap_height = font["OS/2"].sCapHeight
    jb_advance, _lsb = font["hmtx"].metrics[".notdef"]
    y_center = cap_height / 2

    print(
        f"Base: UPM={upm}, advance={jb_advance}, cap_height={cap_height} "
        f"(y_center={y_center:g})"
    )

    glyph_order = list(font.getGlyphOrder())
    for glyph_set in GLYPH_SETS:
        process_set(glyph_set, font, jb_advance, y_center, glyph_order)

    # setGlyphOrder also updates maxp.numGlyphs for us.
    font.setGlyphOrder(glyph_order)

    # Rename the font so it doesn't impersonate JetBrains Mono (OFL RFN).
    name_table = font["name"]
    set_name(name_table, FAMILY_NAME, 1)                           # family
    set_name(name_table, STYLE_NAME, 2)                            # subfamily
    set_name(name_table, f"{FAMILY_NAME} {STYLE_NAME}", 4)         # full name
    set_name(name_table, PS_NAME, 6)                               # PostScript
    set_name(name_table, FAMILY_NAME, 16)                          # typographic family
    set_name(name_table, STYLE_NAME, 17)                           # typographic subfamily
    set_name(name_table, f"{PS_NAME} {VERSION}", 3)                # unique ID
    set_name(name_table, f"Version {VERSION}", 5)                  # version string

    font.save(str(OUTPUT))
    total_added = len(GLYPH_SETS) * NUM_GLYPHS
    base_glyph_count = font["maxp"].numGlyphs - total_added
    print(
        f"Wrote {OUTPUT.name}: {base_glyph_count} base glyphs + "
        f"{total_added} pictograms ({len(GLYPH_SETS)} sets x {NUM_GLYPHS})"
    )


if __name__ == "__main__":
    main()
