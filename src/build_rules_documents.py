#!/usr/bin/env python3
"""Convert text-based Comprehensive Rules files into retrieval-ready JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build JSONL rule documents from text files in docs/."
    )
    parser.add_argument(
        "--input-dir",
        default="docs",
        help="Directory containing rules text files",
    )
    parser.add_argument(
        "--output",
        default="data/rules_documents.jsonl",
        help="Path for the generated rule document JSONL",
    )
    return parser.parse_args()


def iter_source_files(root: Path) -> Iterable[Path]:
    for extension in ("*.txt", "*.md"):
        yield from sorted(root.glob(extension))


def split_sections(text: str) -> list[str]:
    sections = [section.strip() for section in text.split("\n\n")]
    return [section for section in sections if section]


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_path = Path(args.output)

    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    files = list(iter_source_files(input_dir))
    if not files:
        raise SystemExit(
            f"No .txt or .md files found in {input_dir}. Add Comprehensive Rules text there first."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with output_path.open("w", encoding="utf-8") as destination:
        for file_path in files:
            content = file_path.read_text(encoding="utf-8")
            for section_index, section in enumerate(split_sections(content), start=1):
                record = {
                    "source_file": file_path.name,
                    "section": section_index,
                    "text": section,
                }
                destination.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1

    print(f"Input dir: {input_dir}")
    print(f"Files: {len(files):,}")
    print(f"Sections: {written:,}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())