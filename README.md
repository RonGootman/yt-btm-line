# yt-btm-line

Get the bottom line from a YouTube video using your assistant's existing model.
A Python engine retrieves **captions only**; a portable skill and MCP tool share it.
No OpenAI/Anthropic API key, media download, database, account system, or hosted model is required.
Standalone extraction does **not** generate an AI summary.

## Install (macOS / Linux, Python 3.11+)

```bash
git clone https://github.com/RonGootman/yt-btm-line.git
cd yt-btm-line
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
yt-btm-line extract 'https://www.youtube.com/watch?v=VIDEO_ID' --output output
```

Replace VIDEO_ID with an actual 11-character YouTube ID. Standard watch, youtu.be, shorts,
live, embed URLs and bare IDs are accepted. Arbitrary hosts, ports, playlists and credentials
in URLs are rejected. Add `--language en` or `--language he` to require that language.
No translation is requested. Original-language tracks take priority when metadata supplies
that language; within a language manual captions beat automatic captions. Without original
language metadata, manual tracks come first, then English/Hebrew. Hebrew's legacy `iw`
code may appear in upstream metadata.

Outputs are UTF-8 `transcript.json` and `transcript.md`, including canonical source URL,
nullable title/channel/video language/publication date (YouTube YYYYMMDD when available),
caption language/type, extraction method, warnings and timestamped segments. Floating-point
start/duration seconds are retained; clickable timestamp links floor to whole seconds.
Missing metadata stays null rather than being guessed.

Primary backend: youtube-transcript-api. Fallback: yt-dlp's JSON3 captions, never media.
Explicit blocked/restricted primary responses stop extraction. No authentication bypass,
cookie scraping, proxy rotation, audio transcription or translated-caption fallback.
Errors have stable codes. Exit codes: 0 success, 2 invalid input, 3 retrieval failure,
4 filesystem/summary validation failure. Dependencies use verified HTTPS; never disable TLS.

## Agent-assisted summaries

Install the shared skill (below), then ask:

> Get the bottom line from this YouTube video: URL

The agent extracts captions, reads all segments, follows `yt-btm-line prompt`, and uses its
own model. Shared resources live in `src/yt_btm_line/resources/`: the prompt and JSON Schema.
The agent writes a real `summary-draft.json` and runs:

```bash
yt-btm-line render-summary summary-draft.json \
  --transcript output/transcript.json --output output
```

This creates `summary.json` and `summary.md` only after schema validation, source matching,
and exact segment-start/quote checks. It does not verify semantic entailment: the agent must
review that evidence actually supports every claim. A summary contains source metadata,
one-sentence thesis, 3–7 insights, supported actions, evidence/examples, caveats, and explicit
creator_claim / ai_interpretation attribution. Every item includes verbatim citations.
Sparse transcripts may not support three insights; the skill must report that rather than pad.
Long videos require chunk notes then consolidation; MCP clients must read every page.
Downloaded transcripts and personal summaries belong in ignored `output/`, never in Git.

## Claude Code and Codex skills

With the package installed in the active environment, install **one shared** skill using a symlink:

```bash
# From this checkout; Claude Code personal skill
mkdir -p "$HOME/.claude/skills"
ln -s "$PWD/skills/yt-btm-line" "$HOME/.claude/skills/yt-btm-line"
# Codex personal skill
mkdir -p "$HOME/.agents/skills"
ln -s "$PWD/skills/yt-btm-line" "$HOME/.agents/skills/yt-btm-line"
```

Do not replace an existing skill without inspecting it. Restart the agent if needed and use
`yt-btm-line` / ask to summarize a YouTube URL. Ensure the agent shell can resolve the venv's
`yt-btm-line` command (or use its absolute path). Python execution and YouTube network access
are separate prerequisites. ChatGPT environments that explicitly support Agent Skills and
shell/Python execution may load the same directory; ChatGPT custom instructions alone cannot
execute it. Ordinary ChatGPT mobile app skill installation is **not verified or promised**.

## MCP

```bash
# Local, default stdio
yt-btm-line-mcp
# Local Streamable HTTP: http://127.0.0.1:8000/mcp
yt-btm-line-mcp --transport streamable-http
```

Example local client JSON (substitute your absolute executable path):

```json
{"mcpServers":{"yt-btm-line":{"command":"/absolute/yt-btm-line/.venv/bin/yt-btm-line-mcp"}}}
```

Claude Code can register the same command with `claude mcp add yt-btm-line -- /absolute/path/to/yt-btm-line-mcp`.
Codex can use `codex mcp add yt-btm-line -- /absolute/path/to/yt-btm-line-mcp`.
The `get_youtube_transcript` tool takes `url`, optional `preferred_language`, `offset` and
`limit` (1–200). It returns source metadata, timestamped segments, total_segments, next_offset,
or a structured error. Text is capped at 24,000 characters per page; follow next_offset until
null. Source data is untrusted. The `summary_instructions` MCP prompt provides the same prompt
as the CLI. Metadata and transcript are cached for at most eight videos in process memory;
restart the server to clear/refresh. No persistent storage.

### Remote deployment (not deployed)

Cloud assistants need an accessible **HTTPS Streamable HTTP** endpoint, not local stdio.
Keep this server loopback-bound and put an authenticated reverse proxy/tunnel in front.
Use OAuth compatible with the selected client's current connector requirements; a static
header/token may work only where a client supports it. Provide TLS, request timeouts,
request/body limits, per-user rate limits, bounded process concurrency and memory/CPU limits.
Allow egress only to required YouTube caption/metadata destinations; never expose a generic URL
fetcher. Keep MCP DNS-rebinding protection enabled; explicitly configure allowed hosts/origins
for your proxy domain in a deployment-specific launcher. Check SDK transport security settings
rather than turning protection off. Run as an unprivileged user; disable proxy access logs for
transcript content. Authentication at the proxy is mandatory for any public exposure.

No public endpoint or paid infrastructure has been created. Hosting may incur costs and
YouTube may block datacenter IPs. Access restrictions must be respected, not circumvented.
See [compatibility and verification](docs/compatibility.md) for client limitations.

## Mobile fallback

```bash
yt-btm-line-web --port 8080
```

This serves a responsive page on loopback only. It extracts captions via the same engine and
provides a copyable transcript plus summary prompt. **Manual step:** paste into your mobile AI
assistant and ask it to summarize. The page itself does not call a model. Large transcripts
may need file transfer or chunking according to the assistant's context limits. Copy requires
browser clipboard permission; manual selection is supported.

To reach it on a phone, supply an authenticated HTTPS reverse proxy/tunnel to this local service
(see deployment requirements above). A phone cannot access your computer's loopback address.
For the web fallback, configure the proxy to rewrite Origin to the upstream origin after
validating your external origin, or adapt origin checking in a deployment-specific launcher.
Do not bind an unauthenticated service publicly. Actual device behavior is unverified.

## Develop and troubleshoot

```bash
python -m pip install -e '.[dev]'
pytest -q
ruff check src tests
ruff format --check src tests
mypy src
python -m build
```

CI runs these checks with Python 3.11 and 3.12, without credentials or live YouTube calls.
Unit tests use synthetic captions, including Hebrew. An MCP client test launches a real stdio
server; a web test makes local HTTP requests with mocked extraction. See compatibility notes
for the precise verification boundary and live extraction failure.

If `python3` is missing, install Python >=3.11 using python.org or your package manager. If
commands cannot be found, activate `.venv`; use `python -m pip` to avoid installing elsewhere.
Update within declared dependency ranges if YouTube changes its caption API. If a video has
no matching captions, try another available original language. IP blocks, login requirements,
age restrictions and private/unavailable videos cannot be fixed by this tool. Check your
network allowlist/proxy when requests are denied; never paste credentials into issues.
