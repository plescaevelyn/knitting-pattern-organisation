# knitting-pattern-organisation

Automated Python scripts that rename knitting patterns according to the designer and pattern name, as well as the garment type. Coding, knitting and organising? Best trio!

Renames files to format: `Author_PatternName_GarmentType.pdf`

**Two versions available:**
- `rename_patterns.py` - Offline version using regex pattern matching (no AI required)
- `rename_patterns_ai.py` - AI-powered version using Claude API (more accurate but requires API key)

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

---

## AI-Powered Version

For better accuracy, especially with unusual pattern formats, use the AI-powered version.

### Additional Requirements

- `anthropic` Python package: `pip install anthropic`
- `ANTHROPIC_API_KEY` environment variable (get from https://console.anthropic.com/)

### Usage

```bash
# Set your API key
export ANTHROPIC_API_KEY=your_key_here

# Preview mode
python3 rename_patterns_ai.py /path/to/patterns

# Apply renames
python3 rename_patterns_ai.py /path/to/patterns --apply
```

### How It Works

1. Extracts text from first 3 pages using `pdftotext`
2. Sends text + filename to Claude API for intelligent extraction
3. Claude returns structured JSON with author, pattern name, and garment type
4. Normalizes author names using built-in aliases (e.g., "Maria M" → "Marias Verden")
5. Removes duplicate garment types from pattern names (e.g., "Tydes Cardigan" + cardigan → "Tydes_Cardigan")

### Adding Author Aliases

Edit `AUTHOR_ALIASES` in the script to standardize author name variations:
```python
AUTHOR_ALIASES = {
    "maria m": "Marias Verden",
    "leknit": "LeKnit",
    # Add more as needed
}
```

### Cost

Uses Claude Sonnet with ~256 tokens per file. Processing 100 patterns costs approximately $0.10-0.20 in API credits.
