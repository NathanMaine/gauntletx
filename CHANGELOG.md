# Changelog

Notable changes, newest first. The image tag carries the version, so what
`/api/version` reports is what this file explains.

## 0.2.13 — 2026-08-10

**The self-test now checks the model, not just the code**, and the button is on
both tabs.

0.2.11's self-test proved the code was sound and said nothing about whether a
run could actually start — which is the failure people hit most: the box is off,
the served model was swapped, a pinned name went stale. Three live checks added:

| Check | Catches |
|---|---|
| model endpoint | the backend being unreachable, or reachable but serving nothing |
| model name matches | a pinned `GAUNTLETX_MODEL` the server is not serving — vLLM serves one model and 404s any other name, so every generation dies at the door with nothing in the UI to explain it |
| generation round-trip | a backend that answers `/v1/models` but cannot actually generate |

The response now separates `code_ok` from `live_ok`, so "your code is fine, your
model is down" is distinguishable at a glance from a real regression. Verified
with a negative control against an unreachable endpoint: 5/6, `code_ok: true`,
`live_ok: false`.

### Changed

- The **Run self-test** button now appears on **both** tabs — beside *Generate*
  on the form tab as well as above *Draft the form* — sharing one handler that
  reports into whichever status line is on screen. The draft-tab twin follows
  the repo's `d`-prefix convention (`dselftest`), matching `dharness` and
  `dstatuspage`.
- Round-trip uses `max_tokens: 1`, so the check costs one token and reports its
  own latency.

## 0.2.12 — 2026-08-10

Packaging fix for 0.2.11. The Dockerfile copied only `gauntletx.py`,
`gauntletx_version.py` and `VERSION`, so the container had no test suites and
`/api/selftest` reported them `missing` — 3/5 on the NAS deployment while the
same commit passed 5/5 from a checkout. The self-test was the one feature that
had to work everywhere and it worked only where it was least needed.

`test_units.py` and `test_logic.py` now ship in the image. Stdlib-only, a few KB,
no runtime cost. Found by running the endpoint against the NAS rather than
assuming a green local run transferred.

## 0.2.11 — 2026-08-10

**A self-test you can run before spending a generation.** New `Run self-test`
button on the first tab and a `GET /api/selftest` endpoint behind it.

Two regressions shipped in two days and neither was catchable by reading the
diff or by checking Python syntax: a harness that silently coerced to the wrong
value (0.2.5), and a client-side function declared inside another function so
its call site threw and ate the whole result (0.2.10, see
`docs/issue-002-streaming-result-loss.md`).

The self-test runs, in-process:

| Check | Catches |
|---|---|
| `test_units.py` | harness coercion, both contract doors |
| `test_logic.py` | every pure function reachable without a network |
| `node --check` on the **served** JS | syntax errors in the page as rendered |
| top-level declaration of both contract appenders | a valid-but-unreachable nested declaration |

That last row exists because `node --check` **passed** on the code that caused
issue 002. It asserts the property that actually failed rather than the one that
is easy to test.

### Added

- `run_selftest()`, `GET /api/selftest`, and the button. Never raises — a
  crashed suite is reported as a failed suite. Skips the node checks with a
  pass and a note when node is not installed.
- **`test_logic.py` — 76 checks** covering the pure surface: `_num`,
  `_harness_key`, `models_url`, `_headers`, `is_web_harness`, `validate_inputs`,
  `build_user_message`, `parse_sections`, `_prompt_span`, `_repair_web_closer`,
  `harden_output`, both raw-reflection doors, `sse_events`, and `SectionStream`.
- Combined: **167 checks** across the two suites (91 + 76).

### On coverage

Every function that can be exercised without a network or a bound socket is now
covered. The remainder — `resolve_model`, `open_vllm`, `call_blocking`,
`generate_blocking`, `draft_blocking`, `run_server`, `run_cli`, `_print_final`,
`Handler`, `GXServer`, `version_info` — needs a live vLLM or a socket, and
"covering" them would mean asserting against mocks the suite wrote itself. The
exclusion list and the reason are in `test_logic.py`'s docstring rather than
implied by a percentage.

One test was wrong and the code was right: `build_user_message` does not omit
empty sections, it fills them with explicit `none` markers so the model knows a
section was considered rather than forgotten. The test now asserts the real
design.

## 0.2.10 — 2026-08-10

**Fixes a regression in 0.2.8 that 0.2.9 made unavoidable.** On the streaming
door, a completed generation would render nothing: the prompt vanished, the
Generate button stayed disabled, and no history entry was written. Inputs
remained on screen, so it looked like the run had been thrown away.

Two mistakes, both mine:

1. `applyBaselineContract` was declared **inside** `applyStatusContract` — the
   0.2.8 patch anchored on a line within its `for` loop — so the top-level call
   site hit `ReferenceError: applyBaselineContract is not defined`.
2. It called `sectionHeads()`, a helper that does not exist, and matched
   `'prompt'` in lowercase where the parser emits `'PROMPT'`.

The JavaScript was syntactically valid throughout, which is why nothing caught
it. The throw happened after the stream completed and skipped the render, the
history push and the button re-enable in one go.

0.2.8 shipped this latent — it only fires when the baseline toggle is on, and in
0.2.8 the toggle was opt-in and off by default. **0.2.9's auto-apply for
`Backend or code` turned a dormant bug into a certainty** for the most common
work type.

### Fixed

- Both contracts now go through one top-level `appendToPromptSection(raw,text)`;
  `applyStatusContract` and `applyBaselineContract` are one-line wrappers. The
  duplicated span surgery that made the mistake possible is gone.
- The client-side appends are wrapped in `try/catch`. A failed append now
  degrades to "no append" and surfaces as a lint warning — never to "no result".

### Verified

- The served JS is extracted and checked with `node --check`, then the contract
  functions are executed in node against a realistic `### PROMPT` payload:
  both defined at top level, text inserted inside the prompt section, `### NOTES`
  preserved, both contracts ordered correctly, unparseable raw passed through.
  Syntax checking alone would not have caught this — the bug was scoping.

## 0.2.9 — 2026-08-10

Makes the v0.2.8 baseline contract discoverable and mostly automatic.

### Changed

- The toggle **auto-applies for `Backend or code` and `Research`** — the work
  types whose bar is usually a number — and stays off elsewhere. A manual
  toggle takes ownership and is never overridden afterwards.
- **Keyed to work type, not harness, deliberately.** The failure it guards
  against is a property of the bar, not of the tool: a writing task on Claude
  Code does not need it, a backend task on a (web) chat target does. Keying it
  to the harness would have put it in the wrong twelve places.
- Label reworded from "Degenerate-baseline check" to **"Baseline sanity
  check"** — the original meant nothing to anyone who had not debugged the run
  that prompted it.
- Both tabs gained an explanatory hint, matching the status-page hint pattern
  that already existed and that 0.2.8 failed to follow. When the check
  auto-applies, the hint says so and how to turn it off.

### Docs

- `docs/issue-001-degenerate-metric.md` — the full issue and its resolution:
  symptom, root cause, why five separate guards all failed to fire, the two
  findings, the fix, verification, and what remains open.

## 0.2.8 — 2026-08-10

**Degenerate-baseline contract.** A new opt-in toggle, sibling to the status
page, that deterministically appends `BASELINE_CONTRACT`: any reported score
must be printed beside a constant-predictor score, a random-predictor score,
and the label distribution of both splits; a model that cannot beat the
constant predictor is a failed round.

Written after a real run produced **100% accuracy against an 82% target** and
the number turned out to be meaningless. A three-line `label_encode` compared
full domain strings (`'SAFe 6.0'`) against short class names (`'SAFe'`), never
matched, and returned `0` for every record — so all 192 training labels and all
49 holdout labels collapsed to one class. A constant predictor scores 100% on
that. 39 tests passed, loss decreased monotonically, and every downstream
signal confirmed success. Nothing was adversarial; a string comparison silently
converted a real task into a trivial one.

The contract is worded as a property of the **artifact** ("the evaluation
harness must print…"), not as a **behaviour** ("report baselines each round").
That is deliberate and is the run's other finding: `STATUS_CONTRACT` *was*
applied to that prompt, and the model honoured every structural clause in it
(auto-refresh meta, stat cards, piece table, activity log) while ignoring every
behavioural one — it invented a 07:45–08:31 activity log for a run that
happened 22:04–23:20, never updated the page mid-run, and logged no failures
despite five. Structure gets complied with; sustained behaviour does not.

### Added

- `BASELINE_CONTRACT`, `apply_baseline_contract(prompt, flag)` and
  `_baseline_contract_raw(raw, flag)` — same deterministic-append machinery as
  the status contract, so the text never passes through the model.
- `/api/generate` boolean `baseline_check`; `--baseline-check` on the CLI;
  a checkbox on both UI tabs, mirrored like the status-page pair.
- Client-side `applyBaselineContract` for the streaming door, from an embedded
  `__BASELINE_CONTRACT__`, so SSE frame order is untouched and the two appends
  cannot drift.
- `test_units.py`: 8 new cases (91/91 total).

### Notes

- **No harness gate.** Unlike the status page, this needs no filesystem, so
  (web) chat targets get it too — pinned by the unit cases.
- The CLI streaming printer now joins both contracts when both flags are set.

## 0.2.7 — 2026-08-09

Credit and attribution. The UI footer and the README's Method & credit section
now link this repo alongside Matt Shumer's method, and the credit section says
plainly what the tool adds on top of the idea: a hand-written Gauntlet Loop
prompt is only as good as the bar you happened to think of that day, and has to
be re-adapted by hand for each harness. gauntletx picks a bar the agent cannot
argue with and emits phrasing matched to what each of thirteen targets can
actually do.

Versioned rather than slipped in silently because the footer is served content,
and this project's rule is that what `/api/version` reports is what the
CHANGELOG explains.

### Changed

- UI footer: adds a `gauntletx on GitHub ↗` link after the method link.
- `README.md`: Method & credit links `NathanMaine/gauntletx` and
  `github.com/NathanMaine` after Matt Shumer's, with the free-form-prompting
  comparison stated explicitly.

## 0.2.6 — 2026-08-09

Thirteenth harness target: **Antigravity**, Google's agent-first IDE and CLI.
Its main agent decomposes a task and clones itself into parallel sub-agents, but
it has no `/loop` and no ultracode, so it joins the Codex / Gemini CLI / opencode
closer family.

**Gemini CLI is dead and the roster did not know.** Google retired it on
18 June 2026 and replaced it with Antigravity CLI; free, Google AI Pro and Ultra
access ended that day, and only Gemini Code Assist Standard/Enterprise licences
still run it. gauntletx had been generating prompts for a tool most users can no
longer execute. The target stays — enterprise licence holders still have it — but
it now carries a warning note pointing at Antigravity, which generates an
identical prompt.

### Added

- `Antigravity` across every layer: HARNESSES, SYSTEM_PROMPT closer family,
  NOTES harness families, DRAFT_PROMPT enum + nicknames ("anti gravity",
  "antigravity cli"), both UI selects, JS whitelist, CLI help, README.
- A per-target hnote for `Antigravity`: sub-agents yes, `/loop` and ultracode no,
  and the caveat that it defaults to a flash-tier Gemini model — strong at
  building, weaker as a critic, and to confirm the critic accepts images before
  trusting a blind side-by-side on a visual goal.
- A **warning** hnote for `Gemini CLI` — the first note on the roster that says a
  target may not run at all, rather than that it runs the method differently.
- `test_units.py`: 8 new cases (83/83 total).

### Naming

- The target is `Antigravity`, **not** `Google Antigravity`. The latter's
  matching key would prefix-match a bare "google" from the Agentic CLIs group,
  ahead of `Google Gemini (web)` in the Online chat group, silently breaking that
  alias. Regression-pinned: bare "google" and bare "gemini" both still resolve to
  `Google Gemini (web)`.

## 0.2.5 — 2026-08-09

Twelfth harness target: **opencode**. It has primary agents and sub-agents it
can delegate to, but no `/loop` and no ultracode, so it joins the Codex /
Gemini CLI closer family ("Use sub-agents heavily and keep iterating
continuously."). The Agentic CLIs group is now four.

The distinguishing property is that **opencode's quality is not opencode's** —
it is whichever provider the user has configured behind it. The prompt is told
never to assume a frontier model's headroom, and the UI note says so plainly,
including the failure mode that matters most for a Gauntlet Loop: a text-only
model cannot blind-compare screenshots and will fall back to reading its own
source and calling it good.

### Added

- `opencode` across every layer: HARNESSES, SYSTEM_PROMPT closer family,
  NOTES harness families, DRAFT_PROMPT enum + nicknames ("open code"), both UI
  selects, JS whitelist, CLI help, README.
- A dedicated per-target hnote for `opencode` — the first note keyed to an
  exact harness rather than a suffix family, covering the provider-quality
  caveat and the vision requirement for visual critics.
- `test_units.py`: 8 new cases (75/75 total), including three regression pins
  that a bare "code" still resolves to `Codex`.

### Fixed

- `coerce_harness("opencode")` silently returned `Claude Code`, so anyone who
  typed it got the wrong closer and a prompt citing `/loop` and ultracode that
  opencode does not have. Roster order matters here: `opencode` sits *after*
  `Codex` because the matcher walks `_HARNESS_KEYS` in order with a two-way
  prefix test, and a bare "code" must keep landing on `Codex`.

### Docs

- `docs/visual-gauntlet-loop.md` — how the loop produces AAA visuals, built on
  `mshumer/Claude-of-Duty`. The load-bearing finding: the critic must inspect
  real pixels via a deterministic capture harness, or "check it visually"
  silently becomes an agent reading source.
- `docs/adversarial-review-2026-08-09.md` — review of v0.2.4 proposing three
  changes (require the inspection harness; a held-out check on machine-checkable
  bars; a `Challenge` work type for attempt/score loops). Proposal only; no
  change was made to `SYSTEM_PROMPT`.

## 0.2.4 — 2026-08-08

Eleventh harness target: **Qwen 3.8 Max (API)** — the Token-Plan flagship
driven by an agentic CLI (e.g. Qwen Code in VSCode). Joins the local-model
closer family ("Run builders and critics as separate sessions with fresh
context, and keep looping." — no ultracode, no /loop) and the status-page
toggle. The "Local models" UI group is now "Local & API models".

### Added

- `Qwen 3.8 Max (API)` across every layer: HARNESSES, SYSTEM_PROMPT closer
  family, DRAFT_PROMPT enum + nicknames, both UI selects, JS whitelist,
  per-target hnote (now covers `(API)` suffixes), CLI help.
- `coerce_harness`: explicit qwen+max/api branch — required because
  "qwen 3.8" and "qwen 3.8 max" are mutual prefixes the generic loops cannot
  split; bare "qwen 3.8" stays local (regression-pinned).
- `test_units.py`: 8 new cases (67/67 total); roster tripwire updated
  deliberately.

## 0.2.3 — 2026-08-08

Structured status page toggle: an opt-in that DETERMINISTICALLY appends a
fixed contract to generated prompts pinning down exactly what the live
progress page must be — a single auto-refreshing `progress.html` in the
project root with a header, stat cards, a piece table, and an append-only
activity log with real timestamps, never backfilled, failures recorded the
moment they occur. Pure harden_output philosophy: the fixed text never goes
through the model. The model's behavior does NOT change — SYSTEM_PROMPT,
DRAFT_PROMPT, and the user message are byte-identical to 0.2.2, and the
drafter never sees the toggle.

### Added

- `STATUS_CONTRACT` module constant (the contract paragraph, verbatim; final
  sentence "Update the page every working turn.") and
  `apply_status_contract(prompt, harness, flag)` — the unit-testable door
  logic: append `"\n\n" + STATUS_CONTRACT` when the flag is on and the
  harness is a non-(web) target; (web) targets are ignored without error
  (a chat window can't write files); no prompt, no append.
- `/api/generate` boolean `status_page` (default false). Blocking door: the
  contract is reflected into raw's `### PROMPT` section BEFORE parsing, so
  the parsed `prompt` field and `raw` always agree; unparseable raw passes
  through untouched. Streaming door: the server sends no extra frames — the
  UI performs the identical append client-side from an embedded copy of the
  contract (templated into the page like `__VERSION__`, as a JSON string
  literal), so SSE frame order is untouched and the two appends can never
  drift apart.
- CLI `--status-page`: appended after parse on every parsing path —
  `--no-stream` (all output modes, via the same blocking plumbing as the
  API), streamed `--quiet` (buffered, appended before printing), and streamed
  sectioned output (appended to the PROMPT section at print time, when its
  body is complete). Combined with a (web) harness it warns on stderr and
  skips. Streamed `--raw` stays a verbatim passthrough (same reason the
  harden_output guards skip it) with a stderr note.
- UI: "Structured status page (progress.html)" checkbox on BOTH tabs, two-way
  synced like the harness selects, hint "Appends a fixed page contract to the
  prompt — auto-refreshing, real timestamps, no simulation." When a (web)
  harness is selected both checkboxes disable and the hint becomes "chat
  targets can't write files" (wired into the existing updateHnotes flow). The
  toggle joins FORM_IDS dirty tracking — flipping it after a generation trips
  the stale banner — and its state is captured at submit time like the goal.
  It is NOT part of the draft input: the drafter never sees it, because it is
  not a model input.
- `test_units.py`: 12 apply_status_contract cases (flag × harness family +
  no-prompt guards) — 59/59 total with the 47 coerce_harness cases.
- `test_smoke.sh`: one added check — a stream=false generation with
  `status_page: true` asserting the prompt ends with the contract's final
  sentence.

## 0.2.2 — 2026-08-08

Four online chat targets — Claude (web), ChatGPT (web), Google Gemini (web),
Grok (web) — plus a grouped ten-value harness roster, a harness select on the
Describe-it tab (two-way synced with the Form tab), and a resubmit/stale-state
indicator after generation. Late additions in the same release: per-target
notices under both harness selects (amber chat-adaptation warning for (web)
targets naming the selected tool, muted separate-sessions hint for (local)
targets, nothing for agentic CLIs); Regenerate hides while the form is dirty
so the stale banner's Resubmit is the single call to action; footer and README
credit reframed (method: Matt Shumer; diagnosis, architecture, verification:
Nathan Maine). The full roster, everywhere a harness is named, in
the three UI groups: Agentic CLIs — Claude Code (default), Codex, Gemini CLI;
Local models — Qwen3 Coder Next (local), Qwen 3.8 (local), DeepSeek V4 Flash
(local); Online chat — Claude (web), ChatGPT (web), Google Gemini (web),
Grok (web).

### Added

- Chat-target prompt formatting in SYSTEM_PROMPT: a normal chat cannot run a
  real gauntlet loop (no sub-agents, no /loop, no ultracode, no progress
  page), so for the four (web) targets the Task and the Bar stay unchanged
  but the Build Method paragraph becomes in-conversation rounds, and all four
  share ONE exact closer (KAT lesson: a worked sentence, not a rule): "Work
  in rounds inside this conversation: build the full artifact, then switch to
  the voice of a separate, harsh critic with fresh eyes — blind-compare it
  against the bar, name the single biggest gap — then rebuild. Repeat every
  time I say continue." The pairing joined the one-closer-per-prompt example
  block; the live-progress-page instruction is now explicitly scoped to
  non-web harnesses; and a (web) prompt's NOTES always include a bullet that
  this is the chat adaptation of a method built for agentic harnesses —
  Claude Code or Codex will go further on the same goal.
- `coerce_harness` family aliases, ahead of the generic prefix match:
  "gemini"+"cli" → Gemini CLI but bare "gemini" → Google Gemini (web);
  "claude code" → Claude Code but bare "claude"/"claude.ai" → Claude (web);
  "chatgpt"/"gpt" → ChatGPT (web); "grok" → Grok (web). All 27 v0.2.1 unit
  cases still pass; 20 new alias cases added (47/47) — the suite is committed
  as `test_units.py` (stdlib only, `python3 test_units.py`).
- DRAFT_PROMPT: ten-value HARNESS enum with the new nickname worked examples
  ("I'll paste this into chatgpt" → ChatGPT (web)), plus a CHOSEN HARNESS
  rule with its own worked-example line: a leading "Target harness already
  chosen by user: X" line makes HARNESS exactly X unless the description
  explicitly names a different target.
- UI: both harness `<select>`s use `<optgroup>` (Agentic CLIs / Local models /
  Online chat). The Describe-it tab gets its own harness select, two-way
  synced with the Form tab's (one state; the drafter receives a non-default
  choice via the "already chosen by user" line; a drafted result updates both
  selects).
- UI: after a successful generation the form is snapshotted (all textareas
  and selects, harness included); any change shows a stale banner near the
  results ("Form changed since this prompt was generated — resubmit to update
  it") with a highlighted "Resubmit ↻" button (same action as Generate). The
  banner clears on resubmit or when values return to the snapshot; it never
  appears before the first generation, and Stop/error paths clear the
  snapshot rather than mark half-finished output fresh. Works in both themes.

### Fixed (post-verification round, same day)

Live E2E on the real Spark vLLM found nondeterministic (temp 0.7) model
failures on the (web) targets and four smaller defects; all fixed and
re-verified live:

- (web)-target guards, server-side after generation (`harden_output`): the
  mandated verbatim (web) closer — paraphrased by the model in ~2/5 observed
  runs — is now verified and repaired deterministically instead of trusted;
  an agentic-feature leak into a chat prompt (sub-agents / ultracode / /loop /
  progress page, observed 1/5) triggers ONE regeneration on the blocking door
  and otherwise ships flagged (`lint` field / SSE `lint` frame). A repaired
  closer reaches the streaming UI as a full-raw `replace` frame before `done`;
  the CLI repairs where output is buffered (`--no-stream`, `--quiet`) and
  warns on stderr where it already streamed. Non-web harnesses pass through
  untouched.
- The Claude Code closer in SYSTEM_PROMPT is now an exact worked sentence
  ("Use everything Claude Code gives you: sub-agents, /loop, and ultracode.")
  — the old feature-list instruction invited the model to echo the
  instruction itself into the prompt ("End with the harness closer for
  Claude Code: …").
- NOTES guidance in SYSTEM_PROMPT is now per-harness-family worked sentences,
  fixing three observed wobbles: "watch the progress page" in (web) NOTES,
  "/effort ultracode in Claude Code" advice in a local-model prompt's NOTES,
  and the chat-adaptation caveat appearing when the target IS Claude Code.
- Describe-it textarea maxlength 4000 → 3935: a non-default harness rides to
  /api/draft as a worst-case 65-char "Target harness already chosen by
  user: …" prefix inside the same 4000-char DESC_MAX, so a max-length
  description the UI accepted used to 400 on submit.
- /api/draft's empty-GOAL salvage no longer nulls the harness: a goal-less
  description ("I'll paste this into chatgpt") returns the coerced HARNESS
  the model answered, and the UI lands it on both selects.
- History entries store the submit-time goal (captured in `run()`) instead of
  re-reading the textarea at render time — a goal edited mid-generation was
  saved paired with the previous goal's prompt (pre-existing since 0.1.0).
- `test_units.py` committed — the 47-case coerce_harness suite cited above is
  now in the repo and runnable by anyone verifying a release.

No behavior changes for the six existing harnesses: their closers, the
three-paragraph skeleton, and the coercion of every 0.2.1 spelling are
byte-identical.

## 0.2.1 — 2026-08-08

Four new target harnesses: Gemini CLI, plus three local models run through an
agentic CLI — Qwen3 Coder Next (local), Qwen 3.8 (local), DeepSeek V4 Flash
(local). The full list, everywhere a harness is named: Claude Code (default),
Codex, Gemini CLI, Qwen3 Coder Next (local), Qwen 3.8 (local), DeepSeek V4
Flash (local).

### Added

- SYSTEM_PROMPT part-3 harness rule extended (KAT lesson: exact sentences,
  not abstract rules): Gemini CLI ends with sub-agents and continuous
  iteration (no ultracode or /loop — Claude Code features); a local-model
  target ends with the literal sentence "Run builders and critics as separate
  sessions with fresh context, and keep looping." and never mentions
  ultracode or /loop. Codex and Gemini CLI close with the exact sentence
  "Use sub-agents heavily and keep iterating continuously." — every harness
  owns one closer, and the output contract shows the three-paragraph layout
  as a skeleton with both blank-line positions named, which stopped the
  local-model closer leaking into Claude Code / Gemini prompts.
- DRAFT_PROMPT HARNESS rule now enumerates all six exact values,
  WORK_TYPE-style, with Claude Code the default.
- `HARNESSES` whitelist tuple with tolerant coercion (`coerce_harness`:
  casefold, drop "(local)"-style qualifiers, prefix match — "qwen 3 coder"
  lands on "Qwen3 Coder Next (local)"; off-list becomes Claude Code),
  applied on every door: `/api/draft`, `/api/generate`, and CLI `--harness`.
  The UI draft-fill guards with the same list.
- UI Target-harness select and CLI `--harness` help list all six options.

No behavior changes for existing Claude Code / Codex flows.

## 0.2.0 — 2026-08-08

Describe-it tab: one-shot description drafted into the form by the local
model; `/api/draft`. The manual form is untouched and always one click away —
the draft step is optional and never generates on its own.

### Added

- "✨ Describe it" tab (the new default) next to the manual Form tab: type
  what you want in a sentence or two, hit "Draft the form →", and the Spark
  model expands it into the form fields. On success it populates the form,
  switches to the Form tab, and briefly flash-highlights every field it
  filled (both themes) — you review, edit, and press Generate yourself.
  Switching tabs preserves all state in both panes.
- `POST /api/draft` — blocking only (the output is small), body
  `{"description": "..."}`, required, cap 4000 chars (400 over/empty).
  Returns the drafted fields plus `raw`. Server-side coercion after parsing:
  `mode` lowercased into {fresh, polish} else fresh; `work_type` must exactly
  match a form option else Auto; `harness` in {Claude Code, Codex} else
  Claude Code; all fields trimmed and capped at the generate limits. A reply
  that can't be parsed returns `raw` with the other fields null — never a
  500 — and the UI shows it in a raw-fallback card while keeping your text.
  502 names the vLLM URL it tried, same as `/api/generate`.
- `DRAFT_PROMPT` — a second system prompt through the same blocking-call and
  section-parsing plumbing, with the same fixed-output-contract discipline as
  the main one: field rules plus a worked example, because the local model
  follows examples where it skims abstract rules.
- Smoke test: a draft check that POSTs the worked example's input and asserts
  goal non-empty, mode in {fresh, polish}, work_type in the allowed list.

CLI unchanged this version (possible future: `--draft`).

## 0.1.1 — 2026-08-07

Transcript-informed refinements — three recordings of the Gauntlet Loop used
in the wild, folded back into the meta-prompt. Nothing here contradicts
0.1.0; it sharpens it.

### Added

- `boundaries` — hard limits an unattended run must never cross (no deploys,
  no domains, don't touch prod). Optional field in the UI and the API (cap
  2000 chars), `--boundaries` in the CLI. The generated prompt states them in
  one blunt sentence at the end and tells the critics that crossing a
  boundary is an automatic fail no matter how good the work looks.
- `mode` — Start fresh (default) / Polish an existing build; `--polish` in
  the CLI. Field experience says cold-start loops optimize toward whatever
  the agent guesses; the working pattern is a solid MVP first, then the loop
  as a polish pass. In polish mode the prompt names the existing artifact,
  pulls the user's own brand/design references into the bar, and makes
  off-brief drift a critic fail even when the drifted version looks better
  in isolation.
- README: "When this pays off" — three honest rules from field experience
  (machine-checkable done beats vibes; polish a strong MVP rather than
  cold-start; budget hours and tokens — you are the stop condition).
- This changelog.

### Changed

- The meta-prompt now prefers a MACHINE-CHECKABLE bar wherever the domain
  allows one — a named test suite that must pass, a benchmark number that
  must move, a latency target, a failure-recovery drill, a clean migration —
  reserving blind side-by-side comparison for work a machine cannot score
  (visuals, prose, feel). A model grading its own homework gives itself an A.
  The user's own reference files (photos, floor plans, brand systems, an
  existing codebase's test suite) are now named as a valid bar class.
- NOTES output always includes one line of honest run expectations: hours of
  runtime, heavy token use (comfortable on a subscription plan, real money on
  API pricing), and a loop that will rarely stop on its own — watch the
  progress page and stop the run when improvement per round gets small.
- UI anatomy hint gained a second line: "The prompt doesn't describe the
  product — it describes who's allowed to call it finished."

## 0.1.0 — 2026-08-07

Initial release.

### Added

- `gauntletx.py` — the whole tool in one stdlib-only file: CLI mode, hosted
  server on port 7332, and the embedded web UI (dark/light theme, streamed
  reasoning in a collapsed box, result cards, copy buttons, last 10
  generations in localStorage).
- The GauntletX meta-prompt: three-part anatomy (The Task / The Build Method
  / The Bar), concrete-bar enforcement with a find-the-bar fallback when the
  domain has none, Claude Code and Codex phrasing, and the fixed
  `### BAR/WHY/PROMPT/NOTES` output contract.
- vLLM client for the Spark: model auto-discovery from `/v1/models` with
  re-discovery on 404, `reasoning_content` and `content` handled separately
  and never mixed, truncation detected via the missing `[DONE]` sentinel on
  both the streaming and blocking paths.
- HTTP API: `GET /api/version` (never crashes; reports reachability),
  `POST /api/generate` with SSE streaming and blocking JSON, tolerant section
  parsing that degrades to raw output instead of a 500.
- NAS deployment: Dockerfile (python:3.12-slim, non-root uid 1000, stdlib
  only), hardened compose (read-only rootfs, no-new-privileges, no volumes),
  healthcheck on `/api/version`, and `test_smoke.sh` for PASS/FAIL checks
  against a running instance.
