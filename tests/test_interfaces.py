import asyncio
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_engine import sample

from yt_btm_line import cli, mcp_server, web
from yt_btm_line.models import ExtractionError


def test_cli(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "extract", lambda *_: sample())
    monkeypatch.setattr(
        sys, "argv", ["yt-btm-line", "extract", "abcdefghijk", "--output", str(tmp_path)]
    )
    assert cli.main() == 0
    assert (tmp_path / "transcript.json").exists()
    monkeypatch.setattr(
        cli, "extract", lambda *_: (_ for _ in ()).throw(ExtractionError("invalid_url", "bad URL"))
    )
    assert cli.main() == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_url"


def test_mcp_paging(monkeypatch):
    monkeypatch.setattr(mcp_server, "cached_extract", lambda *_: sample())
    result = mcp_server.get_youtube_transcript("abcdefghijk", limit=1)
    assert result["segments"][0]["start"] == 2.75
    assert result["next_offset"] is None
    assert mcp_server.get_youtube_transcript("bad")["error"]["code"] == "invalid_url"
    assert mcp_server.get_youtube_transcript("abcdefghijk", limit=201)["error"]
    t = sample()
    t.segments = t.segments * 3
    monkeypatch.setattr(mcp_server, "cached_extract", lambda *_: t)
    assert mcp_server.get_youtube_transcript("abcdefghijk", limit=2)["next_offset"] == 2


def test_real_mcp_stdio():
    async def run():
        async with stdio_client(  # noqa: SIM117
            StdioServerParameters(
                command=sys.executable,
                args=["-c", "from yt_btm_line.mcp_server import main; main()"],
            )
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert tools.tools[0].name == "get_youtube_transcript"
                result = await session.call_tool("get_youtube_transcript", {"url": "not-a-url"})
                assert result.structuredContent["error"]["code"] == "invalid_url"
                prompt = await session.get_prompt("summary_instructions")
                assert "untrusted" in prompt.messages[0].content.text

    asyncio.run(run())


def test_web_functional(monkeypatch):
    monkeypatch.setattr(web, "extract", lambda *_: sample())
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base) as response:
            assert b"viewport" in response.read()
        request = urllib.request.Request(base + "/extract", data=b"url=abcdefghijk")
        with urllib.request.urlopen(request) as response:
            data = json.load(response)
            assert data["transcript"]["transcript_language"] == "he"
            assert "untrusted" in data["prompt"]
        request.add_header("Sec-Fetch-Site", "cross-site")
        try:
            urllib.request.urlopen(request)
            assert False, "cross-site request accepted"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
