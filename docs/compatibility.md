# Compatibility and verification

Checked in this cloud environment on 2026-11-14. No authenticated external assistant session,
mobile device, or authorized remote hosting was available. Passing Python tests does not prove
external integrations work.

| Environment | Implementation / requirements | Verification |
|---|---|---|
| Mac terminal | Python >=3.11, venv, CLI | CLI tested on Linux Python 3.12; macOS not run |
| Codex | Shared skill under ~/.agents/skills; shell and YouTube access | Skill extraction command attempted here; blocked by outbound proxy; full model summary not verified |
| Claude Code | Shared skill under ~/.claude/skills or local stdio MCP | Installation documented; actual client not run |
| ChatGPT Web | Account/plan with custom remote MCP capability, accessible authenticated HTTPS endpoint | Not connected/tested |
| Claude Web | Custom remote MCP connector and HTTPS endpoint | Not connected/tested |
| ChatGPT iOS/Android | Do not assume custom MCP availability matches web | Not verified; use manual browser fallback |
| Claude iOS/Android | Check connector availability for account/app version | Not verified; use manual browser fallback |
| Mobile browser fallback | Responsive HTML, copy/paste to assistant, authenticated remote access required | Local HTTP functional test passed; physical device/clipboard not tested |

## Current support research

Official documentation retrieval was attempted for these sources, but the environment proxy
returned `403 Forbidden` for both. Consequently this project makes **no assertion** about
current custom MCP support on either mobile app. Consult the current pages before deployment:

- OpenAI: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt-beta
- Anthropic: https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp
- MCP transport specification: https://modelcontextprotocol.io/specification/latest/basic/transports

Check your account's connector/app settings for custom remote servers, supported authentication,
plan availability and mobile invocation. Register the authenticated HTTPS `/mcp` endpoint if
supported. Test a public captioned video on web, then separately invoke on an actual phone,
check returned timestamps/language and confirm all pages were read. Record device/app version
and results before claiming support. A working web connection does not verify mobile access.

## Live extraction attempt

Ran `yt-btm-line extract 'https://www.youtube.com/watch?v=jNQXAC9IVRw'`.
The cloud outbound proxy denied YouTube access (`Tunnel connection failed: 403 Forbidden`).
The CLI returned structured `extraction_failed` with exit status 3; it produced no fabricated
transcript. This is an environment network blocker, not evidence of successful live extraction.
Allow required YouTube domains in environment networking before retrying. Typical destinations
include www.youtube.com, youtube.com and caption hosts returned by YouTube; diagnose additional
required hosts from denied requests rather than broadly opening networking.

## Security / limits

No URLs from captions are executed. Inputs are canonicalized to an allowlisted YouTube video
URL. Requests have connect/read timeouts; yt-dlp retries are disabled. These are per-request
limits, not a guaranteed total extraction deadline. Use an outer reverse-proxy/worker deadline
in hosted deployments. Extraction caps at 50,000 nonempty segments / 4 million text characters;
JSON3 fallback streaming caps at 8 MB. The primary third-party library buffers upstream data
before normalization, so a hosted worker needs external memory and time limits. MCP caches
at most eight transcripts and pages them without silently truncating. Web extraction has two
concurrent slots; production still requires an edge rate limiter and connection limits.
The stdlib web server is a local fallback, not a production Internet server.

Captions may omit visual information and automatic captions may be inaccurate. Quote membership
validation cannot detect an unsupported interpretation or guarantee high-quality summarization.
Review semantics. Automated fixtures are synthetic; no user transcripts are stored in Git.
