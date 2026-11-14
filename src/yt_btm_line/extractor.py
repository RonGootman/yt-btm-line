"""Caption-only retrieval. No translation, media downloads, or access-control bypasses."""

import html
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL

from .models import ExtractionError, Segment, Transcript

ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
MAX_SEGMENTS = 50_000
MAX_TEXT = 4_000_000


def video_id(value: str) -> str:
    value = value.strip()
    if ID.fullmatch(value):
        return value
    try:
        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or url.username or url.password or url.port:
            raise ValueError
        host = (url.hostname or "").lower()
        parts = url.path.strip("/").split("/")
        candidate = ""
        if host == "youtu.be" and len(parts) == 1:
            candidate = parts[0]
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if url.path == "/watch":
                ids = parse_qs(url.query).get("v", [])
                candidate = ids[0] if len(ids) == 1 else ""
            elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
                candidate = parts[1]
        if ID.fullmatch(candidate):
            return candidate
    except ValueError:
        pass
    raise ExtractionError(
        "invalid_url", "Expected a YouTube video URL or an 11-character video ID."
    )


def language_code(value: str | None) -> str | None:
    if value is not None and not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*", value):
        raise ExtractionError("invalid_language", "Use a language code such as en or he.")
    return value.lower() if value else None


def rank(code: str, generated: bool, preferred: str | None, original: str | None) -> tuple:
    # Explicit language is a constraint; otherwise prefer original language, then manual.
    base = code.lower().split("-")[0]
    return (
        bool(preferred and base != preferred.split("-")[0]),
        bool(original and base != original.lower().split("-")[0]),
        generated,
        base not in {"en", "he", "iw"},
        code,
    )


def normalize(rows: Any) -> list[Segment]:
    segments = []
    total = 0
    for row in rows:
        text = html.unescape(str(row["text"]))
        text = " ".join(text.split())
        if not text:
            continue
        try:
            segment = Segment(text=text, start=float(row["start"]), duration=float(row["duration"]))
        except (ValueError, TypeError) as exc:
            raise ExtractionError(
                "invalid_captions", "Captions contain invalid timestamps."
            ) from exc
        segments.append(segment)
        total += len(text)
        if len(segments) > MAX_SEGMENTS or total > MAX_TEXT:
            raise ExtractionError("too_large", "Transcript exceeds the extraction resource limit.")
    if not segments:
        raise ExtractionError("no_captions", "No nonempty captions were returned.")
    return sorted(segments, key=lambda s: s.start)


class TimeoutSession(requests.Session):
    def request(self, *args: Any, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", (5, 15))
        return super().request(*args, **kwargs)


def _info(vid: str) -> dict[str, Any]:
    with YoutubeDL(
        {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 15,
            "retries": 0,
            "extractor_retries": 0,
            "noplaylist": True,
        }
    ) as ydl:
        return ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)


def _fallback(vid: str, preferred: str | None, info: dict[str, Any]) -> Transcript:
    tracks = []
    for field, generated in (("subtitles", False), ("automatic_captions", True)):
        for code, formats in (info.get(field) or {}).items():
            # yt-dlp uses '-orig' for original automatic captions; exclude auto translations.
            if generated and not (code.endswith("-orig") or code == info.get("language")):
                continue
            clean = code.removesuffix("-orig")
            if preferred and clean.split("-")[0] != preferred.split("-")[0]:
                continue
            for fmt in formats:
                if fmt.get("ext") == "json3":
                    tracks.append((clean, generated, fmt))
                    break
    if not tracks:
        raise ExtractionError("no_captions", "No original captions match the requested language.")
    code, generated, fmt = min(
        tracks, key=lambda t: rank(t[0], t[1], preferred, info.get("language"))
    )
    # Caption URLs come only from YouTube's extractor; enforce HTTPS YouTube hosts, no redirects.
    parsed = urlsplit(fmt["url"])
    if parsed.scheme != "https" or not (
        parsed.hostname == "www.youtube.com" or (parsed.hostname or "").endswith(".youtube.com")
    ):
        raise ExtractionError("unsafe_caption_url", "Rejected an unexpected caption host.")
    with (
        TimeoutSession() as session,
        session.get(fmt["url"], stream=True, allow_redirects=False) as response,
    ):
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 8_000_000:
                raise ExtractionError("too_large", "Caption response exceeds 8 MB.")
    import json

    events = json.loads(data).get("events", [])
    rows = [
        {
            "text": "".join(s.get("utf8", "") for s in e.get("segs", [])),
            "start": e.get("tStartMs", 0) / 1000,
            "duration": e.get("dDurationMs", 0) / 1000,
        }
        for e in events
    ]
    return Transcript(
        video_id=vid,
        url=f"https://www.youtube.com/watch?v={vid}",
        transcript_language=code,
        transcript_type="automatic" if generated else "manual",
        extraction_method="yt-dlp",
        segments=normalize(rows),
    )


def extract(value: str, preferred_language: str | None = None) -> Transcript:
    vid, preferred = video_id(value), language_code(preferred_language)
    info: dict[str, Any] = {}
    warnings = []
    try:
        info = _info(vid)
    except Exception:  # noqa: BLE001 -- optional metadata must not prevent captions
        warnings.append("Source metadata unavailable; title, channel and publication may be null.")
    try:
        with TimeoutSession() as session:
            tracks = list(YouTubeTranscriptApi(http_client=session).list(vid))
            eligible = [
                t
                for t in tracks
                if not preferred or t.language_code.split("-")[0] == preferred.split("-")[0]
            ]
            if not eligible:
                raise ExtractionError("no_captions", "No captions match the requested language.")
            track = min(
                eligible,
                key=lambda t: rank(
                    t.language_code, t.is_generated, preferred, info.get("language")
                ),
            )
            result = Transcript(
                video_id=vid,
                url=f"https://www.youtube.com/watch?v={vid}",
                transcript_language=track.language_code,
                transcript_type="automatic" if track.is_generated else "manual",
                extraction_method="youtube-transcript-api",
                segments=normalize(track.fetch().to_raw_data()),
            )
    except Exception as exc:
        # Do not try another backend after an explicit restriction or authentication failure.
        if type(exc).__name__ in {
            "AgeRestricted",
            "RequestBlocked",
            "IpBlocked",
            "VideoUnavailable",
            "VideoUnplayable",
        }:
            raise ExtractionError(
                "restricted",
                "YouTube denied access or this video is unavailable. "
                "No restriction bypass was attempted.",
            ) from exc
        try:
            if not info:
                raise ExtractionError(
                    "extraction_failed", "Both caption and metadata retrieval failed."
                )
            result = _fallback(vid, preferred, info)
        except ExtractionError:
            raise
        except Exception as fallback_exc:
            raise ExtractionError(
                "extraction_failed",
                "Caption retrieval failed. Check network access "
                "and whether the video has publicly accessible captions.",
            ) from fallback_exc
        warnings.append("Primary caption retrieval failed; used yt-dlp captions.")
    result.title = info.get("title")
    result.channel = info.get("channel") or info.get("uploader")
    result.video_language = info.get("language")
    result.published_at = info.get("upload_date")
    result.warnings = warnings
    return result
