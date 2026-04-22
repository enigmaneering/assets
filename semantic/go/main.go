// Demo: print all 256 byte values as their Semantic Alphabet pictogram.
//
// The merged "Semantic Mono" font ships with TWO alphabet sets, each
// occupying one 256-codepoint block in the Private Use Area:
//
//   irrational set: U+E100 + N  -> free-form unique pictograms
//   rational  set: U+E200 + N  -> DecaCode (structured byte readout)
//
// Switch between them with the -set flag. The chart below renders
// whichever set you pick; the translation is always rune(base) + rune(b).
//
// "Can a terminal even do this?"  Yes — but the terminal has to render
// the chosen PUA block using a font that covers it. The font lives in
// the Private Use Area (no font ships glyphs there by default), so
// whichever installed font defines those codepoints wins fallback.
// Setup:
//
//  1. Install the TTF:
//       cp ../SemanticMono-Regular.ttf ~/Library/Fonts/        # macOS
//       cp ../SemanticMono-Regular.ttf ~/.local/share/fonts/   # Linux
//                                                              # (then fc-cache -f)
//  2. Point your terminal at Semantic Mono — the merged font covers
//     ASCII as JetBrains Mono and PUA blocks E100/E200 as the pictograms.
//  3. Run: go run .  (or: go run . -set rational)
//
// If you see tofu boxes (□) instead of pictograms, the font isn't being
// picked up for that PUA block.
package main

import (
	"flag"
	"fmt"
	"log"
	"strings"
)

// PUA base for each alphabet set; keep in sync with GLYPH_SETS in
// build_merged_font.py.
const (
	puaBaseIrrational = 0xE100
	puaBaseRational   = 0xE200
)

func main() {
	setName := flag.String("set", "irrational", "which alphabet to render: irrational | rational")
	flag.Parse()

	var puaBase rune
	switch *setName {
	case "irrational":
		puaBase = puaBaseIrrational
	case "rational":
		puaBase = puaBaseRational
	default:
		log.Fatalf("unknown set %q; expected 'irrational' or 'rational'", *setName)
	}
	fmt.Printf("alphabet: %s  (base U+%04X)\n\n", *setName, puaBase)

	// Column header: low nibble 0..F
	fmt.Print("    ")
	for col := 0; col < 16; col++ {
		fmt.Printf(" _%X", col)
	}
	fmt.Println()
	fmt.Println("   +" + strings.Repeat("---", 16))

	// 16 rows x 16 columns = 256 bytes
	for row := 0; row < 16; row++ {
		fmt.Printf("%X_ |", row)
		for col := 0; col < 16; col++ {
			b := byte(row*16 + col)
			// The key mapping: byte -> font codepoint.
			r := puaBase + rune(b)
			fmt.Printf(" %c ", r)
		}
		fmt.Println()
	}

	// Bonus: demonstrate encoding an arbitrary byte slice as a pictogram
	// string. This is how you'd render a real payload at runtime.
	fmt.Println()
	payload := []byte{0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE}
	fmt.Printf("payload %X -> %s\n", payload, bytesToGlyphs(payload, puaBase))
}

// bytesToGlyphs maps each byte to its PUA codepoint under `base` and
// returns the UTF-8 string. This is the translation layer any consumer
// needs — bytes on one side, font-renderable runes on the other.
func bytesToGlyphs(b []byte, base rune) string {
	runes := make([]rune, len(b))
	for i, v := range b {
		runes[i] = base + rune(v)
	}
	return string(runes)
}
