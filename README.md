<<<<<<< HEAD
# Knitting Pattern Renamer

A Python script that automatically renames knitting pattern PDFs to a consistent format:
`Author_PatternName_GarmentType.pdf`

No AI required - uses PDF metadata extraction and regex pattern matching.

## Requirements

- Python 3.6+
- `pdftotext` and `pdfinfo` (from poppler-utils)

### Install on Ubuntu/Debian/WSL:
```bash
sudo apt install poppler-utils
```

### Install on macOS:
```bash
brew install poppler
```

### Install on Windows:
Use WSL (Windows Subsystem for Linux) and follow the Ubuntu instructions above.

## Usage

```bash
# Preview mode - see what would be renamed (no changes made)
python3 rename_patterns.py /path/to/patterns

# Interactive mode - confirm medium/low confidence files before renaming
python3 rename_patterns.py /path/to/patterns -i --apply

# Apply all renames without confirmation
python3 rename_patterns.py /path/to/patterns --apply
```

If you're already in the patterns folder:
```bash
python3 rename_patterns.py . -i --apply
```

## Interactive Mode

For files with uncertain detection (medium/low confidence), you'll be prompted:

```
File: Blouse No 4 MFT.pdf
  Detected Author:  ???
  Detected Pattern: MFT
  Detected Type:    blouse
  → Would rename to: Mft_Blouse.pdf

Accept (a), Edit (e), or Skip (s)? [a]:
```

- **a** - Accept the detected values
- **e** - Edit author, pattern name, or garment type manually
- **s** - Skip this file (don't rename)

## Output

- Generates `rename_preview.csv` with all detected info for review
- Renames files to format: `Author_PatternName_GarmentType.pdf`
- Skips files that would have duplicate names

## How It Works

1. Extracts PDF metadata (title, author fields)
2. Extracts text from first 2 pages using `pdftotext`
3. Uses pattern matching to find:
   - Author: "by X", "@username", "Designer: X", PDF metadata
   - Pattern name: PDF title, filename, or text headers
   - Garment type: keyword matching (sweater, cardigan, tee, etc.)
4. Cleans up names (removes junk words, splits CamelCase)
5. Generates standardized filename

## Supported Garment Types

sweater, cardigan, pullover, tee, top, blouse, camisole, tank top, vest, dress, skirt, shawl, scarf, cowl, hat, socks, slippers, mittens, gloves, bag, pouch, toy, blanket

## Limitations

- Scanned PDFs (images) have no extractable text - relies on filename only
- Some patterns may need manual review (shown as "medium" confidence)
- Non-Latin characters in author names are preserved but may affect sorting
=======
# knitting-pattern-organisation
Automated Python script that renames the knitting patterns according to the designer and pattern name, as well as the garment type. Coding, knitting and organising? Best trio!
>>>>>>> 0f4e98fc3d713aae411eab4b457bf926430dceb5
