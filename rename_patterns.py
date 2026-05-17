#!/usr/bin/env python3
"""
Knitting Pattern File Renamer

Extracts author, pattern name, and garment type from PDF metadata and text content,
then renames files to a uniform convention: Author_PatternName_GarmentType.pdf

Usage:
    python rename_patterns.py [directory]              # Preview mode (default)
    python rename_patterns.py [directory] -i           # Interactive mode (confirm medium/low confidence)
    python rename_patterns.py [directory] -i --apply   # Interactive + apply renames
    python rename_patterns.py [directory] --apply      # Apply all renames (no confirmation)
"""

import os
import re
import subprocess
import sys
import csv
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Garment types to detect (order matters - more specific first)
# Check filename/title first, then text content (to avoid false positives from instructions)
GARMENT_TYPES = [
    "tank top", "crop top", "sweater dress", "sweater-dress",
    "cami", "camisole", "blouse",
    "cardigan", "pullover", "sweater", "jumper",
    "tee", "t-shirt", "top", "vest",
    "shawl", "wrap", "poncho", "cape",
    "slippers", "socks", "mittens", "gloves", "hat", "beanie", "cowl", "scarf",
    "skirt", "dress", "shorts", "pants",
    "blanket", "throw",
    "toy", "amigurumi", "plushie", "doll",
    "bag", "pouch",
]

# Additional keywords that indicate toy type (but shouldn't be stripped from pattern names)
TOY_INDICATORS = ["cow", "bull", "goose", "bunny", "bear", "cat", "dog", "elephant", "mouse"]

# Normalize garment types for output
GARMENT_NORMALIZE = {
    "cami": "camisole",
    "tee": "tee",
    "t-shirt": "tee",
    "jumper": "sweater",
    "sweater-dress": "sweater dress",
}

# Patterns to find author names - require capitalized proper names
AUTHOR_PATTERNS = [
    # "by First Last" - require capital letters for each word
    r"(?:by|BY)\s+([A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+[A-Z][a-zA-ZÀ-ÿ\-']+){0,3})",
    # "Designer: Name"
    r"(?:designer|Designer|DESIGNER)[:\s]+([A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+[A-Z][a-zA-ZÀ-ÿ\-']+){0,2})",
    # @username (uppercase)
    r"@([A-Z][A-Za-z0-9_]+)",
    # "Studio x Studio" or "Name x Name" collaboration
    r"^([A-Z][a-zA-ZÀ-ÿ\s]+\s+x\s+[A-Z][a-zA-ZÀ-ÿ]+)",
    # "Name Name - knitting pattern"
    r"([A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+[A-Z][a-zA-ZÀ-ÿ\-']+)+)\s*[-–—]\s*(?:knit|pattern|design)",
]

# Words that indicate we've gone past the author name
AUTHOR_STOP_WORDS = {"basic", "simple", "easy", "quick", "pattern", "sweater", "pullover",
                     "cardigan", "top", "tee", "shawl", "sock", "hat", "tank", "vest",
                     "size", "sizes", "sizing", "gauge", "yarn", "needle", "stitch", "row", "round",
                     "notes", "instructions", "about", "materials"}

# Words to strip from pattern names
STRIP_WORDS = [
    r"^(?:final|updated|rearranged|new|v\d+|version\s*\d*|eng|english|pdf|crop|set)\s*[-_]?\s*",
    r"\s*[-_]?\s*(?:final|updated|rearranged|v\d+|version\s*\d*|eng|english|pdf)$",
    r"(?:knitting\s*)?pattern",
    r"\bknitting\b",  # standalone "knitting"
    r"from\s+.*$",  # "from New Wave Knitting"
    r"^\d+[-_\s]*",  # Leading numbers
    r"[-_\s]*\d+$",  # Trailing numbers only if preceded by space/separator
    r"\s+no\s*\d+",  # "no 026"
]

# Additional words to strip from pattern names (garment types already get stripped separately)
PATTERN_STRIP_WORDS = ["knitting", "pattern", "crochet"]

# Additional author-related terms to remove from pattern names
AUTHOR_STRIP_PATTERNS = [
    r"\bMariia\s+Ermolova\b",
    r"\bPolushkabunny\b",
]


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
        parts.append(self._sanitize(self.pattern_name))
        if self.garment_type:
            parts.append(self._sanitize(self.garment_type.title()))

        return "_".join(parts) + ".pdf"

    def _sanitize(self, text: str) -> str:
        # Convert to title case, remove special chars, replace spaces with nothing
        text = text.strip()
        # Remove multiple spaces
        text = re.sub(r"\s+", " ", text)
        # Convert to CamelCase
        words = text.split()
        result = "".join(word.capitalize() for word in words)
        # Remove any remaining non-alphanumeric (except for accented chars)
        result = re.sub(r"[^a-zA-ZÀ-ÿ0-9]", "", result)
        return result


def get_pdf_metadata(pdf_path: Path) -> dict:
    """Extract PDF metadata using pdfinfo."""
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        metadata = {}
        for line in result.stdout.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip().lower()] = value.strip()
        return metadata
    except Exception:
        return {}


def get_pdf_text(pdf_path: Path, pages: int = 2) -> str:
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


def extract_author(text: str, metadata: dict, filename: str) -> Optional[str]:
    """Try to extract author from various sources."""
    # Clean text of newlines for pattern matching
    text_clean = re.sub(r"\s+", " ", text)

    # Priority 1: PDF metadata author field
    if metadata.get("author") and len(metadata["author"]) > 2:
        author = metadata["author"].strip()
        # Skip generic/tool names
        if author.lower() not in ["bo", "виктория", "unknown", "user"]:
            return author

    # Priority 2: "by Author" in filename
    match = re.search(r"\bby\s+([^.]+?)(?:\.pdf)?$", filename, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Priority 3: Author patterns in text (case sensitive to require proper capitalization)
    for pattern in AUTHOR_PATTERNS:
        match = re.search(pattern, text_clean)  # NOT case insensitive - require caps
        if match:
            author = match.group(1).strip()
            # Remove any trailing stop words that got captured
            words = author.split()
            while words and words[-1].lower() in AUTHOR_STOP_WORDS:
                words.pop()
            author = " ".join(words)
            # Skip if too short or looks like a garment type
            if len(author) > 2 and author.lower() not in GARMENT_TYPES:
                # Skip common false positives
                if author.lower() in {"the", "a", "an", "this", "that", "for", "with"}:
                    continue
                # Limit length
                if len(author) < 40:
                    return author

    # Priority 4: " - AUTHOR" pattern in filename
    match = re.search(r"\s*[-–—]\s*([A-Z][A-Z\s]+)(?:\.pdf)?$", filename)
    if match:
        return match.group(1).strip().title()

    return None


def extract_garment_type(text: str, filename: str, title: str) -> Optional[str]:
    """Detect garment type from filename/title first, then text."""
    # Priority 1: Check filename and title (most reliable)
    primary = f"{filename} {title}".lower()
    for garment in GARMENT_TYPES:
        if garment in primary:
            return GARMENT_NORMALIZE.get(garment, garment)

    # Priority 2: Check for toy indicators in filename/title
    for indicator in TOY_INDICATORS:
        if indicator in primary:
            return "toy"

    # Priority 3: Check text content (may have false positives)
    text_lower = text.lower()
    for garment in GARMENT_TYPES:
        # For text, require word boundary to avoid partial matches
        if re.search(rf"\b{re.escape(garment)}\b", text_lower):
            return GARMENT_NORMALIZE.get(garment, garment)

    # Priority 4: Check for toy indicators in text
    for indicator in TOY_INDICATORS:
        if re.search(rf"\b{re.escape(indicator)}\b", text_lower):
            return "toy"

    return None


def extract_pattern_name(metadata: dict, filename: str, text: str, author: Optional[str] = None) -> Optional[str]:
    """Extract the pattern name."""
    name = None

    # Priority 1: PDF title metadata (if meaningful and not junk)
    if metadata.get("title"):
        title = metadata["title"]
        # Skip if title looks like filename junk or contains underscores
        if not re.search(r"(?:final|updated|crop|set|v\d|_|luonnos|draft)", title, re.IGNORECASE):
            name = title

    # Priority 2: Parse from filename (users often curate filenames carefully)
    if not name or len(name) < 3:
        # Remove extension
        name = Path(filename).stem

    # Priority 3: If filename looks like junk, try text extraction
    if name and re.search(r"(?:final|updated|crop|set|v\d|_\d_)", name, re.IGNORECASE):
        # Look for pattern like "PATTERN NAME" or "Pattern Name" near start of text
        lines = text.strip().split("\n")[:10]
        for line in lines:
            line = line.strip()
            # Skip author lines, very short lines, lines with instructions, or garment-only lines
            if len(line) > 3 and len(line) < 50:
                # Skip if it's JUST a garment type
                line_lower = line.lower().strip()
                if line_lower in GARMENT_TYPES or line_lower in {"tank top", "sweater", "cardigan", "top", "pullover"}:
                    continue
                if not re.search(r"(?:by\s|@|designer|gauge|size\b|yarn|needle|stitch|no\.\s*\d|table|contents|message|tips)", line, re.IGNORECASE):
                    # Check if it looks like a title (letters, spaces, hyphen, slash)
                    if re.match(r"^[A-Z][A-Za-zÀ-ÿ\s\-/]+$", line):
                        name = line
                        break

    if name:
        # Clean up underscores and multiple spaces
        name = re.sub(r"[_-]+", " ", name)

        # Remove common prefixes/suffixes
        for pattern in STRIP_WORDS:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)

        name = re.sub(r"\s+", " ", name)
        # Remove "by Author" suffix
        name = re.sub(r"\s+by\s+.*$", "", name, flags=re.IGNORECASE)

        # Remove author name if we found it (avoid duplication)
        if author:
            # Escape special regex chars and make case insensitive
            author_pattern = re.escape(author)
            name = re.sub(rf"\b{author_pattern}\b", "", name, flags=re.IGNORECASE)

        # Remove additional author-related patterns
        for pattern in AUTHOR_STRIP_PATTERNS:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)

        # Handle CamelCase names (split them) BEFORE garment stripping
        if name and " " not in name and len(name) > 10:
            # Insert space before uppercase letters that follow lowercase
            name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
            # Also handle sequences like "ImA" -> "Im A"
            name = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", name)

        # Remove garment type from name (we'll add it separately)
        for garment in GARMENT_TYPES:
            name = re.sub(rf"\b{re.escape(garment)}\b", "", name, flags=re.IGNORECASE)

        # Remove additional pattern-related words
        for word in PATTERN_STRIP_WORDS:
            name = re.sub(rf"\b{word}\b", "", name, flags=re.IGNORECASE)

        name = re.sub(r"\s+", " ", name).strip()

        return name if len(name) > 1 else None

    return None


def analyze_pattern(pdf_path: Path) -> PatternInfo:
    """Analyze a single PDF and extract pattern info."""
    info = PatternInfo(original_path=pdf_path)

    filename = pdf_path.name
    metadata = get_pdf_metadata(pdf_path)
    text = get_pdf_text(pdf_path)

    # Check if text extraction worked
    if len(text.strip()) < 50:
        info.notes.append("No/little text extracted (scanned PDF?)")

    # Extract components
    info.author = extract_author(text, metadata, filename)
    info.garment_type = extract_garment_type(text, filename, metadata.get("title", ""))
    info.pattern_name = extract_pattern_name(metadata, filename, text, info.author)

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

    # Add notes about what's missing
    if not info.author:
        info.notes.append("Author not found")
    if not info.garment_type:
        info.notes.append("Garment type not detected")
    if not info.pattern_name:
        info.notes.append("Pattern name unclear")

    return info


def prompt_user(prompt: str, default: str = "") -> str:
    """Prompt user for input."""
    try:
        if default:
            response = input(f"{prompt} [{default}]: ").strip()
            return response if response else default
        else:
            return input(f"{prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)


def interactive_confirm(info: PatternInfo) -> PatternInfo:
    """Interactively confirm or edit pattern info for medium/low confidence."""
    print(f"\n{'='*60}")
    print(f"File: {info.original_path.name}")
    print(f"  Detected Author:  {info.author or '???'}")
    print(f"  Detected Pattern: {info.pattern_name or '???'}")
    print(f"  Detected Type:    {info.garment_type or '???'}")
    if info.notes:
        print(f"  Notes: {'; '.join(info.notes)}")
    print(f"  → Would rename to: {info.new_filename or 'SKIP'}")
    print()

    action = prompt_user("Accept (a), Edit (e), or Skip (s)?", "a").lower()

    if action == "s":
        info.pattern_name = None  # Mark to skip
        return info
    elif action == "e":
        # Allow editing each field
        new_author = prompt_user("  Author", info.author or "")
        new_pattern = prompt_user("  Pattern name", info.pattern_name or "")
        new_type = prompt_user("  Garment type", info.garment_type or "")

        if new_author:
            info.author = new_author
        if new_pattern:
            info.pattern_name = new_pattern
        if new_type:
            info.garment_type = new_type

        print(f"  → New filename: {info.new_filename}")

    return info


def process_directory(directory: Path, apply: bool = False, interactive: bool = False):
    """Process all PDFs in directory."""
    pdfs = list(directory.glob("*.pdf"))

    if not pdfs:
        print(f"No PDF files found in {directory}")
        return

    print(f"Found {len(pdfs)} PDF files\n")

    results = []
    for pdf in sorted(pdfs):
        print(f"Analyzing: {pdf.name[:50]}...")
        info = analyze_pattern(pdf)
        results.append(info)

    # Interactive confirmation for medium/low confidence
    if interactive:
        print("\n" + "=" * 80)
        print("INTERACTIVE REVIEW (medium/low confidence files)")
        print("=" * 80)

        for i, info in enumerate(results):
            if info.confidence in ("medium", "low"):
                results[i] = interactive_confirm(info)

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
            print(f"  → New:   {new_name}")
            renames.append((info.original_path, directory / new_name))
        else:
            print(f"  → SKIP (insufficient info)")
        print()

    # Write CSV report
    csv_path = directory / "rename_preview.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Original", "Author", "Pattern Name", "Garment Type", "Confidence", "New Name", "Notes"])
        for info in results:
            writer.writerow([
                info.original_path.name,
                info.author or "",
                info.pattern_name or "",
                info.garment_type or "",
                info.confidence,
                info.new_filename or "SKIP",
                "; ".join(info.notes)
            ])
    print(f"Preview saved to: {csv_path}")

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
            old_path.rename(new_path)
            print(f"  Renamed: {old_path.name} → {new_path.name}")
        print("\nDone!")
    elif not apply:
        print(f"\nTo review and apply:")
        print(f"  python {sys.argv[0]} {directory} -i --apply   # Interactive (confirm medium/low confidence)")
        print(f"  python {sys.argv[0]} {directory} --apply      # Apply all without confirmation")


def main():
    if len(sys.argv) < 2:
        directory = Path.cwd()
    else:
        directory = Path(sys.argv[1])

    apply = "--apply" in sys.argv
    interactive = "--interactive" in sys.argv or "-i" in sys.argv

    if not directory.is_dir():
        print(f"Error: {directory} is not a directory")
        sys.exit(1)

    process_directory(directory, apply, interactive)


if __name__ == "__main__":
    main()
