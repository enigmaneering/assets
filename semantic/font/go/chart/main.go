// Render the 256-byte Semantic Alphabet chart to a PNG.
//
// Unlike ../main.go (which emits PUA codepoints and lets the terminal
// pick a font), this program loads a TTF directly with
// golang.org/x/image/font/opentype and rasterizes glyphs itself. No
// system font install, no terminal config — the TTF is referenced
// explicitly via the -font flag.
//
// The merged Semantic Mono font ships two alphabet sets at separate PUA
// blocks (E100 = irrational, E200 = rational/DecaCode). Pick which one
// the chart renders with -set.
//
// Run:
//   go run ./chart
//   go run ./chart -set rational -out chart-rational.png
//   go run ./chart -font ../SemanticAlphabet.ttf -size 36
package main

import (
	"flag"
	"fmt"
	"image"
	"image/color"
	"image/draw"
	"image/png"
	"log"
	"os"

	"golang.org/x/image/font"
	"golang.org/x/image/font/basicfont"
	"golang.org/x/image/font/opentype"
	"golang.org/x/image/math/fixed"
)

// PUA base for each alphabet set; keep in sync with GLYPH_SETS in
// build_merged_font.py. (E100/E200 rather than E000/E100 avoids the
// Powerline range at U+E0A0-E0B3.)
const (
	puaBaseIrrational = 0xE100
	puaBaseRational   = 0xE200
)

func main() {
	fontPath := flag.String("font", "../SemanticMono-Regular.ttf", "path to the TTF (must cover the chosen set's PUA block)")
	setName := flag.String("set", "irrational", "which alphabet: irrational | rational")
	outPath := flag.String("out", "", "output PNG path (default: chart-<set>.png)")
	glyphSize := flag.Float64("size", 36, "glyph point size")
	flag.Parse()

	var puaBase rune
	switch *setName {
	case "irrational":
		puaBase = puaBaseIrrational
	case "rational":
		puaBase = puaBaseRational
	default:
		log.Fatalf("unknown -set %q; expected 'irrational' or 'rational'", *setName)
	}
	if *outPath == "" {
		*outPath = fmt.Sprintf("chart-%s.png", *setName)
	}

	// Load and parse the TTF. This is the bit the terminal demo can't do —
	// we read the actual font bytes instead of delegating to the OS.
	fontBytes, err := os.ReadFile(*fontPath)
	if err != nil {
		log.Fatalf("read font %q: %v", *fontPath, err)
	}
	sfntFont, err := opentype.Parse(fontBytes)
	if err != nil {
		log.Fatalf("parse font: %v", err)
	}

	glyphFace, err := opentype.NewFace(sfntFont, &opentype.FaceOptions{
		Size:    *glyphSize,
		DPI:     72,
		Hinting: font.HintingNone,
	})
	if err != nil {
		log.Fatalf("new glyph face: %v", err)
	}
	defer glyphFace.Close()

	// Built-in bitmap font for the hex labels, so we don't need a second TTF.
	labelFace := basicfont.Face7x13

	// Cell dimensions driven by the font's actual metrics. The source
	// pictograms are roughly 1.5x wider than tall, so we size cells
	// accordingly and let glyphs keep their real proportions.
	metrics := glyphFace.Metrics()
	glyphH := (metrics.Ascent + metrics.Descent).Ceil()
	const cellPad = 10
	cellH := glyphH + cellPad
	cellW := int(float64(glyphH)*1.6) + cellPad

	const (
		rows, cols                             = 16, 16
		marginL, marginT, marginR, marginB     = 48, 36, 24, 24
	)
	imgW := marginL + cols*cellW + marginR
	imgH := marginT + rows*cellH + marginB

	img := image.NewRGBA(image.Rect(0, 0, imgW, imgH))
	draw.Draw(img, img.Bounds(), &image.Uniform{C: color.White}, image.Point{}, draw.Src)

	// Grid lines so cells are distinguishable even when a glyph is sparse.
	gridColor := color.RGBA{R: 220, G: 220, B: 220, A: 255}
	for c := 0; c <= cols; c++ {
		x := marginL + c*cellW
		drawVLine(img, x, marginT, marginT+rows*cellH, gridColor)
	}
	for r := 0; r <= rows; r++ {
		y := marginT + r*cellH
		drawHLine(img, marginL, marginL+cols*cellW, y, gridColor)
	}

	// Column headers (low nibble).
	for col := 0; col < cols; col++ {
		drawLabel(img, labelFace, fmt.Sprintf("_%X", col),
			marginL+col*cellW+cellW/2-7, marginT-8)
	}
	// Row headers (high nibble) + glyphs.
	for row := 0; row < rows; row++ {
		drawLabel(img, labelFace, fmt.Sprintf("%X_", row),
			marginL-28, marginT+row*cellH+cellH/2+4)
		for col := 0; col < cols; col++ {
			b := byte(row*cols + col)
			r := puaBase + rune(b)
			drawGlyph(img, glyphFace, string(r),
				marginL+col*cellW+cellPad/2,
				marginT+row*cellH+cellH-cellPad/2-metrics.Descent.Ceil())
		}
	}

	// Write PNG.
	out, err := os.Create(*outPath)
	if err != nil {
		log.Fatalf("create %q: %v", *outPath, err)
	}
	defer out.Close()
	if err := png.Encode(out, img); err != nil {
		log.Fatalf("encode png: %v", err)
	}
	log.Printf("wrote %s (%dx%d, %s set U+%04X..U+%04X from %s)",
		*outPath, imgW, imgH, *setName, puaBase, puaBase+rune(rows*cols-1), *fontPath)
}

func drawLabel(img *image.RGBA, face font.Face, s string, x, y int) {
	d := &font.Drawer{
		Dst:  img,
		Src:  image.NewUniform(color.Black),
		Face: face,
		Dot:  fixed.P(x, y),
	}
	d.DrawString(s)
}

func drawGlyph(img *image.RGBA, face font.Face, s string, x, baseline int) {
	d := &font.Drawer{
		Dst:  img,
		Src:  image.NewUniform(color.Black),
		Face: face,
		Dot:  fixed.P(x, baseline),
	}
	d.DrawString(s)
}

func drawHLine(img *image.RGBA, x0, x1, y int, c color.Color) {
	for x := x0; x <= x1; x++ {
		img.Set(x, y, c)
	}
}

func drawVLine(img *image.RGBA, x, y0, y1 int, c color.Color) {
	for y := y0; y <= y1; y++ {
		img.Set(x, y, c)
	}
}
