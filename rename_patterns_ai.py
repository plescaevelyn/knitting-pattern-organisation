#!/usr/bin/env python3
"""
Knitting Pattern File Renamer (AI-Powered Version)

Uses Claude API to intelligently extract author, pattern name, and garment type
from PDF content, then renames files to: Author_PatternName_GarmentType.pdf

Usage:
    python rename_patterns_ai.py [directory]                        # Preview mode
    python rename_patterns_ai.py [directory] --apply                # Apply renames
    python rename_patterns_ai.py [directory] --apply --organize     # Organize into folders by type

Requires:
    - ANTHROPIC_API_KEY environment variable
    - pip install anthropic
    - poppler-utils (pdftotext, pdfinfo)
"""

import os
import re
import json
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import anthropic

# Standardize author names (AI may return variations)
AUTHOR_ALIASES = {
    "maria m": "Marias Verden",
    "maria schei": "Marias Verden",
    "maria schei mogenstad": "Marias Verden",
    "marias verden": "Marias Verden",
    "mariasverden": "Marias Verden",
    "lene holme samsøe": "LeKnit",
    "lene holme samsoe": "LeKnit",
    "lene samsøe": "LeKnit",
    "lene samsoe": "LeKnit",
    "leknit": "LeKnit",
    "le knit": "LeKnit",
}


def normalize_author(author: str) -> str:
    """Standardize author name using aliases."""
    if not author:
        return author
    lookup = author.lower().strip()
    return AUTHOR_ALIASES.get(lookup, author)


# Initialize Claude client
# Supports ANTHROPIC_API_KEY directly, or Portkey proxy via env vars
def get_client():
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        # Portkey or custom proxy
        headers = {}
        custom_headers = os.environ.get("ANTHROPIC_CUSTOM_HEADERS", "")
        if custom_headers:
            for header in custom_headers.split(","):
                if ":" in header:
                    key, value = header.split(":", 1)
                    headers[key.strip()] = value.strip()
        return anthropic.Anthropic(
            base_url=base_url,
            api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN", "dummy"),
            default_headers=headers
        )
    return anthropic.Anthropic()

client = get_client()

# System prompt for extraction (cached for efficiency)
SYSTEM_PROMPT = """You are a knitting pattern metadata extractor. Given text extracted from a knitting pattern PDF, identify:

1. **Designer/Author**: The person or brand who designed the pattern. Look for:
   - "by [Name]", "Designer: [Name]", "@username", website URLs
   - Brand names like "PetiteKnit", "LeKnit", "My Favourite Things Knitwear", "Marias Verden"
   - Instagram handles often reveal the designer (e.g., @mariasverden = "Marias Verden")
   - Names in headers, footers, or copyright notices
   - If both a brand name and personal name appear, prefer the brand name

2. **Pattern Name**: The name of this specific pattern (not the designer name). Examples:
   - "Agnes Sweater", "Peacock Cardigan", "Musling Tee"
   - Usually appears prominently at the start

3. **Garment Type**: What type of item this pattern makes. One of:
   sweater, cardigan, pullover, tee, top, blouse, vest, camisole,
   dress, skirt, shorts, pants,
   shawl, scarf, cowl, wrap, poncho, cape,
   socks, slippers, mittens, gloves, hat, beanie,
   bag, pouch, blanket, throw, toy

Return ONLY a JSON object (no markdown, no explanation):
{"author": "Designer Name", "pattern": "Pattern Name", "type": "garment type"}

If you cannot determine a field with confidence, use null for that field."""


@dataclass
class PatternInfo:
    original_path: Path
    author: Optional[str] = None
    pattern_name: Optional[str] = None
    garment_type: Optional[str] = None
    confidence: str = "low"
    notes: list = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []

    @property
    def new_filename(self) -> Optional[str]:
        if not self.pattern_name:
            return None

        parts = []
        if self.author:
            parts.append(self._sanitize(self.author))

        # Strip garment type from end of pattern name if it duplicates
        pattern = self.pattern_name
        if self.garment_type:
            garment_lower = self.garment_type.lower()
            pattern_lower = pattern.lower()
            if pattern_lower.endswith(garment_lower):
                pattern = pattern[:-len(garment_lower)].strip()
            elif pattern_lower.endswith(garment_lower + "s"):  # plural
                pattern = pattern[:-(len(garment_lower)+1)].strip()

        parts.append(self._sanitize(pattern))
        if self.garment_type:
            parts.append(self._sanitize(self.garment_type.title()))

        return "_".join(parts) + ".pdf"

    def _sanitize(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        words = text.split()
        result = "".join(word.capitalize() for word in words)
        result = re.sub(r"[^a-zA-ZÀ-ÿ0-9]", "", result)
        return result


def get_pdf_text(pdf_path: Path, pages: int = 3) -> str:
    """Extract text from first N pages of PDF."""
    try:
        result = subprocess.run(
            ["pdftotext", "-f", "1", "-l", str(pages), str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout
    except Exception:
        return ""


def extract_with_ai(text: str, filename: str) -> dict:
    """Use Claude to extract pattern metadata."""
    if len(text.strip()) < 50:
        text = f"[Limited text extracted. Filename: {filename}]"

    # Truncate very long text to save tokens
    if len(text) > 8000:
        text = text[:8000] + "\n[... truncated ...]"

    user_prompt = f"""Filename: {filename}

Extracted text from PDF:
{text}

Extract the author, pattern name, and garment type. Return JSON only."""

    try:
        response = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=256,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }],
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Parse JSON response
        response_text = response.content[0].text.strip()
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = re.sub(r"```json?\n?", "", response_text)
            response_text = re.sub(r"\n?```$", "", response_text)

        return json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return {"author": None, "pattern": None, "type": None}
    except anthropic.APIError as e:
        print(f"  API error: {e}")
        return {"author": None, "pattern": None, "type": None}


def analyze_pattern(pdf_path: Path) -> PatternInfo:
    """Analyze a single PDF using AI."""
    info = PatternInfo(original_path=pdf_path)

    filename = pdf_path.name
    text = get_pdf_text(pdf_path)

    if len(text.strip()) < 50:
        info.notes.append("Limited text extracted")

    # Call Claude API
    result = extract_with_ai(text, filename)

    info.author = normalize_author(result.get("author"))
    info.pattern_name = result.get("pattern")
    info.garment_type = result.get("type")

    # Assess confidence
    found = sum([
        info.author is not None,
        info.pattern_name is not None,
        info.garment_type is not None
    ])

    if found == 3:
        info.confidence = "high"
    elif found == 2:
        info.confidence = "medium"
    else:
        info.confidence = "low"

    return info


def process_directory(directory: Path, apply: bool = False, organize: bool = False):
    """Process all PDFs in directory."""
    pdfs = list(directory.glob("*.pdf"))

    if not pdfs:
        print(f"No PDF files found in {directory}")
        return

    print(f"Found {len(pdfs)} PDF files")
    print("Using Claude AI for extraction (this uses API credits)\n")

    results = []
    for i, pdf in enumerate(sorted(pdfs), 1):
        print(f"[{i}/{len(pdfs)}] Analyzing: {pdf.name[:50]}...")
        info = analyze_pattern(pdf)
        results.append(info)

    # Generate report
    print("\n" + "=" * 80)
    print("RENAME PREVIEW")
    print("=" * 80 + "\n")

    renames = []
    for info in results:
        new_name = info.new_filename
        print(f"Original:  {info.original_path.name}")
        print(f"  Author:  {info.author or '???'}")
        print(f"  Pattern: {info.pattern_name or '???'}")
        print(f"  Type:    {info.garment_type or '???'}")
        print(f"  Confidence: {info.confidence}")
        if info.notes:
            print(f"  Notes:   {'; '.join(info.notes)}")
        if new_name:
            if organize and info.garment_type:
                folder = info.garment_type.title()
                new_path = directory / folder / new_name
                print(f"  → New:   {folder}/{new_name}")
            else:
                new_path = directory / new_name
                print(f"  → New:   {new_name}")
            renames.append((info.original_path, new_path))
        else:
            print(f"  → SKIP (insufficient info)")
        print()

    # Apply renames if requested
    if apply and renames:
        print("\nApplying renames...")
        for old_path, new_path in renames:
            if old_path == new_path:
                print(f"  Skip (same name): {old_path.name}")
                continue
            if new_path.exists():
                print(f"  Skip (exists): {new_path.name}")
                continue
            # Create folder if organizing
            new_path.parent.mkdir(exist_ok=True)
            old_path.rename(new_path)
            print(f"  Moved: {old_path.name} → {new_path.relative_to(directory)}")
        print("\nDone!")
    elif not apply:
        flags = "--apply"
        if organize:
            flags += " --organize"
        print(f"\nTo apply, run: python {sys.argv[0]} {directory} {flags}")


def main():
    # Check for API key (supports direct key or Portkey proxy)
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_BASE_URL"):
        print("Error: Set ANTHROPIC_API_KEY or configure Portkey via ANTHROPIC_BASE_URL")
        sys.exit(1)

    if len(sys.argv) < 2:
        directory = Path.cwd()
    else:
        directory = Path(sys.argv[1])

    apply = "--apply" in sys.argv
    organize = "--organize" in sys.argv

    if not directory.is_dir():
        print(f"Error: {directory} is not a directory")
        sys.exit(1)

    process_directory(directory, apply, organize)


if __name__ == "__main__":
    main()
