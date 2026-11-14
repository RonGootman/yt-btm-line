import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from yt_btm_line import extractor as ex
from yt_btm_line.formatting import markdown, timestamp, write_transcript
from yt_btm_line.models import ExtractionError, Segment, Transcript
from yt_btm_line.summary import save_summary

VID = "abcdefghijk"


def sample():
    return Transcript(
        video_id=VID,
        url=f"https://www.youtube.com/watch?v={VID}",
        transcript_language="he",
        transcript_type="manual",
        extraction_method="youtube-transcript-api",
        segments=[Segment(text="שלום evidence", start=2.75, duration=1.2)],
    )


@pytest.mark.parametrize(
    "value",
    [
        VID,
        f"https://youtu.be/{VID}?t=10",
        f"https://www.youtube.com/watch?v={VID}&t=1",
        f"https://m.youtube.com/shorts/{VID}",
        f"https://youtube.com/embed/{VID}",
        f"https://youtube.com/live/{VID}",
    ],
)
def test_urls(value):
    assert ex.video_id(value) == VID


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.com/watch?v=" + VID,
        "file:///etc/passwd",
        "https://youtube.com.evil.com/watch?v=" + VID,
        "https://youtube.com@evil.com/" + VID,
        "https://youtube.com:443/watch?v=" + VID,
        "https://youtu.be/" + VID + "/extra",
        "https://youtube.com/watch?v=" + VID + "&v=12345678901",
        "",
        "abcd",
    ],
)
def test_reject_urls(value):
    with pytest.raises(ExtractionError, match="Expected"):
        ex.video_id(value)


def track(language, generated):
    return SimpleNamespace(
        language_code=language,
        is_generated=generated,
        fetch=lambda: SimpleNamespace(
            to_raw_data=lambda: [{"text": language + " &amp; text", "start": 2.75, "duration": 1.2}]
        ),
    )


@pytest.mark.parametrize(
    ("preferred", "original", "expected", "kind"),
    [
        (None, "he", "he", "automatic"),
        (None, None, "en", "manual"),
        ("en", "he", "en", "manual"),
        ("he", "en", "he", "automatic"),
    ],
)
def test_selection(monkeypatch, preferred, original, expected, kind):
    monkeypatch.setattr(ex, "_info", lambda _: {"language": original, "title": "Title"})
    monkeypatch.setattr(
        ex,
        "YouTubeTranscriptApi",
        lambda **_: SimpleNamespace(
            list=lambda _: [track("he", True), track("en", True), track("en", False)]
        ),
    )
    result = ex.extract(VID, preferred)
    assert result.transcript_language == expected
    assert result.transcript_type == kind
    assert result.segments[0].start == 2.75
    assert result.title == "Title"


def test_normalization():
    result = ex.normalize([{"text": " שלום  &amp;\nworld ", "start": 1.25, "duration": 0.75}])
    assert result[0].text == "שלום & world"
    for value in [-1, float("nan"), float("inf")]:
        with pytest.raises(ExtractionError):
            ex.normalize([{"text": "x", "start": value, "duration": 1}])
    with pytest.raises(ExtractionError):
        ex.normalize([])


def test_fallback_and_failures(monkeypatch):
    monkeypatch.setattr(ex, "_info", lambda _: {"title": "Title"})
    monkeypatch.setattr(ex, "YouTubeTranscriptApi", Mock(side_effect=RuntimeError("network")))
    fallback = Mock(return_value=sample())
    monkeypatch.setattr(ex, "_fallback", fallback)
    assert ex.extract(VID).warnings
    fallback.assert_called_once()
    monkeypatch.setattr(
        ex, "_fallback", Mock(side_effect=ExtractionError("no_captions", "Missing"))
    )
    with pytest.raises(ExtractionError) as error:
        ex.extract(VID)
    assert error.value.code == "no_captions"


def test_restriction_does_not_fallback(monkeypatch):
    monkeypatch.setattr(ex, "_info", lambda _: {})
    blocked = type("RequestBlocked", (Exception,), {})
    monkeypatch.setattr(ex, "YouTubeTranscriptApi", Mock(side_effect=blocked()))
    fallback = Mock()
    monkeypatch.setattr(ex, "_fallback", fallback)
    with pytest.raises(ExtractionError) as error:
        ex.extract(VID)
    assert error.value.code == "restricted"
    fallback.assert_not_called()


def test_missing_language(monkeypatch):
    monkeypatch.setattr(ex, "_info", lambda _: {"title": "t"})
    monkeypatch.setattr(ex, "YouTubeTranscriptApi", lambda **_: SimpleNamespace(list=lambda _: []))
    with pytest.raises(ExtractionError) as error:
        ex.extract(VID, "he")
    assert error.value.code == "no_captions"


def test_format_and_json(tmp_path):
    t = sample()
    write_transcript(t, tmp_path)
    assert Transcript.model_validate_json((tmp_path / "transcript.json").read_text()) == t
    assert "שלום" in (tmp_path / "transcript.json").read_text()
    assert "&t=2s)" in markdown(t)
    assert timestamp(3661.99) == "01:01:01"
    with pytest.raises(ValidationError):
        Segment(text="x", start=-1, duration=0)


def test_summary_citations(tmp_path):
    t = sample()
    item = {
        "text": "A claim",
        "attribution": "creator_claim",
        "citations": [{"start": 2.75, "quote": "evidence"}],
    }
    data = {
        "source": t.model_dump(exclude={"segments", "warnings"}),
        "main_thesis": item,
        "key_insights": [item] * 3,
        "actionable_takeaways": [],
        "evidence_and_examples": [],
        "caveats_and_uncertainty": [],
    }
    save_summary(data, t, tmp_path)
    assert json.loads((tmp_path / "summary.json").read_text()) == data
    assert "&t=2s)" in (tmp_path / "summary.md").read_text()
    item["citations"][0]["start"] = 3
    with pytest.raises(ValueError, match="Citation"):
        save_summary(data, t, tmp_path)


def test_json3_fallback(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, _):
            yield json.dumps(
                {"events": [{"tStartMs": 1250, "dDurationMs": 500, "segs": [{"utf8": "שלום"}]}]}
            ).encode()

    class Session(Response):
        def get(self, url, **kwargs):
            assert url.startswith("https://www.youtube.com/")
            assert kwargs["allow_redirects"] is False
            return Response()

    monkeypatch.setattr(ex, "TimeoutSession", Session)
    info = {
        "language": "he",
        "subtitles": {
            "he": [{"ext": "json3", "url": "https://www.youtube.com/api/timedtext?v=abcdefghijk"}]
        },
        "automatic_captions": {
            "he-orig": [{"ext": "json3", "url": "https://www.youtube.com/api/timedtext"}]
        },
    }
    result = ex._fallback(VID, "he", info)
    assert result.transcript_type == "manual"
    assert result.segments[0].start == 1.25
    assert result.segments[0].text == "שלום"
    info["subtitles"]["he"][0]["url"] = "http://localhost/secret"
    with pytest.raises(ExtractionError) as err:
        ex._fallback(VID, "he", info)
    assert err.value.code == "unsafe_caption_url"


def test_translated_auto_not_selected():
    info = {
        "language": "he",
        "automatic_captions": {"en": [{"ext": "json3", "url": "https://www.youtube.com/x"}]},
    }
    with pytest.raises(ExtractionError) as err:
        ex._fallback(VID, "en", info)
    assert err.value.code == "no_captions"
