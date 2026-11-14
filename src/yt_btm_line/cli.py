"""Command-line entry point; summaries require a real agent/model step."""

import argparse
import json
import sys
from pathlib import Path

from jsonschema.exceptions import ValidationError

from .extractor import extract
from .formatting import write_transcript
from .models import ExtractionError, Transcript
from .summary import instructions, save_summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract YouTube captions without LLM credentials."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    extraction = commands.add_parser("extract", help="Write transcript.json and transcript.md")
    extraction.add_argument("url")
    extraction.add_argument("--language", help="Preferred original caption language, e.g. en or he")
    extraction.add_argument("--output", type=Path, default=Path("output"))
    commands.add_parser("prompt", help="Print shared agent summarization instructions")
    render = commands.add_parser(
        "render-summary", help="Validate an agent's JSON and write summary files"
    )
    render.add_argument("summary", type=Path)
    render.add_argument("--transcript", type=Path, required=True)
    render.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args()
    try:
        if args.command == "extract":
            transcript = extract(args.url, args.language)
            write_transcript(transcript, args.output)
            print(f"Wrote {len(transcript.segments)} segments to {args.output}")
        elif args.command == "prompt":
            print(instructions())
        else:
            transcript = Transcript.model_validate_json(args.transcript.read_text(encoding="utf-8"))
            save_summary(
                json.loads(args.summary.read_text(encoding="utf-8")), transcript, args.output
            )
    except ExtractionError as exc:
        print(json.dumps({"error": exc.as_dict()}), file=sys.stderr)
        return 2 if exc.code.startswith("invalid_") else 3
    except (OSError, ValueError, ValidationError) as exc:
        print(f"Output/validation error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    return 0
