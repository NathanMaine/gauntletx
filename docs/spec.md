# GauntletX build spec (as-built)

> **AUTHORITY NOTE:** for both system prompts, the text embedded in `gauntletx.py`
> (`SYSTEM_PROMPT`, `DRAFT_PROMPT`) is AUTHORITATIVE — it carries live-tested,
> model-behavior fixes this spec's base text predates. Rebuilding from this spec
> verbatim would regress them — the live-tested text in the code is authoritative.

*v0.1.1 folds in the transcript-analysis addendum
(`gx-spec-v2-addendum.md`): machine-checkable bar preference, boundaries field,
polish mode, honest run-expectation notes.*

Single-purpose tool: takes a user's goal + optional info, calls a local vLLM,
and generates a ready-to-paste **Gauntlet Loop prompt** in the style of Matt Shumer's
Claude of Duty prompt. Sibling of promptx (same author, same conventions).

Source material: Matt Shumer's Gauntlet Loop article
(https://somethingbig.ai/gauntlet-loop) plus three video-transcript analyses.


## Hard constraints

1. **Python stdlib only.** No pip installs, ever. This is what makes the
   container trivial. urllib for HTTP out, http.server + socketserver for HTTP in.
2. Python 3.9+ compatible (Mac has 3.14; container will be 3.12-slim).
3. One core file: `gauntletx.py`. Server mode + CLI mode in the same file.
4. Port **7332**.
5. Server binds 127.0.0.1 by default; `--host 0.0.0.0` flag for the container.

## The three-part anatomy (CRITICAL — from Matt Shumer's original prompt)

Every generated Gauntlet Loop prompt MUST have exactly this skeleton, in this order,
as plain flowing paragraphs (no headings inside the prompt itself):

1. **The Task (What)** — the goal at full ambition. Original example:
   "I want you to build a first-person shooter at the level of the most recent Call of Duty
   games. It should be utterly perfect, visually beautiful, with every single thing done at
   AAA quality—from textures to physics to anything you could think of."
2. **The Build Method (How)** — fan out sub-agents, loop each piece, separate harsh critic.
   Original example:
   "Fan out sub-agents and have sub-agents tackle each one individually so that the game is
   utterly perfect. You should /loop on each item and have a separate sub-agent check it
   visually to ensure it looks triple A. That separate sub-agent should be a really harsh
   critic, and if it doesn't look triple A it should keep going."
3. **The Bar to hit (When to stop)** — blind side-by-side against the concrete reference,
   don't stop until critics are wowed. Original example:
   "Don't stop until each sub-agent is utterly wowed with the quality when compared with the
   actual Call of Duty game. It should literally compare them side by side blind and say which
   one looks better. Do this in ThreeJS. /loop until it's utterly perfect. Fan out sub-agents
   and ultracode."

Note the style: imperative, conversational, zero architecture prescription. Implementation
constraints the user insists on (like "Do this in ThreeJS") get one short sentence near the
end, not a spec. Total prompt length target: 80–220 words (the original 80–180 predates the
boundaries / polish-mode sentences added in v0.1.1, which earn the extra length).

## The system prompt (BASE TEXT — the version in gauntletx.py is authoritative)

```
You are GauntletX. You write Gauntlet Loop prompts — the prompting method behind Matt
Shumer's "Claude of Duty" (a AAA-quality FPS built by Claude Code from one prompt).

A Gauntlet Loop prompt is given to an agentic coding harness (Claude Code or Codex). It
makes the agent iterate far past one-shot quality: a lead agent splits the goal into the
smallest pieces that can be improved separately; each piece gets a builder and a SEPARATE
harsh critic with fresh context; the critic blind-compares real output side by side against
a concrete reference bar, names the biggest remaining gap, and sends it back; the loops
keep running with no fixed round count until the user stops the run.

Your job: given a goal (and optionally references, constraints, hard boundaries, work
type, target harness, and whether this is a fresh build or a polish pass on an existing
one), produce (a) the strongest concrete quality bar, (b) one sentence on why it works,
and (c) the final ready-to-paste prompt.

THE BAR — the most important part:
- It must be something an agent can actually inspect and compare its work against:
  a named best-in-class product and its screenshots (games, apps), a set of named real
  websites (web design), exemplary paragraphs (writing), a test suite / latency target /
  failure-recovery test / security review / reference implementation (backend), real
  campaign examples (marketing).
- "Make it amazing", "production-ready", "keep improving" are NOT bars. Reject vagueness.
- Prefer a MACHINE-CHECKABLE bar whenever the domain allows one: a named test suite that
  must pass, a benchmark number that must move, a latency target, a failure-recovery
  drill, a migration that completes clean. Reserve blind side-by-side comparison for work
  a machine cannot score (visuals, prose, feel). Remember: the prompt does not describe
  the product — it describes who is allowed to call it finished.
- The bar does not need to be reachable. It sets direction and prevents the agent stopping
  at "pretty good for AI".
- If the user supplied references, pick the strongest (or combine into one comparable set).
  The user's own reference files count — photos, floor plans, brand/design systems, an
  existing codebase's test suite.
- If no good bar exists for the domain, make FINDING the bar the agent's first task: tell
  it to find a concrete comparison or measurement that plays the same role Call of Duty
  screenshots played for Claude of Duty, explain why it is a useful bar, then judge every
  round against it.

THE PROMPT YOU WRITE — exactly three parts, as plain flowing paragraphs, no headings:
1. The Task (What): the goal at full ambition, in the user's terms. Do NOT prescribe
   architecture, file structure, workstreams, or the decomposition. Give the destination,
   let the agent choose the route.
2. The Build Method (How): fan out sub-agents; break the goal into the smallest pieces
   that can be improved and judged separately (the agent decides the pieces); loop on each
   piece; every piece gets a separate sub-agent critic with fresh context that inspects the
   ACTUAL artifact (real pixels, running product, rendered page, test results, finished
   text) — never the builder's summary — and if it does not meet the bar, it names the
   single biggest remaining gap and sends it back to the builder for another round.
3. The Bar to hit (When to stop): don't stop until each critic is utterly wowed when the
   work is compared side by side, BLIND, against the bar; the critic says which one is
   better; keep looping until ours wins or the user stops the run. If the user has a hard
   implementation constraint, give it one short sentence here. For Claude Code, end with
   the harness features: sub-agents, /loop, and ultracode. For Codex, end with sub-agents
   and continuous iteration (no ultracode — that is a Claude Code feature). For Gemini
   CLI, end with sub-agents and continuous iteration (no ultracode or /loop — those are
   Claude Code features). For a local-model target (Qwen3 Coder Next, Qwen 3.8, DeepSeek
   V4 Flash), the prompt will be run by an agentic CLI driving that local model: end with
   the sentence 'Run builders and critics as separate sessions with fresh context, and
   keep looping.' — and never mention ultracode or /loop.
Also tell the lead agent (one sentence, in part 2 or 3) to maintain a simple live progress
page showing the work evolving — do not overspecify it.

BOUNDARIES: if the user gives hard boundaries, put them in ONE blunt sentence at the end
of part 3 (e.g. "Build it fully local and static; do not deploy anything, register
domains, or push anything live."). Tell the critics that crossing a boundary is an
automatic fail no matter how good the work looks.

POLISH MODE: if the user is polishing an existing build, part 1 names the existing
artifact and states that the job is to raise it to the bar WITHOUT drifting off-brief;
the bar must include the user's own brand/design references (not only external
best-in-class), and critics must fail work that drifts from the brief even when it looks
better in isolation.

STYLE: imperative, direct, conversational — like dictated speech, not a spec. 80–180 words
total. No bullet lists, no headings, no numbered rounds, no "phase 1". Every sentence earns
its place.

OUTPUT FORMAT — exactly these sections, nothing before the first heading:
### BAR
<the concrete bar, 1-3 sentences>
### WHY
<one sentence on why this bar works for this goal>
### PROMPT
<the ready-to-paste prompt and nothing else>
### NOTES
<1-4 short bullets. ALWAYS include one line of run expectations: this loop runs for
hours, consumes tokens heavily (comfortable on a subscription plan, real money on API
pricing), and will rarely stop on its own — watch the progress page and stop the run
when improvement per round gets small. Other bullets as useful: how to run it (paste
into Claude Code, /effort ultracode), one variation worth trying — like the article's
optional smoothing pass: a fresh agent at the end of each wave making the
separately-improved pieces feel like one thing.>
```

## User-message assembly (in gauntletx.py)

```
Goal:
<goal>

Mode: <"start fresh" or "polish an existing build">
Work type: <work_type or "auto-detect">
Target harness: <harness, default "Claude Code">
References / quality bars I already have:
<references or "none — choose or task the agent with finding one">
Hard constraints / must-haves:
<constraints or "none">
Hard boundaries (never cross):
<boundaries or "none">
```

Input caps (reject with 400 over): goal 8000 chars, references 8000, constraints 4000,
boundaries 2000. Goal required, non-empty after strip. mode is "fresh" (default) or
"polish"; unknown values fall back to fresh.

## vLLM client

- URL: env `GAUNTLETX_VLLM_URL`, default `http://127.0.0.1:8000/v1/chat/completions`.
- Model: env `GAUNTLETX_MODEL`; if unset, GET the sibling `/v1/models` endpoint (derive
  from the vllm URL) at first use and take `data[0]["id"]`; cache it; re-discover on 404.
  Currently serving: `sakamakismile/KAT-Coder-V2.5-Dev-NVFP4` (64k ctx).
- The server runs vLLM with `--reasoning-parser qwen3`: responses carry BOTH
  `reasoning_content` (thinking) and `content` (answer) — in streaming, deltas may have
  either field. Handle both; never mix them.
- Sampling: temperature env `GAUNTLETX_TEMPERATURE` default 0.7, max_tokens env
  `GAUNTLETX_MAX_TOKENS` default 8192, timeout env `GAUNTLETX_TIMEOUT` default 600s.
- Streaming: `"stream": true` upstream → SSE lines (`data: {...}`, ends `data: [DONE]`).
  Read line-by-line off the urllib response object.

## HTTP API

- `GET /` → the web UI (single embedded HTML string).
- `GET /api/version` → `{"version": VERSION, "model": <resolved or null>, "vllm_url": ...,
  "vllm_reachable": bool}` (reachability = quick /v1/models probe with ~3s timeout; never
  crash this endpoint).
- `POST /api/generate` body `{"goal": ..., "mode": "fresh"|"polish", "work_type": ...,
  "references": ..., "constraints": ..., "boundaries": ..., "harness": ...,
  "stream": true|false}`.
  - stream=true (UI default): respond `Content-Type: text/event-stream` and forward events
    as SSE frames, each `data: {"type": "reasoning"|"content"|"done"|"error", "text": ...}`.
    Use HTTP/1.0 close-delimited framing for this response (no Content-Length) and flush
    per event. On upstream failure mid-stream, emit a final `error` event.
  - stream=false (CLI + tests): block, then JSON
    `{"bar": ..., "why": ..., "prompt": ..., "notes": ..., "raw": ..., "reasoning_chars": n}`.
    Parse the `### BAR/WHY/PROMPT/NOTES` sections server-side (regex on `^### `); if
    parsing fails, still return `raw` with the other fields null — never 500 on a
    malformed model reply.
- Errors: JSON `{"error": ...}` with 400 (bad input) / 502 (vLLM unreachable/errored).
  502 message must include the vLLM URL it tried.

## Web UI (embedded in gauntletx.py, no external assets, no CDN)

Aesthetic: match the promptx / nas-home family — system font stack, dark default with CSS
variables, light theme via `[data-theme]` toggle (persist in localStorage). Reference vars:
dark `--bg:#0f1420 --panel:#171d2b --ink:#e8edf5 --muted:#94a0b4 --line:#26303f
--accent:#6ea8fe`; light equivalents like inventory.html. Max width ~880px, single column.

Form:
- Goal — textarea, required, placeholder with a real example goal.
- Mode — select: Start fresh (default) / Polish an existing build. Small muted hint next
  to it: "Best results: build a solid MVP first, then run a gauntlet loop to polish it.
  Cold-start loops optimize toward whatever the agent guesses."
- Work type — select: Auto / Game / Website or app / Writing / Backend or code / Design /
  Marketing / Research / Other.
- Target harness — select, on BOTH tabs, grouped via `<optgroup>`:
  Agentic CLIs — Claude Code (default) / Codex / Gemini CLI;
  Local models — Qwen3 Coder Next (local) / Qwen 3.8 (local) /
  DeepSeek V4 Flash (local);
  Online chat — Claude (web) / ChatGPT (web) / Google Gemini (web) / Grok (web).
- References or quality bar you already have — textarea, optional, placeholder explaining
  what a bar is ("e.g. real Call of Duty screenshots; 3 sites you admire; a test suite;
  your own reference photos or brand system").
- Hard constraints / must-haves — textarea, optional ("e.g. Three.js only; must run on...").
- Hard boundaries (never cross) — textarea, optional ("e.g. local only — no deploys, no
  domains, nothing live; don't touch prod; no paid APIs").
- Generate button (disabled while running), Stop button (aborts the fetch).

Streaming view:
- While reasoning streams: a muted, collapsed-by-default "model thinking" `<details>` box
  that fills live (auto-scroll), with a subtle spinner.
- Content streams into a live raw area; when `done`, parse `### ` sections client-side and
  render cards:
  - BAR card (labeled "The Bar"), WHY as its caption
  - PROMPT card — monospace, pre-wrap, the star of the page; "Copy prompt" button; also
    subtle inline labels above the three paragraphs if detectable is NOT required — keep
    the prompt text pristine (copy must be exactly the prompt).
  - NOTES card if present.
  - "Copy prompt" + "Copy all" + "Regenerate" buttons.
- If parsing fails, show raw output in a card with a copy button (never show nothing).
- Error state: readable message incl. which URL failed.
- History: keep the last 10 generations in localStorage (goal + prompt + timestamp), listed
  collapsed at the bottom, click to re-expand; a clear-history button.
- Footer: model + endpoint from /api/version, credit line
  "Method: Matt Shumer's Gauntlet Loop — somethingbig.ai/gauntlet-loop" (link), version.
- An anatomy hint under the form (small, muted), two lines: "A Gauntlet Loop prompt =
  The Task (what) → The Build Method (how) → The Bar (when to stop)." and "The prompt
  doesn't describe the product — it describes who's allowed to call it finished."
- Keyboard: Cmd/Ctrl+Enter submits.

## CLI mode

`python3 gauntletx.py "your goal"` → generates and prints. Flags: `--type`, `--refs`,
`--constraints`, `--boundaries`, `--polish` (sets mode=polish), `--harness`,
`--no-stream`, `--raw` (print raw model output incl. all sections), `--quiet` (prompt
only, for piping). Default streamed output: reasoning
suppressed, sections printed as they complete; `--verbose` shows reasoning to stderr.
With no positional goal → server mode: `--port` (default 7332), `--host` (default
127.0.0.1). Exit non-zero with a clear message when vLLM is unreachable.

## Aux files

- `README.md` — what it is, the method (three parts + credit/link to article and to
  github.com/mshumer + the meta-prompt provenance), quick start (CLI + server), env vars
  table (incl. GAUNTLETX_API_KEY), API reference, NAS deployment section (build/tag/
  compose, port 7332, `cp .env.example .env` on first deploy, the "EXACTLY ONE autostart
  mechanism" warning promptx uses), relationship to promptx, and a short "When this pays
  off" section with three honest rules from field experience: (1) machine-checkable done
  beats vibes; (2) polish a strong MVP rather than cold-start when the brief matters;
  (3) budget hours and tokens — the bar is directional, you are the stop condition.
- `CHANGELOG.md` — promptx-style; entries for 0.1.0 (initial) and 0.1.1
  (transcript-informed refinements: machine-checkable bar preference, boundaries field,
  polish mode, honest run-expectation notes).
- `VERSION` — `0.1.1`
- `LICENSE` — MIT, "Copyright (c) 2026 Nathan Maine"
- `gauntletx_version.py` — VERSION constant read pattern like promptx (or read VERSION
  file with fallback — match promptx's approach; check its promptx_version.py).
- `Dockerfile` — python:3.12-slim, stdlib only, non-root uid 1000, PYTHONDONTWRITEBYTECODE,
  EXPOSE 7332, CMD server on 0.0.0.0:7332, OCI labels, promptx style incl. comments.
- `docker-compose.yml` — image gauntletx:0.1.1, port 7332:7332, env_file .env,
  restart: unless-stopped, read_only: true, no-new-privileges, healthcheck via
  /api/version urllib probe. NO volume mounts (gauntletx touches no filesystem). Comment
  header in promptx's style explaining update/rollback.
- `.env.example` — all GAUNTLETX_* vars with defaults + comments. No secrets exist (local
  vLLM needs no key) — say so in a comment; include optional GAUNTLETX_API_KEY passthrough
  as a commented-out line ONLY if trivially supported in code (Authorization: Bearer header
  when set).
- `test_smoke.sh` — bash; starts nothing itself; takes BASE_URL (default
  http://127.0.0.1:7332); checks /api/version fields, POSTs a generate with stream=false
  and a tiny goal, asserts non-empty `prompt` containing no "### " headings, asserts `bar`
  non-empty, prints PASS/FAIL per check, non-zero exit on any FAIL.

- `.gitignore` — `.env`, `__pycache__/`, `.DS_Store`.

## Style rules for gauntletx.py

- Top-of-file docstring: what it is, the three entry forms, credit to the article.
- Comment density and tone like promptx server.py: explain WHY at decision points.
- No global mutable state beyond the resolved-model cache + a lock.
- ThreadingTCPServer with daemon threads; SIGINT clean shutdown.
- Every network read has a timeout. Every exception path returns a JSON error, not a
  traceback, except startup config errors which exit(1) with one clear line.
- Target length: whatever it takes, but expect ~700-1000 lines including the embedded UI.

## v0.2.0 — AI-drafted form ("Describe it" tab)

New flow: a tab where the user types a one-shot description of what they want; the Spark
model extrapolates it into the form fields; the user reviews/edits; then hits the normal
Generate. The manual form remains directly accessible — the draft step is optional.

### New endpoint

`POST /api/draft` body `{"description": "..."}` (required, cap 4000 chars, 400 over/empty).
Blocking only (no streaming — output is small). Returns
`{"goal","mode","work_type","references","constraints","boundaries","harness","raw"}`.
Server-side coercion after parsing: mode lowercased into {fresh, polish} else "fresh";
work_type must exactly match a form option else "Auto"; harness in {Claude Code, Codex,
Gemini CLI, Qwen3 Coder Next (local), Qwen 3.8 (local), DeepSeek V4 Flash (local),
Claude (web), ChatGPT (web), Google Gemini (web), Grok (web)}
else "Claude Code"; all fields trimmed; generate caps apply (goal 8000 etc.). Parsing
failure never 500s — return raw with other fields null, UI shows raw + keeps user text.
502-with-URL semantics identical to /api/generate. Reuses the existing blocking-call and
###-section-parsing plumbing with a different system prompt.

### DRAFT_PROMPT (embed VERBATIM as a second system prompt; KAT lesson applies —
OUTPUT FORMAT block + worked example, no abstract rules without an example)

```
You are GauntletX's intake assistant. The user describes, in a sentence or two, something
they want an AI coding agent to build or improve. Expand that into the GauntletX form
fields — extrapolate sensible context, but never invent specifics they did not imply.

FIELD RULES
- GOAL: 1-3 sentences, first person, at full ambition, ready to submit. Keep every
  concrete detail the user gave — paths, URLs, names, numbers, even placeholders like
  XXXXX — VERBATIM. A placeholder means the user will fill it in; carry it through.
- MODE: "polish" when they point at something that already exists (analyze, improve,
  fix, speed up, refactor, redesign); "fresh" when they are creating from nothing.
- WORK_TYPE: exactly one of: Auto, Game, Website or app, Writing, Backend or code,
  Design, Marketing, Research, Other.
- REFERENCES: suggest one concrete, inspectable quality bar the domain implies — prefer
  machine-checkable (a measured baseline, a test suite, a latency target) over
  named-product comparisons. End the suggestion with "[suggested — edit or replace]".
  Leave the section empty rather than inventing when nothing is implied.
- CONSTRAINTS: only what the user implied. Empty beats invented.
- BOUNDARIES: the safety limits an unattended multi-hour run needs for THIS ask (for
  anything existing/production-adjacent: work on a local copy, no deploys, nothing
  pushed live). Empty when nothing is implied.
- HARNESS: exactly one of: Claude Code, Codex, Gemini CLI, Qwen3 Coder Next (local),
  Qwen 3.8 (local), DeepSeek V4 Flash (local), Claude (web), ChatGPT (web),
  Google Gemini (web), Grok (web). "Claude Code" unless the user names
  another harness on that list — then copy that value exactly as written above.

OUTPUT FORMAT — exactly these sections, nothing before the first heading, empty sections
allowed (heading followed by blank line):
### GOAL
### MODE
### WORK_TYPE
### REFERENCES
### CONSTRAINTS
### BOUNDARIES
### HARNESS

EXAMPLE
Input: "i want to analyze this platform located here XXXXX and i want you to improve it. I need it to run faster"
### GOAL
Analyze the platform located at XXXXX and make it run dramatically faster — profile it, find the real bottlenecks, and cut response times without breaking anything that works today.
### MODE
polish
### WORK_TYPE
Backend or code
### REFERENCES
A measured performance baseline of the current platform (response times, throughput, load behavior) — the bar is a concrete, re-measured improvement against those numbers. [suggested — edit or replace]
### CONSTRAINTS
All existing functionality must keep working exactly as it does today.
### BOUNDARIES
Work on a local copy only — do not deploy, restart production services, or push anything live.
### HARNESS
Claude Code
```

### UI

- Tab bar at the top of the panel: "✨ Describe it" (default) and "Form". Plain buttons
  styled like the theme, active state underlined/accented; switching preserves all state.
- Describe tab: one textarea (cap 4000, placeholder is the worked example's input line),
  a "Draft the form →" button with running state, error display consistent with the
  generate flow. NEVER auto-generates: on success it populates the form fields, switches
  to the Form tab, briefly flash-highlights every field the draft filled (CSS transition,
  works in both themes), and leaves the user to review/edit and press Generate.
- Form tab: unchanged manual form; directly reachable at any time by clicking the tab.
- If draft parsing failed: stay on Describe tab, show raw output in the existing
  raw-fallback card style so the user can copy anything useful.

### Bookkeeping

- VERSION and gauntletx_version 0.2.0; compose image tag gauntletx:0.2.0; CHANGELOG entry
  ("0.2.0 — Describe-it tab: one-shot description drafted into the form by the local
  model; /api/draft").
- README: document the tab flow and /api/draft with the coercion rules.
- test_smoke.sh: add a draft check — POST the worked example's input, assert goal
  non-empty, mode is "fresh" or "polish", work_type is one of the allowed values.
- CLI unchanged this version (possible future: --draft).

## v0.2.1 — six-harness roster (bookkeeping)

Adds four target harnesses alongside Claude Code and Codex: Gemini CLI, Qwen3 Coder
Next (local), Qwen 3.8 (local), DeepSeek V4 Flash (local). The harness lists earlier in
this spec (SYSTEM_PROMPT part 3, DRAFT_PROMPT HARNESS rule, /api/draft coercion) were
updated in place to the six-value roster; the CHANGELOG 0.2.1 entry carries the change
narrative. Historical version strings above (Aux files `VERSION — 0.1.1`, compose
`gauntletx:0.1.1`, v0.2.0 bookkeeping) are what those sections shipped with and stay
as written.

### Bookkeeping

- VERSION and gauntletx_version 0.2.1; compose image tag gauntletx:0.2.1; CHANGELOG
  entry 0.2.1.
- `HARNESSES` whitelist tuple plus tolerant `coerce_harness()` (casefold, drop
  "(local)"-style qualifiers, prefix match — "qwen 3 coder" and the draft model's
  "Qwen3 Coder (local)" both land on "Qwen3 Coder Next (local)"; off-list still falls
  back to Claude Code), applied on every door: /api/draft, /api/generate, and the CLI
  `--harness`.
- DRAFT_PROMPT HARNESS rule carries nickname worked examples ("qwen 3 coder" → Qwen3
  Coder Next (local), etc.); SYSTEM_PROMPT part 3 anchors each harness's closing
  sentence with a worked example and pins the closer as the last sentence inside the
  third paragraph.

## v0.2.2 — ten-harness roster, chat targets, resubmit UX (bookkeeping)

Adds four online chat targets — Claude (web), ChatGPT (web), Google Gemini (web),
Grok (web) — for a ten-value roster in three groups (the order the UI `<optgroup>`s
show): Agentic CLIs — Claude Code (default), Codex, Gemini CLI; Local models — Qwen3
Coder Next (local), Qwen 3.8 (local), DeepSeek V4 Flash (local); Online chat — the four
(web) values. The harness lists earlier in this spec (UI select, /api/draft coercion,
DRAFT_PROMPT HARNESS rule) were updated in place to the ten-value roster, same
convention as v0.2.1; the authoritative prompt texts live in `gauntletx.py`.

### Chat-target prompt formatting (SYSTEM_PROMPT)

A normal chat cannot run a real gauntlet loop — no sub-agents, no /loop, no ultracode,
no live progress page. For the four (web) targets the generated prompt keeps The Task
and The Bar unchanged, but the Build Method paragraph becomes in-conversation rounds,
and all four share ONE exact closer (KAT lesson — a worked sentence, not a rule), the
final sentence of the third paragraph:

```
Work in rounds inside this conversation: build the full artifact, then switch to the
voice of a separate, harsh critic with fresh eyes — blind-compare it against the bar,
name the single biggest gap — then rebuild. Repeat every time I say continue.
```

A (web) prompt never mentions sub-agents, ultracode, /loop, or a live progress page;
the progress-page instruction is scoped to non-web harnesses only. The (web) pairing
joined the one-closer-per-prompt example block, and (web) NOTES always carry a bullet
that this is the chat adaptation of a method built for agentic harnesses — Claude Code
or Codex will go further on the same goal.

### Bookkeeping

- VERSION and gauntletx_version 0.2.2; compose image tag gauntletx:0.2.2; CHANGELOG
  entry 0.2.2.
- `HARNESSES` grown to the ten canonical strings above; `coerce_harness()` gains
  family aliases ahead of the generic prefix match: contains "cli" + gemini →
  Gemini CLI, bare "gemini" → Google Gemini (web); "claude code" → Claude Code, bare
  "claude"/"claude.ai" → Claude (web); "chatgpt"/"gpt" → ChatGPT (web); "grok" →
  Grok (web). All 27 v0.2.1 unit cases still pass; 20 new alias cases (47/47). Same
  three doors as before: /api/draft, /api/generate, CLI `--harness`.
- DRAFT_PROMPT: ten-value HARNESS enum with the new nickname worked examples ("I'll
  paste this into chatgpt" → ChatGPT (web)) plus a CHOSEN HARNESS rule with a
  worked-example line: a leading "Target harness already chosen by user: X" line makes
  HARNESS exactly X unless the description explicitly names a different target.
- UI: harness select on BOTH tabs (grouped identically, `<optgroup>` × 3), two-way
  synced as one state; a non-default Describe-tab choice reaches the drafter via the
  "already chosen by user" line; a drafted result updates both selects. Resubmit +
  dirty state on the Form tab: snapshot every form input after a successful
  generation; any change shows a stale banner near the results ("Form changed since
  this prompt was generated — resubmit to update it") with a highlighted "Resubmit ↻"
  button (same action as Generate); clears on resubmit or when values return to the
  snapshot; no banner before the first generation; Stop/error paths clear the
  snapshot. Both themes.

## v0.2.3 — structured status page toggle (bookkeeping)

An opt-in that DETERMINISTICALLY appends a fixed status-page contract to
generated prompts. harden_output philosophy: fixed text never goes through
the model — SYSTEM_PROMPT, DRAFT_PROMPT, and the user message are
byte-identical to 0.2.2, and the drafter never sees the toggle (it is not a
model input).

- `STATUS_CONTRACT` module constant, verbatim, one paragraph: a single
  auto-refreshing `progress.html` in the project root
  (`<meta http-equiv="refresh" content="10">`) with a header (project name /
  current phase / last-updated), stat cards (pieces passed, score vs the
  bar), a piece table (BUILDING / IN REVIEW / PASSED / BLOCKED, rounds,
  score, biggest remaining gap), and an append-only activity log with real
  timestamps written at event time — never backfilled, failures recorded the
  moment they occur. Final sentence: "Update the page every working turn."
  (the smoke test's assertion).
- `apply_status_contract(prompt, harness, flag)` — the unit-testable door
  logic: append `"\n\n" + STATUS_CONTRACT` iff the flag is on AND the
  harness is non-(web) AND a prompt exists; (web) is ignored, never an error
  (a chat target can't write files).
- `/api/generate` boolean `status_page` (default false). Blocking door:
  reflected into raw's `### PROMPT` section BEFORE parsing (span surgery like
  harden_output's), so `prompt` and `raw` always agree; unparseable raw
  passes through. Streaming door: no server-side frames — the UI appends
  client-side from an embedded copy templated into the page like
  `__VERSION__` (JSON string literal `__STATUS_CONTRACT__`), so SSE frame
  order is untouched.
- CLI `--status-page`: appended after parse on every parsing path
  (`--no-stream` via the shared blocking plumbing; streamed `--quiet`
  buffered; streamed sectioned output at PROMPT print time). (web) harness →
  stderr warning + skip. Streamed `--raw` stays verbatim passthrough with a
  stderr note.
- UI: "Structured status page (progress.html)" checkbox on BOTH tabs, two-way
  synced like the harness selects; hint "Appends a fixed page contract to the
  prompt — auto-refreshing, real timestamps, no simulation."; disabled with
  hint "chat targets can't write files" when a (web) harness is selected
  (wired into updateHnotes); joins FORM_IDS dirty tracking (a flip after
  generation trips the stale banner); captured at submit time; never part of
  the draft prefix.

### Bookkeeping

- VERSION and gauntletx_version 0.2.3; compose image tag gauntletx:0.2.3;
  CHANGELOG entry 0.2.3.
- `test_units.py`: 12 apply_status_contract cases (flag × harness family +
  no-prompt guards), 59/59 total.
- `test_smoke.sh`: one added check — stream=false generate with
  `status_page: true` asserts the prompt ends with the contract's final
  sentence.
- Parked as a future side project: a harvester that watches multiple builds'
  `progress.html` files and aggregates them into one dashboard — the fixed
  contract is its input format.

## v0.2.4 — Qwen 3.8 Max (API) harness (bookkeeping)

Eleventh target: the Token-Plan flagship driven by an agentic CLI (Qwen Code
in VSCode). Local-closer family; explicit qwen+max/api coercion branch (the
generic prefix loops cannot split mutual prefixes "qwen 3.8"/"qwen 3.8 max");
UI group renamed "Local & API models". Units 67/67; VERSION/compose 0.2.4.
