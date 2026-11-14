"""Stable serialized transcript models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Segment(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    text: str
    start: float = Field(ge=0)
    duration: float = Field(ge=0)


class Transcript(BaseModel):
    schema_version: str = "1.0"
    video_id: str
    url: str
    title: str | None = None
    channel: str | None = None
    video_language: str | None = None
    published_at: str | None = None
    transcript_language: str
    transcript_type: Literal["manual", "automatic"]
    extraction_method: Literal["youtube-transcript-api", "yt-dlp"]
    segments: list[Segment]
    warnings: list[str] = Field(default_factory=list)


class ExtractionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}
