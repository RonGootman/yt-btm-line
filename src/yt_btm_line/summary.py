"""Validate agent-written summaries and render them; never generate fabricated summaries."""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import validate

from .formatting import escape, link
from .models import Transcript


def instructions() -> str:
    return files("yt_btm_line").joinpath("resources/summary-prompt.md").read_text(encoding="utf-8")


def save_summary(data: dict[str, Any], transcript: Transcript, directory: Path) -> None:
    schema = json.loads(
        files("yt_btm_line").joinpath("resources/summary.schema.json").read_text(encoding="utf-8")
    )
    validate(data, schema)
    if data["source"] != transcript.model_dump(exclude={"segments", "warnings"}):
        raise ValueError("Summary source must match transcript metadata exactly.")
    segments = {s.start: s.text for s in transcript.segments}
    for item in [
        data["main_thesis"],
        *data["key_insights"],
        *data["actionable_takeaways"],
        *data["evidence_and_examples"],
        *data["caveats_and_uncertainty"],
    ]:
        for citation in item["citations"]:
            if (
                citation["start"] not in segments
                or citation["quote"] not in segments[citation["start"]]
            ):
                raise ValueError("Citation must use an exact segment start and verbatim quote.")
    lines = [
        f"# {escape(transcript.title or transcript.video_id)}",
        "",
        transcript.url,
        "",
        "## Source",
        "",
    ]
    lines.extend(
        f"- {key}: {escape(str(value)) if value is not None else 'Unknown'}"
        for key, value in data["source"].items()
    )
    for field, title in (
        ("main_thesis", "Main thesis"),
        ("key_insights", "Key insights"),
        ("actionable_takeaways", "Actionable takeaways"),
        ("evidence_and_examples", "Evidence and examples"),
        ("caveats_and_uncertainty", "Caveats and uncertainty"),
    ):
        lines.extend(["", f"## {title}", ""])
        items = [data[field]] if field == "main_thesis" else data[field]
        if not items:
            lines.append("None supported by the transcript.")
        for item in items:
            cites = " ".join(
                f"{link(transcript.url, c['start'])} “{escape(c['quote'])}”"
                for c in item["citations"]
            )
            lines.append(f"- **{item['attribution']}**: {escape(item['text'])} {cites}")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (directory / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
