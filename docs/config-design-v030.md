# Config page design — proposed v0.3.0

*Status: design for review — not built.*

## The idea

A ⚙ Config tab that controls **which model writes your prompts and how**, with Auto as
the default that keeps today's zero-config behavior. Two providers, per-model profiles,
and — the part that matters most — **prompt variants**, because we proved during v0.1.1
that the system prompt is itself a per-model setting.

## Providers

| Provider | Endpoint | Key env | Privacy |
| --- | --- | --- | --- |
| **Local** — default | adjustable (see below) | none | 🔒 fully local |
| **DeepSeek** (direct) | `api.deepseek.com/chat/completions` | `GAUNTLETX_DEEPSEEK_KEY` | ⚠️ cloud — goal text leaves the LAN |
| **Qwen** (direct, DashScope) | `dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions` | `GAUNTLETX_QWEN_KEY` | ⚠️ cloud — goal text leaves the LAN |
| **OpenRouter** | `openrouter.ai/api/v1/chat/completions` | `GAUNTLETX_OPENROUTER_KEY` | ⚠️ cloud — goal text leaves the LAN |

All four are OpenAI-compatible chat completions — one client, four URL/auth configs.
promptx already integrates OpenRouter (see its `SUGGESTED` list with per-model pricing);
we reuse that pattern, including showing $/M next to each suggested model.

Why direct DeepSeek/Qwen when OpenRouter can route to the same families: first-party
pricing (DeepSeek's off-peak discounts apply only direct), keys you may already
hold, and DashScope-only Qwen variants. Model lists for the direct providers: attempt
the OpenAI-style `/models` endpoint opportunistically, fall back to a curated static
list + free-text ID (exact IDs confirmed against each provider's live catalog at build
time). A provider with no key present shows as inactive in the config UI ("key
missing — set GAUNTLETX_*_KEY"), never hidden.

One deliberately interesting note for the battery: KAT-Coder is qwen3-family. Qwen
cloud models may share its compliance quirks and could prefer the `local-tuned`
variant over `frontier` — the acceptance battery decides each model's default variant
empirically rather than assuming cloud = frontier.

**Local is fully adjustable too** — different local models are a first-class case, not
just a fallback:

- **Endpoint presets** for the common local servers: vLLM (`:8000`) and Ollama
  (`:11434`), plus a free-text URL for anything else (a second instance, another
  box on the LAN).
- **Model picker populated from the endpoint's own `/v1/models`** (both vLLM and Ollama
  expose it) — pick from what's actually loaded, or type a name. Auto mode keeps
  today's behavior: first discovered model wins.
- **Per-model profiles apply to local models equally.** The KAT lesson is KAT-specific:
  a different local model may follow abstract rules fine and prefer the `frontier`
  prompt variant, or need its own temperature. Swapping local models is exactly when
  the profile system earns its keep — and when the A/B compare (v0.4 idea below) gets
  interesting locally: KAT vs another local model on the same goal, zero cloud cost.

The privacy badge is not decoration: gauntletx is 100%-local today. Choosing OpenRouter
changes that, and the UI must say so at the point of choice.

## The KAT lesson, operationalized: prompt profiles

Verified during v0.1.1 (~6 live iterations): KAT-Coder follows OUTPUT FORMAT blocks and
worked example sentences; it ignores abstract rules. Every behavior fix that stuck was a
worked example. A frontier model (Claude, GPT, Gemini) follows abstract rules fine and
may do better with a leaner prompt.

So the config carries **two shipped SYSTEM_PROMPT variants**:

- `local-tuned` — today's prompt: worked examples, explicit layout spec (KAT-verified)
- `frontier` — same method, leaner phrasing: rules stated once, no worked-example
  scaffolding, trusts the model with style

Auto-selection: Local provider → `local-tuned`; OpenRouter → `frontier`. Overridable —
switching variants per model is exactly the experiment worth running.

## Per-model profiles

A profile = `{model_id: {temperature, max_tokens, prompt_variant, reasoning}}`.
Auto-applied when the active model matches; every field editable; "Reset to auto" wipes
back to defaults. Shipped defaults:

| Setting | Local (KAT) | OpenRouter frontier |
| --- | --- | --- |
| temperature | 0.7 | 0.7 (0.9 for creative work types worth trying) |
| max_tokens | 8192 | 4096 (no local reasoning stream to budget for) |
| prompt variant | local-tuned | frontier |
| reasoning | stream + show collapsed | request off / model default |

## Other adjustments (the "what else" list)

- **Timeout** — local gens are slow, cloud is fast; separate defaults per provider
- **Reasoning visibility** — show/hide the thinking box
- **Default harness** — persist Claude Code vs Codex choice
- **Default boundaries snippet** — your standard safety line, auto-filled into new forms
- **Prompt length target** — the 80–220 word envelope, adjustable (we learned the
  original 80–180 was too tight once boundaries/polish sentences were added)
- **History size** (default 10)
- **Cost readout** — when on OpenRouter, show tokens used + estimated cost per
  generation in the result footer (OpenRouter returns usage; pricing from the curated
  list)

## Storage — the read-only container constraint

The container runs with a read-only filesystem (deliberately). So the
server cannot persist config. Design that respects this:

- **Server defaults** come from env vars (`.env` in the container) — including the
  OpenRouter key (`GAUNTLETX_OPENROUTER_KEY`), the promptx way.
- **UI config lives in browser localStorage** and is sent as per-request overrides in
  the POST body (provider, model, temperature, max_tokens, prompt_variant, and
  optionally an OpenRouter key entered in the UI). Server validates every override
  against whitelists/ranges; nothing is written server-side.
- `GET /api/config` reports: server defaults, whether an env OpenRouter key exists,
  curated model list, available prompt variants — the UI merges this with localStorage.

Consequence: config follows the browser, not the server. Phone and laptop can have
different configs. Acceptable for a self-hosted tool; noted here so it's a decision, not a
surprise.

Key handling note: a UI-entered OpenRouter key sits in localStorage and travels per
request over LAN HTTP. Fine for this network's trust model; the env-var route is the
recommended one for container deployment and the config page says so.

## Auto config

"Auto" is a first-class mode, on by default, and visually distinct: **everything at
auto = exactly today's v0.2.0 behavior** (local server, discovered model, tuned
prompt, default sampling). Any override lights up an "custom" indicator with one-click
reset. Swapping the local model keeps working with zero config — that property is
non-negotiable.

## Worth considering for v0.4: A/B compare

"Different models, different results" begs for evidence: a compare button that runs the
same form through two configured models and renders the prompts side by side — the
gauntlet loop's own blind-comparison idea applied to choosing your generator model.
Deferred so v0.3.0 stays small, listed so it isn't forgotten.

## Model acceptance battery (the live-validation plan)

The same checks KAT-Coder had to pass in v0.1.1, packaged as `test_variant.sh <model>`
and run against any candidate model — cloud or local — before trusting it:

1. `### BAR/WHY/PROMPT/NOTES` sections parse
2. Exactly three paragraphs, no headings, no bullets
3. Boundary sentence AND critic auto-fail sentence present when boundaries given
4. No piece enumeration in the build-method paragraph
5. Polish-mode bar names the user's own references
6. NOTES includes the run-expectations line
7. Placeholders (XXXXX) survive the draft path verbatim

Two scenarios (fresh, polish+boundaries) × 2 runs per model for nondeterminism.
At build time: run it against the curated models of every cloud provider with a key
present — OpenRouter picks plus DeepSeek and Qwen direct (~20–30 calls, still well
under $1 at these providers' prices; DeepSeek and Qwen are among the cheapest). Afterward: it is the standing acceptance test for every model
added to the list — one command answers "does this model follow the method?", and its
failures feed that model's profile defaults (which worked example it needs back,
length line, etc.). Every check above corresponds to a failure KAT actually exhibited;
none is hypothetical.

## Decision 2026-08-10 — endpoint override is allowed

The open question was whether a per-request endpoint URL constitutes an SSRF hole.

**Resolved: allow it.** gauntletx is a LAN tool run on a network you control, not a
hardened public endpoint — see [threat-model.md](threat-model.md). Under that posture,
letting the browser point the server at another box on your own LAN is the feature, not
the vulnerability; having to edit a `.env` and restart a container to switch models is the
thing the config page exists to remove.

The scheme is still validated (`http`/`https` only) so a typo fails cleanly. Numeric
overrides are range-checked. Nothing is written server-side.

What this rules out is equally explicit: gauntletx is not to be placed on the public
internet or an untrusted network. The threat model lists what would have to be built first.

## Open questions for review

1. Sequencing: config page before or after the NAS deploy? (Suggested: after.)
2. OpenRouter curated list — which 5–6 models? (Suggestion: current Claude Sonnet,
   a GPT, Gemini Flash for cheap/fast, one strong open model, matching promptx's picks
   where sensible.)
3. ~~Live-validate the frontier variant at build time?~~ **Decided: yes** — via the
   model acceptance battery above; the project's core lesson is that prompt-behavior
   claims need live evidence.
