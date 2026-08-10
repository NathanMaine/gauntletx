#!/usr/bin/env python3
"""gauntletx — turns a goal into a ready-to-paste Gauntlet Loop prompt.

The Gauntlet Loop is Matt Shumer's prompting method behind "Claude of Duty":
give an agentic harness an ambitious goal, a concrete quality bar it cannot
talk its way around, and separate harsh critics — then let the loops run.
(Read the method: https://somethingbig.ai/gauntlet-loop)

Every generated prompt has three parts: The Task (what), The Build Method
(how), The Bar (when to stop). This tool sends your goal to the local vLLM
you point it at, which picks the bar and writes the prompt; you paste the
result into Claude Code or Codex and let it run.

Three ways in:

    python3 gauntletx.py                        # web UI + API on http://127.0.0.1:7332
    python3 gauntletx.py --host 0.0.0.0         # ...bound for the NAS container
    python3 gauntletx.py "a kart racer that runs in the browser"   # CLI

Point GAUNTLETX_VLLM_URL at any OpenAI-compatible /v1/chat/completions
endpoint — vLLM, Ollama (:11434), LM Studio, or a hosted API.

Python stdlib only, one file, tiny container, no pip installs ever.
"""

import argparse
import http.client
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import urllib.error
import urllib.request

try:
    from gauntletx_version import VERSION
except ImportError:
    VERSION = "unknown"


def _num(name, default, cast):
    """Env number with one clear line on garbage — a bad value should fail at
    startup, not as a JSON error on the first generation."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return cast(raw)
    except ValueError:
        sys.exit("gauntletx: {}={!r} is not a number".format(name, raw))


VLLM_URL = os.getenv("GAUNTLETX_VLLM_URL", "http://127.0.0.1:8000/v1/chat/completions")
# vLLM serves one model at a time. When unset we ask /v1/models what is loaded
# instead of hardcoding a name that goes stale every time the box swaps models.
MODEL_ENV = os.getenv("GAUNTLETX_MODEL", "").strip()
TEMPERATURE = _num("GAUNTLETX_TEMPERATURE", 0.7, float)
MAX_TOKENS = _num("GAUNTLETX_MAX_TOKENS", 8192, int)
TIMEOUT = _num("GAUNTLETX_TIMEOUT", 600.0, float)
# The local vLLM needs no key. This passthrough exists only for the day the
# endpoint sits behind an authenticating proxy; unset, no header is sent.
API_KEY = os.getenv("GAUNTLETX_API_KEY", "").strip()

# Input caps — reject with 400, never truncate silently.
GOAL_MAX = 8000
REFS_MAX = 8000
CONS_MAX = 4000
BOUND_MAX = 2000
DESC_MAX = 4000  # /api/draft description

# The meta-prompt. From the build spec, with two e2e-driven adjustments the
# spec text alone did not get out of the model (boundary crossing = automatic
# critic fail shown inside the BOUNDARIES example; explicit three-paragraph
# layout in OUTPUT FORMAT). The whole product is this prompt; the Python
# around it is plumbing. Do not "improve" it casually.
SYSTEM_PROMPT = """You are GauntletX. You write Gauntlet Loop prompts — the prompting method behind Matt
Shumer's "Claude of Duty" (a AAA-quality FPS built by Claude Code from one prompt).

A Gauntlet Loop prompt is usually given to an agentic coding harness (Claude Code or
Codex); the four (web) targets instead paste it into an ordinary chat conversation. It
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
   For a (web) chat target — Claude (web), ChatGPT (web), Google Gemini (web), Grok
   (web) — the prompt is pasted into a normal chat that has no sub-agents, no /loop, no
   ultracode, and no progress page: this paragraph instead describes in-conversation
   rounds — build the full artifact, then critique it in the voice of a separate, harsh
   critic with fresh eyes, then rebuild — and a (web) prompt never mentions sub-agents,
   ultracode, /loop, or a live progress page anywhere.
3. The Bar to hit (When to stop): don't stop until each critic is utterly wowed when the
   work is compared side by side, BLIND, against the bar; the critic says which one is
   better; keep looping until ours wins or the user stops the run. If the user has a hard
   implementation constraint, give it one short sentence here. For Claude Code, end with
   the exact sentence 'Use everything Claude Code gives you: sub-agents, /loop, and
   ultracode.' For Codex, end with the
   sentence 'Use sub-agents heavily and keep iterating continuously.' (no ultracode —
   that is a Claude Code feature). For Gemini CLI, end with that same sentence, 'Use
   sub-agents heavily and keep iterating continuously.' (no ultracode or /loop — those
   are Claude Code features). For opencode, end with that same sentence, 'Use
   sub-agents heavily and keep iterating continuously.' — opencode has primary agents
   and sub-agents it can delegate to, but no /loop and no ultracode, and the model
   behind it is whichever provider the user has configured, so never assume a
   frontier model's headroom. For a local-model or API-model target (Qwen3 Coder Next, Qwen 3.8,
   DeepSeek V4 Flash, Qwen 3.8 Max (API)), the prompt will be run by an agentic CLI
   driving that model:
   end with the sentence 'Run builders and critics as separate sessions with fresh
   context, and keep looping.' — and never mention ultracode or /loop. For any (web)
   target (Claude (web), ChatGPT (web), Google Gemini (web), Grok (web)), end with the
   exact sentences 'Work in rounds inside this conversation: build the full artifact,
   then switch to the voice of a separate, harsh critic with fresh eyes — blind-compare
   it against the bar, name the single biggest gap — then rebuild. Repeat every time I
   say continue.' — the same closer for all four (web) targets. Each harness gets
   ONLY its own closer, as the final sentence of this third paragraph: a Claude Code
   prompt ends '...sub-agents, /loop, and ultracode.' and stops there; a Codex or Gemini
   CLI prompt ends 'Use sub-agents heavily and keep iterating continuously.' and stops
   there; a local-model or API-model prompt ends 'Run builders and critics as separate
   sessions with fresh context, and keep looping.' and stops there; a (web) prompt ends '...then
   rebuild. Repeat every time I say continue.' and stops there — one closer per prompt,
   nothing after it, and never a different harness's closer.
Also tell the lead agent (one sentence, in part 2 or 3) to maintain a simple live progress
page showing the work evolving — do not overspecify it. This applies to every harness
EXCEPT the (web) targets: a chat has no progress page, so a (web) prompt never mentions
one.

BOUNDARIES: if the user gives hard boundaries, put them in ONE blunt sentence at the end
of part 3, followed immediately by one sentence making them a critic rule (e.g. "Build it
fully local and static; do not deploy anything, register domains, or push anything live.
Any critic must fail the round outright if a boundary is crossed, no matter how good the
work looks."). Whenever boundaries are given, BOTH sentences must appear in the prompt —
the boundary itself and the automatic-fail rule for the critics.

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
<the ready-to-paste prompt and nothing else. Its layout is exactly this skeleton — three
paragraphs with a real blank line between them, no headings, nothing after the third:

[task paragraph]

[build-method paragraph — opens with a sentence equivalent to: "Fan out sub-agents and
break this into the smallest pieces that can be improved and judged separately — the
pieces are yours to choose." For a (web) target it opens instead with a sentence
equivalent to: "Work in rounds inside this conversation: build it in full, then turn
harsh critic with fresh eyes, then rebuild."]

[bar paragraph — opens with a sentence equivalent to: "Don't stop until every critic is
utterly wowed when the work is compared side by side, blind, against the bar." and ends
with the harness closer as its final sentence, nothing after it]

The two blank lines are part of the format: one right before the "Fan out sub-agents..."
sentence, one right before the "Don't stop until..." sentence — each of those sentences
starts its own paragraph. Copy the build-method opener's shape exactly: no list of
example pieces, no "such as", no em-dash enumeration of components — naming the pieces
is the lead agent's job at run time, never yours. If boundaries were given, the last
paragraph ends with the boundary sentence and the critic automatic-fail sentence.>
### NOTES
<1-4 short bullets, every one matched to the target harness. ALWAYS include one line of
run expectations, and pick it by harness family. For Claude Code, Codex, Gemini CLI, opencode, and
the local-model and API-model targets the line is equivalent to: "This loop runs for hours, consumes
tokens heavily (comfortable on a subscription plan, real money on API pricing), and will
rarely stop on its own — watch the progress page and stop the run when improvement per
round gets small." For a (web) target the line is instead equivalent to: "Rounds continue
only while you keep saying continue — stop when improvement per round gets small." — a
chat has no progress page, so a (web) target's NOTES never mention one. For a (web)
target, ALWAYS also include one bullet saying this prompt is the chat adaptation of a
method built for agentic harnesses — Claude Code or Codex pointed at the same goal will
go further. That bullet belongs to the four (web) targets alone: when the target already
IS an agentic harness (Claude Code, Codex, Gemini CLI, opencode, a local model), NOTES skip it.
Other bullets as useful: how to run it — paste into the target harness, and the
"/effort ultracode" tip only in a Claude Code prompt's NOTES (Codex, Gemini CLI, opencode, local,
and (web) targets have no ultracode, so their NOTES never suggest it) — and one
variation worth trying, like the article's optional smoothing pass: a fresh agent at the
end of each wave making the separately-improved pieces feel like one thing.>"""


# The intake meta-prompt behind /api/draft (the "Describe it" tab). Same KAT
# lesson as SYSTEM_PROMPT: a fixed OUTPUT FORMAT block plus a worked example,
# because this model follows examples where it skims abstract rules. Embedded
# verbatim from the spec — do not rephrase it.
DRAFT_PROMPT = """You are GauntletX's intake assistant. The user describes, in a sentence or two, something
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
- HARNESS: exactly one of: Claude Code, Codex, Gemini CLI, opencode, Qwen3 Coder Next (local),
  Qwen 3.8 (local), DeepSeek V4 Flash (local), Qwen 3.8 Max (API), Claude (web),
  ChatGPT (web), Google Gemini (web), Grok (web). "Claude Code" unless the user names another harness
  on that list — then copy that value exactly as written above. Nicknames map to the
  full list value, copied to the letter: "qwen 3 coder" or "qwen coder" → Qwen3 Coder
  Next (local); "qwen 3.8" → Qwen 3.8 (local); "qwen 3.8 max", "qwen max", or "qwen ... api" →
  Qwen 3.8 Max (API); "deepseek" → DeepSeek V4 Flash (local);
  "gemini cli" → Gemini CLI; bare "gemini" → Google Gemini (web); "opencode" or
  "open code" → opencode; "claude code" →
  Claude Code; bare "claude" or "claude.ai" → Claude (web); "chatgpt" or "gpt" →
  ChatGPT (web); "grok" → Grok (web). "I'll paste this into chatgpt" means the harness
  is ChatGPT (web). Never write a shortened form like "Qwen3 Coder (local)" or
  "ChatGPT" — only the exact list values exist.
- CHOSEN HARNESS: the message may open with the line "Target harness already chosen by
  user: X". When present, HARNESS is exactly X — e.g. "Target harness already chosen
  by user: Grok (web)" means Grok (web) — unless the description itself explicitly
  names a different target harness.

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
Claude Code"""


# The Work type select's exact options. /api/draft coerces into this list so
# a drafted value always lands on a real <option> in the form.
WORK_TYPES = ("Auto", "Game", "Website or app", "Writing", "Backend or code",
              "Design", "Marketing", "Research", "Other")

# The Target harness selects' exact options, Claude Code first (the default),
# in the same three groups the UI <optgroup>s show: agentic CLIs, local models
# run through an agentic CLI, and online chat apps the prompt is pasted into.
# Same coercion contract as WORK_TYPES: /api/draft lands on one of these or
# falls back to Claude Code, so the drafted value always matches an <option>.
HARNESSES = (
    # Agentic CLIs. opencode MUST stay after Codex: coerce_harness matches
    # _HARNESS_KEYS in roster order with a two-way prefix test, and a bare
    # "code" has to keep landing on Codex the way it always did.
    "Claude Code", "Codex", "Gemini CLI", "opencode",
    # Local & API models (an agentic CLI — e.g. Qwen Code in VSCode — drives them)
    "Qwen3 Coder Next (local)", "Qwen 3.8 (local)", "DeepSeek V4 Flash (local)",
    "Qwen 3.8 Max (API)",
    # Online chat
    "Claude (web)", "ChatGPT (web)", "Google Gemini (web)", "Grok (web)",
)


def _harness_key(value):
    """Matching key for fuzzy harness lookup: casefold, drop parenthetical
    qualifiers like "(local)", keep only letters/digits/dots — so the draft
    model's favourite near-misses ("Qwen3 Coder (local)", "qwen 3 coder")
    collide with "Qwen3 Coder Next (local)" instead of falling through."""
    value = re.sub(r"\([^)]*\)", " ", (value or "").casefold())
    return re.sub(r"[^a-z0-9.]+", "", value)


_HARNESS_KEYS = tuple((_harness_key(h), h) for h in HARNESSES)


def coerce_harness(value):
    """Land any harness spelling on a canonical HARNESSES entry, defaulting
    to Claude Code. Exact match wins; then the family aliases ("gemini cli" →
    "Gemini CLI" but bare "gemini" → "Google Gemini (web)"; "claude code" →
    "Claude Code" but bare "claude"/"claude.ai" → "Claude (web)"; "chatgpt"/
    "gpt" → "ChatGPT (web)"; "grok" → "Grok (web)"); then a normalized prefix
    match ("qwen 3 coder" → "Qwen3 Coder Next (local)").
    The v0.2.1 e2e round found the old exact-only check coercing a user who
    said "qwen 3 coder" to the WRONG harness (Claude Code) because the draft
    model drops "Next" — and found /api/generate applying no check at all,
    letting harness="FooCLI" flow verbatim into the meta-prompt. Applied on
    every door (draft, generate, CLI) so neither can happen again."""
    value = (value or "").strip()
    if value in HARNESSES:
        return value
    key = _harness_key(value)
    # Family aliases BEFORE the generic prefix loops. The loops would land a
    # bare "claude" on "Claude Code" and a bare "gemini" on "Gemini CLI" by
    # roster order — but someone who says just "claude" or "gemini" means the
    # chat app, and the (web) targets are new in 0.2.2, so the bare names must
    # resolve here first. "cli"/"code" in the value still means the CLI target.
    if "claude" in key:
        return "Claude Code" if "code" in key else "Claude (web)"
    if "gemini" in key:
        return "Gemini CLI" if "cli" in key else "Google Gemini (web)"
    if "gpt" in key:  # "chatgpt", "chat gpt", bare "gpt" — all the chat app
        return "ChatGPT (web)"
    if "grok" in key:
        return "Grok (web)"
    # "max" or "api" next to qwen means the Token-Plan flagship via Qwen Code,
    # not the Spark-local 3.8 — the generic prefix loops cannot split these
    # (each key is a prefix of the other), so it must be decided here.
    if "qwen" in key and ("max" in key or "api" in key):
        return "Qwen 3.8 Max (API)"
    if len(key) >= 4:  # "qwen" can fuzzy-match; a stray letter or two cannot
        for ck, canonical in _HARNESS_KEYS:
            if key == ck or ck.startswith(key) or key.startswith(ck):
                return canonical
        # Last resort, digits and dots dropped too, so "qwen coder" still
        # finds "Qwen3 Coder Next (local)". Only reached when no digitful
        # match exists, so "qwen 3.8" can never land here.
        bare = re.sub(r"[0-9.]+", "", key)
        if len(bare) >= 4:
            for ck, canonical in _HARNESS_KEYS:
                cb = re.sub(r"[0-9.]+", "", ck)
                if bare == cb or cb.startswith(bare) or bare.startswith(cb):
                    return canonical
    return "Claude Code"


# ---------------------------------------------------------------- vLLM client

def models_url():
    """The sibling /v1/models endpoint, derived from the chat URL so one env
    var configures both."""
    if "/chat/completions" in VLLM_URL:
        return VLLM_URL.rsplit("/chat/completions", 1)[0] + "/models"
    return VLLM_URL.rstrip("/") + "/models"


def _headers():
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["Authorization"] = "Bearer " + API_KEY
    return h


# The only mutable global: which model the vLLM box is currently serving.
# Guarded by a lock because the ThreadingTCPServer handles requests in
# parallel and discovery must happen exactly once, not once per request.
_model_lock = threading.Lock()
_model_cache = {"id": None}


def resolve_model(force=False):
    """Return (model_id, error). GAUNTLETX_MODEL wins; otherwise ask
    /v1/models what is loaded and cache the answer."""
    if MODEL_ENV:
        return MODEL_ENV, None
    with _model_lock:
        if _model_cache["id"] and not force:
            return _model_cache["id"], None
        url = models_url()
        try:
            req = urllib.request.Request(url, headers=_headers())
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            mid = data["data"][0]["id"]
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError) as e:
            return None, ("could not discover a model from {} — set GAUNTLETX_MODEL "
                          "or start vLLM ({})".format(url, e))
        _model_cache["id"] = mid
        return mid, None


def build_user_message(goal, mode, work_type, references, constraints, boundaries, harness):
    """The user message, assembled exactly as the spec lays it out. Empty
    optional fields become explicit 'none' lines so the model never wonders
    whether something was withheld or just forgotten. An unknown mode falls
    back to fresh — the safe reading of a request that never mentioned an
    existing build."""
    polish = (mode or "").strip().lower() == "polish"
    refs = (references or "").strip()
    msg = ("Goal:\n"
           "{goal}\n"
           "\n"
           "Mode: {mode}\n"
           "Work type: {wt}\n"
           "Target harness: {h}\n"
           "References / quality bars I already have:\n"
           "{refs}\n"
           "Hard constraints / must-haves:\n"
           "{cons}\n"
           "Hard boundaries (never cross):\n"
           "{bounds}").format(
        goal=goal.strip(),
        mode="polish an existing build" if polish else "start fresh",
        wt=(work_type or "").strip() or "auto-detect",
        h=(harness or "").strip() or "Claude Code",
        refs=refs or "none — choose or task the agent with finding one",
        cons=(constraints or "").strip() or "none",
        bounds=(boundaries or "").strip() or "none")
    # POLISH MODE's "bar must include the user's own references" line in the
    # system prompt was being skimmed past (v0.1.1 e2e finding: runs cited only
    # external platforms, or nothing). Restating it here as a per-request hard
    # requirement puts it where this model reliably complies: the user turn.
    if polish and refs:
        msg += ("\n\nHard requirement for this polish pass: the BAR must name my "
                "references above explicitly ({}), not only external "
                "best-in-class.".format(refs))
    return msg


def validate_inputs(goal, references, constraints, boundaries):
    """One error string, or None. Checked in both the CLI and the API so the
    caps hold no matter which door the request came through."""
    if not (goal or "").strip():
        return "goal is required"
    if len(goal) > GOAL_MAX:
        return "goal is too long ({} chars; max {})".format(len(goal), GOAL_MAX)
    if len(references or "") > REFS_MAX:
        return "references too long ({} chars; max {})".format(len(references), REFS_MAX)
    if len(constraints or "") > CONS_MAX:
        return "constraints too long ({} chars; max {})".format(len(constraints), CONS_MAX)
    if len(boundaries or "") > BOUND_MAX:
        return "boundaries too long ({} chars; max {})".format(len(boundaries), BOUND_MAX)
    return None


def open_vllm(user_msg, stream, system_prompt=SYSTEM_PROMPT):
    """Open the chat/completions call. Returns (response, None) — the caller
    owns closing it — or (None, error string). The error always names the URL
    it tried, because 'connection refused' without an address is a treasure
    hunt at 2am. system_prompt defaults to the generator; /api/draft passes
    DRAFT_PROMPT through the same plumbing."""
    model, err = resolve_model()
    if err:
        return None, err
    payload = {"model": model,
               "messages": [{"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg}],
               "temperature": TEMPERATURE,
               "max_tokens": MAX_TOKENS,
               "stream": bool(stream)}
    retried = False
    while True:
        req = urllib.request.Request(VLLM_URL, json.dumps(payload).encode(), _headers())
        try:
            return urllib.request.urlopen(req, timeout=TIMEOUT), None
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except OSError:
                pass
            # vLLM serves one model at a time; a 404 usually means the box
            # swapped models since we cached the id. Re-discover once, then
            # give up honestly rather than looping.
            if e.code == 404 and not MODEL_ENV and not retried:
                retried = True
                model, rerr = resolve_model(force=True)
                if model:
                    payload["model"] = model
                    continue
            return None, "vLLM at {} returned HTTP {}: {}".format(
                VLLM_URL, e.code, detail or "no detail")
        except (urllib.error.URLError, OSError) as e:
            return None, "cannot reach vLLM at {}: {}".format(VLLM_URL, e)


def sse_events(resp):
    """Yield ("reasoning"|"content", text) from a streaming vLLM response,
    read line by line off the socket so tokens surface as they arrive, then a
    final ("done", "") — but ONLY if the upstream actually sent `data: [DONE]`.
    An iterator that ends without the done event means the connection closed
    mid-generation (http.client treats a FIN at a chunk boundary as a silent
    end of stream, not an error), and the caller must report truncation,
    never success.

    The server runs with --reasoning-parser qwen3, so a delta may carry
    reasoning_content (thinking) or content (the answer) — occasionally the
    boundary chunk carries both. They are yielded as separate events and
    never concatenated: mixing them would leak thinking into the prompt.
    """
    for raw_line in resp:
        line = raw_line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            yield "done", ""
            return
        try:
            obj = json.loads(data)
        except ValueError:
            continue  # keep-alive noise or a torn line; never fatal
        # Valid JSON of the wrong shape (a bare "ping" keep-alive, a null in
        # choices) must be skipped the same way, not crash the stream.
        if not isinstance(obj, dict):
            continue
        first = (obj.get("choices") or [{}])[0]
        delta = first.get("delta") if isinstance(first, dict) else None
        if not isinstance(delta, dict):
            continue
        r = delta.get("reasoning_content")
        if r:
            yield "reasoning", r
        c = delta.get("content")
        if c:
            yield "content", c


# ------------------------------------------------------------ section parsing

# Tolerant on purpose: "###BAR", "### Bar", trailing chatter after the word —
# a slightly sloppy model reply should degrade to "raw text shown", never to
# a 500. The four names are anchored so prose containing "###" elsewhere
# cannot fake a section.
SECTION_RE = re.compile(r"^###[ \t]*(BAR|WHY|PROMPT|NOTES)\b[^\n]*$",
                        re.IGNORECASE | re.MULTILINE)

# The /api/draft reply's headings. \b keeps "### MODEL" from faking "MODE",
# same anchoring discipline as SECTION_RE.
DRAFT_SECTION_RE = re.compile(
    r"^###[ \t]*(GOAL|MODE|WORK_TYPE|REFERENCES|CONSTRAINTS|BOUNDARIES|HARNESS)\b[^\n]*$",
    re.IGNORECASE | re.MULTILINE)


def parse_sections(raw, pattern=SECTION_RE):
    """Best-effort split into {section: body}. Missing or empty sections are
    simply absent; malformed input returns {} and the caller falls back to
    the raw text. Never raises. The default pattern is the generator's
    BAR/WHY/PROMPT/NOTES; /api/draft passes DRAFT_SECTION_RE."""
    out = {}
    try:
        raw = raw or ""
        heads = list(pattern.finditer(raw))
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(raw)
            key = h.group(1).lower()
            body = raw[h.end():end].strip()
            if body and key not in out:  # first occurrence wins
                out[key] = body
    except Exception:  # noqa: BLE001 — parsing must never take the server down
        return {}
    return out


# ---------------------------------------------------- post-generation guards
#
# The 0.2.2 live e2e found two nondeterministic (temp 0.7) model failures on
# the four (web) targets that no amount of prompt engineering fully closes:
#   (a) ~2 in 5 runs paraphrase the mandated verbatim (web) closer (dropping
#       the "switch to the voice of a separate" / "blind-compare ... biggest
#       gap" clauses);
#   (b) ~1 in 5 runs leak agentic-harness features (sub-agents, ultracode,
#       /loop, a progress page) into a chat prompt.
# The closer is a fixed string, so the server repairs it deterministically
# instead of trusting the model; the leak cannot be repaired mechanically, so
# blocking calls regenerate once and otherwise it is flagged to the caller.

WEB_CLOSER = ("Work in rounds inside this conversation: build the full artifact, "
              "then switch to the voice of a separate, harsh critic with fresh "
              "eyes — blind-compare it against the bar, name the single biggest "
              "gap — then rebuild. Repeat every time I say continue.")

WEB_LEAK_RE = re.compile(r"\bsub-?agents?\b|\bultracode\b|/loop\b|progress page",
                         re.IGNORECASE)


def is_web_harness(harness):
    """The four online-chat targets share the '(web)' suffix in HARNESSES."""
    return (harness or "").strip().endswith("(web)")


def _prompt_span(raw):
    """(start, end) of the first ### PROMPT section's body in raw, or None."""
    heads = list(SECTION_RE.finditer(raw or ""))
    for i, h in enumerate(heads):
        if h.group(1).lower() == "prompt":
            end = heads[i + 1].start() if i + 1 < len(heads) else len(raw)
            return h.end(), end
    return None


def _repair_web_closer(prompt):
    """(prompt, changed). Ensure a (web) prompt ends with WEB_CLOSER verbatim.
    The suffix check is whitespace-tolerant (the model may re-wrap lines).
    Repair replaces from the last 'Work in rounds' inside the FINAL paragraph
    — the build-method paragraph legitimately opens with those words too, so
    an earlier occurrence must never be touched — else appends the closer."""
    tail = prompt.rstrip()
    if re.sub(r"\s+", " ", tail).endswith(WEB_CLOSER):
        return prompt, False
    cut = tail.rfind("\n\n")
    para_start = cut + 2 if cut >= 0 else 0
    m = tail.rfind("Work in rounds")
    if m >= para_start:
        fixed = tail[:m] + WEB_CLOSER  # keep the separator that preceded it
    else:
        fixed = tail + " " + WEB_CLOSER  # closer missing entirely — append
    return fixed, True


def harden_output(raw, harness):
    """Deterministic (web)-target guards on a finished generation.
    Returns (raw, closer_repaired, lint_warning_or_None). Non-web harnesses
    and unparseable replies pass through untouched — raw fallback behavior
    is preserved exactly."""
    if not is_web_harness(harness):
        return raw, False, None
    span = _prompt_span(raw)
    if not span:
        return raw, False, None
    s, e = span
    body = raw[s:e]
    core = body.strip()
    if not core:
        return raw, False, None
    fixed_core, changed = _repair_web_closer(core)
    if changed:
        lead = body[:len(body) - len(body.lstrip())]
        trail = body[len(body.rstrip()):]
        raw = raw[:s] + lead + fixed_core + trail + raw[e:]
    warning = None
    # The repaired closer itself never matches WEB_LEAK_RE; a hit means the
    # body genuinely mentions harness features a chat does not have.
    if WEB_LEAK_RE.search(fixed_core):
        warning = ("web-target lint: this prompt mentions sub-agents, ultracode, "
                   "/loop, or a progress page — a chat target has none of these; "
                   "regenerate for a clean prompt")
    return raw, changed, warning


# ------------------------------------------------- structured status page
#
# v0.2.3. SYSTEM_PROMPT already tells non-web harnesses to keep a simple live
# progress page without overspecifying it; this opt-in contract pins down
# exactly what that page must be. Same philosophy as harden_output: fixed
# text NEVER goes through the model — the contract is appended
# deterministically in code after generation, so every prompt that opts in
# carries the identical paragraph byte for byte, and the model's behavior
# (both system prompts, the user message) is untouched by the toggle.

STATUS_CONTRACT = (
    "For the live progress page specifically: make it a single progress.html "
    "in the project root that auto-refreshes itself "
    '(<meta http-equiv="refresh" content="10">). Model it on this structure: '
    "a header with the project name, current phase, and last-updated time; "
    "stat cards showing pieces passed and the current score against the bar; "
    "a piece table with state (BUILDING / IN REVIEW / PASSED / BLOCKED), "
    "rounds run, score, and the biggest remaining gap per piece; and an "
    "append-only activity log. Every log entry gets a real timestamp written "
    "at the moment the event happens — never backfilled, never invented. "
    "Record failures and blockers the moment they occur; a page with only "
    "good news is wrong. Update the page every working turn.")


def apply_status_contract(prompt, harness, flag):
    """Deterministically append STATUS_CONTRACT to a finished prompt.
    Returns the prompt unchanged unless the flag is on, the harness is a
    non-(web) target (a chat window cannot write files, so the toggle is
    ignored there — never an error), and there is a prompt to append to."""
    if not flag or is_web_harness(harness) or not (prompt or "").strip():
        return prompt
    return prompt.rstrip() + "\n\n" + STATUS_CONTRACT


def _status_contract_raw(raw, harness, flag):
    """The same append reflected inside raw's ### PROMPT section, so `raw`
    and the parsed `prompt` field never disagree about what was generated.
    Span surgery identical to harden_output's; unparseable raw (no ### PROMPT
    section) passes through untouched — raw-fallback behavior preserved."""
    if not flag or is_web_harness(harness):
        return raw
    span = _prompt_span(raw)
    if not span:
        return raw
    s, e = span
    body = raw[s:e]
    core = body.strip()
    if not core:
        return raw
    lead = body[:len(body) - len(body.lstrip())]
    trail = body[len(body.rstrip()):]
    return raw[:s] + lead + apply_status_contract(core, harness, flag) + trail + raw[e:]


def call_blocking(user_msg, system_prompt):
    """One non-streamed round trip, shared by generate and draft. Returns
    (raw content, reasoning, None) or (None, None, error string)."""
    resp, err = open_vllm(user_msg, stream=False, system_prompt=system_prompt)
    if err:
        return None, None, err
    try:
        with resp:
            data = json.loads(resp.read())
    # IncompleteRead (vLLM dying mid-reply) is an HTTPException, not an
    # OSError — miss it and the caller sees a traceback instead of a 502.
    except (OSError, ValueError, http.client.HTTPException) as e:
        return None, None, "error reading reply from {}: {}".format(VLLM_URL, e)
    try:
        msg = data["choices"][0]["message"]
        if not isinstance(msg, dict):  # e.g. "message": null
            raise TypeError("message is not an object")
    except (KeyError, IndexError, TypeError):
        return None, None, "unexpected reply shape from {}: {}".format(
            VLLM_URL, str(data)[:200])
    return (msg.get("content") or "").strip(), msg.get("reasoning_content") or "", None


def generate_blocking(goal, mode, work_type, references, constraints, boundaries, harness,
                      status_page=False):
    """One non-streamed round trip. Returns (result dict, None) or (None, err).
    The dict always carries `raw`; the parsed fields are None when the model
    ignored the output format — the caller still gets everything it said.
    (web) targets get the deterministic guards: the closer repaired in place,
    and on an agentic-feature leak ONE regeneration — if the rerun leaks too,
    the first result ships with a `lint` warning rather than looping.
    status_page appends STATUS_CONTRACT deterministically after generation
    (reflected into raw BEFORE parsing, so `prompt` and `raw` agree); it is
    ignored for (web) harnesses — a chat target can't write files."""
    user_msg = build_user_message(goal, mode, work_type, references,
                                  constraints, boundaries, harness)
    raw, reasoning, err = call_blocking(user_msg, SYSTEM_PROMPT)
    if err:
        return None, err
    raw, _fixed, lint = harden_output(raw, harness)
    if lint:
        raw2, reasoning2, err2 = call_blocking(user_msg, SYSTEM_PROMPT)
        if not err2:
            raw2, _fixed2, lint2 = harden_output(raw2, harness)
            if not lint2:
                raw, reasoning, lint = raw2, reasoning2, None
    raw = _status_contract_raw(raw, harness, status_page)
    s = parse_sections(raw)
    out = {"bar": s.get("bar"), "why": s.get("why"), "prompt": s.get("prompt"),
           "notes": s.get("notes"), "raw": raw,
           "reasoning_chars": len(reasoning)}
    if lint:
        out["lint"] = lint
    return out, None


def draft_blocking(description):
    """One /api/draft round trip: a one-shot description in, coerced form
    fields out. Returns (dict, None) or (None, err). Blocking only — the
    output is small. A reply that ignores the format is NOT an error: the
    dict carries `raw` with every field null and the UI falls back to showing
    the raw text, mirroring generate's raw fallback."""
    raw, _reasoning, err = call_blocking(description.strip(), DRAFT_PROMPT)
    if err:
        return None, err
    s = parse_sections(raw, DRAFT_SECTION_RE)
    goal = (s.get("goal") or "").strip()
    if not goal:
        # No usable GOAL means the model ignored the format; coercing the
        # rest would be guesswork — EXCEPT the harness, which the model often
        # still answers correctly (0.2.2 e2e: a goal-less "I'll paste this
        # into chatgpt" yielded '### HARNESS ChatGPT (web)' in raw while the
        # whole reply was nulled). Surface it, coerced, so the UI can land it
        # on the selects; everything else stays null for raw-text salvage.
        h = (s.get("harness") or "").strip()
        return {"goal": None, "mode": None, "work_type": None,
                "references": None, "constraints": None, "boundaries": None,
                "harness": coerce_harness(h) if h else None, "raw": raw}, None
    # Coercion: whatever the model wrote, the draft must land on values the
    # form (and a follow-up /api/generate) will accept — whitelists for the
    # selects, trims plus the generate caps for the free-text fields.
    mode = (s.get("mode") or "").strip().lower()
    if mode not in ("fresh", "polish"):
        mode = "fresh"
    work_type = (s.get("work_type") or "").strip()
    if work_type not in WORK_TYPES:
        work_type = "Auto"
    harness = coerce_harness(s.get("harness"))
    refs = (s.get("references") or "").strip()
    # The model sometimes emits the bare "[suggested — edit or replace]" tag with
    # no actual suggestion in front of it. That is an empty suggestion, not a
    # reference — pass it through and /api/generate would treat the tag itself
    # as the user's quality bar.
    if refs.replace("[suggested — edit or replace]", "").strip() == "":
        refs = ""
    return {"goal": goal[:GOAL_MAX], "mode": mode, "work_type": work_type,
            "references": refs[:REFS_MAX],
            "constraints": (s.get("constraints") or "").strip()[:CONS_MAX],
            "boundaries": (s.get("boundaries") or "").strip()[:BOUND_MAX],
            "harness": harness, "raw": raw}, None


def version_info():
    """The /api/version payload. The reachability probe is deliberately short
    (3s): this endpoint feeds the UI footer and the healthcheck, and neither
    should hang for minutes because the Spark is off."""
    info = {"version": VERSION, "model": MODEL_ENV or _model_cache["id"],
            "vllm_url": VLLM_URL, "vllm_reachable": False}
    try:
        req = urllib.request.Request(models_url(), headers=_headers())
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
        info["vllm_reachable"] = True
        if not info["model"]:
            ids = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict)]
            if ids and ids[0]:
                with _model_lock:
                    _model_cache["id"] = ids[0]  # free discovery — keep it
                info["model"] = ids[0]
    except Exception:  # noqa: BLE001 — never crash the version endpoint
        pass
    return info


# ------------------------------------------------------------------- web UI

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gauntletx — Gauntlet Loop prompts</title><style>
:root{--bg:#0f1420;--panel:#171d2b;--ink:#e8edf5;--muted:#94a0b4;--line:#26303f;
      --accent:#6ea8fe;--chip:#1e2636;--sh:0 2px 14px rgba(0,0,0,.35)}
:root[data-theme=light]{--bg:#eef1f6;--panel:#fff;--ink:#1a2230;--muted:#5a6474;
  --line:#e2e7ef;--accent:#2563eb;--chip:#eef2f8;--sh:0 2px 12px rgba(20,30,60,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:34px 20px 70px}
header{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.logo{font-size:34px}h1{margin:0;font-size:26px;letter-spacing:-.02em}
.sub{color:var(--muted);margin:2px 0 0;font-size:14px}
.themebtn{margin-left:auto;background:var(--panel);border:1px solid var(--line);
  border-radius:10px;padding:8px 12px;cursor:pointer;color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:18px;box-shadow:var(--sh);margin-top:22px}
.tabbar{display:flex;gap:2px;border-bottom:1px solid var(--line);margin-bottom:16px}
.tabbtn{background:transparent;color:var(--muted);border:0;border-bottom:2px solid transparent;
  border-radius:0;padding:8px 14px;font-weight:600;font-size:14px;cursor:pointer}
.tabbtn:hover{color:var(--ink)}
.tabbtn.active{color:var(--accent);border-bottom-color:var(--accent)}
/* draft-filled fields flash via --accent, so it reads in both themes */
.flash{animation:gxflash 1.4s ease-out}
@keyframes gxflash{0%{box-shadow:0 0 0 3px var(--accent)}100%{box-shadow:0 0 0 0 transparent}}
.lbl{display:block;font-size:13px;font-weight:650;margin:14px 0 6px}
.lbl:first-child{margin-top:0}
.opt{color:var(--muted);font-weight:400;font-size:12px}
textarea{width:100%;min-height:88px;resize:vertical;border:1px solid var(--line);
  border-radius:10px;padding:12px;font:inherit;background:var(--bg);color:var(--ink)}
textarea.short{min-height:56px}
textarea:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px}
.row{display:flex;gap:12px;margin-top:12px;flex-wrap:wrap;align-items:center}
.field{flex:1;min-width:180px}
.modehint{flex:2;min-width:230px;align-self:center}
.field label{display:block;font-size:12.5px;color:var(--muted);margin-bottom:4px}
select{width:100%;border:1px solid var(--line);border-radius:10px;padding:10px 12px;
  font:inherit;background:var(--bg);color:var(--ink)}
button{border:0;border-radius:10px;padding:10px 18px;font:inherit;font-weight:650;
  cursor:pointer;background:var(--accent);color:#fff;font-size:14px}
button:disabled{opacity:.5;cursor:default}
button.ghost{background:transparent;color:var(--muted);border:1px solid var(--line);font-weight:500}
button.small{padding:5px 10px;font-size:12px}
.hint{color:var(--muted);font-size:12.5px}
/* the status-page toggle, one per tab, two-way synced like the harness
   selects. Disabled (a (web) harness is selected) it dims with the hint
   swapped to say why. */
.chk{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:650;cursor:pointer}
.chk input{accent-color:var(--accent)}
.chk:has(input:disabled){opacity:.5;cursor:default}
/* per-target harness notices: amber-bordered warning for chat targets, muted
   hint for local targets. Border color is fixed amber — readable both themes. */
.hnote{margin:8px 0 0;font-size:12.5px;line-height:1.55;color:var(--muted);
  padding:8px 11px;border:1px solid var(--line);border-left:3px solid var(--line);
  border-radius:6px}
.hnote.warn{color:var(--ink);border-left-color:#d97706}
.anatomy{margin-top:12px}
.think{margin-top:18px;color:var(--muted)}
.think summary{cursor:pointer;font-size:13px;padding:6px 4px}
.think pre{background:var(--chip);border:1px solid var(--line);border-radius:10px;
  padding:12px;margin:6px 0 0;max-height:260px;overflow-y:auto;
  font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted)}
pre{white-space:pre-wrap;word-wrap:break-word;margin:0}
.livehead{color:var(--muted);font-size:12.5px;margin-bottom:8px}
#liveraw{font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:340px;overflow-y:auto}
.cardlbl{font-size:11.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
  font-weight:700;margin-bottom:8px}
.cardhead{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px}
.cardhead .cardlbl{margin-bottom:0}
.why{color:var(--muted);font-size:13px;margin-top:10px;border-top:1px solid var(--line);padding-top:10px}
.promptcard{border-color:var(--accent)}
#prompttext{font:13.5px/1.62 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--chip);
  border:1px solid var(--line);border-radius:10px;padding:14px}
.notes,#rawtext,#draftrawtext{font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}
.errcard{border-color:#e0684f}
#errtext{color:#e0684f;font-size:14px;overflow-wrap:break-word}
/* stale banner: visible in both themes via the accent var, like .promptcard */
.stalebanner{display:flex;align-items:center;justify-content:space-between;gap:12px;
  flex-wrap:wrap;background:var(--chip);border:1px solid var(--accent);
  border-radius:10px;padding:10px 14px;margin-top:14px;font-size:13.5px}
button.resub{background:var(--accent);color:#fff;white-space:nowrap}
.actions{margin-top:14px}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--line);
  border-top-color:var(--accent);border-radius:50%;animation:s .7s linear infinite;vertical-align:-2px}
@keyframes s{to{transform:rotate(360deg)}}
.hist{margin-top:34px}
.histhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.hist h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
  margin:0;font-weight:700}
.hitem{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:11px 13px;margin-bottom:8px;cursor:pointer}
.hitem:hover{border-color:var(--accent)}
.hq{font-size:13.5px}.hm{color:var(--muted);font-size:12px;margin-top:2px}
footer{color:var(--muted);font-size:12.5px;margin-top:34px;border-top:1px solid var(--line);
  padding-top:14px;line-height:1.8}
footer a{color:var(--accent);text-decoration:none}
</style></head><body><div class="wrap">
<header><span class="logo">🧤</span><div><h1>gauntletx</h1>
<p class="sub">Turns a goal into a ready-to-paste Gauntlet Loop prompt · the method behind Claude of Duty</p></div>
<button class="themebtn" id="tb">◑ Theme</button></header>

<div class="card">
  <div class="tabbar">
    <button class="tabbtn active" id="tabdesc">✨ Describe it</button>
    <button class="tabbtn" id="tabform">Form</button>
  </div>

  <div id="descpane">
    <label class="lbl" for="desc">What do you want built or improved?</label>
    <!-- 3935 = DESC_MAX (4000) minus the worst-case "Target harness already
         chosen by user: DeepSeek V4 Flash (local)\n" prefix (65 chars), so a
         max-length description plus the prefix can never 400 on /api/draft -->
    <textarea id="desc" autofocus maxlength="3935" placeholder="i want to analyze this platform located here XXXXX and i want you to improve it. I need it to run faster"></textarea>
    <div class="row">
      <div class="field"><label for="dharness">Target harness</label><select id="dharness">
        <optgroup label="Agentic CLIs"><option>Claude Code</option><option>Codex</option>
          <option>Gemini CLI</option><option>opencode</option></optgroup>
        <optgroup label="Local &amp; API models"><option>Qwen3 Coder Next (local)</option>
          <option>Qwen 3.8 (local)</option><option>DeepSeek V4 Flash (local)</option>
          <option>Qwen 3.8 Max (API)</option></optgroup>
        <optgroup label="Online chat"><option>Claude (web)</option><option>ChatGPT (web)</option>
          <option>Google Gemini (web)</option><option>Grok (web)</option></optgroup>
        </select></div>
      <div class="modehint"><span class="hint">One choice, both tabs — the drafter keeps it unless your description names a different harness.</span></div>
    </div>
    <div class="row">
      <label class="chk"><input type="checkbox" id="dstatuspage"> Structured status page (progress.html)</label>
      <span class="hint" id="dstatushint">Appends a fixed page contract to the prompt — auto-refreshing, real timestamps, no simulation.</span>
    </div>
    <p class="hnote" id="hnote_d" hidden></p>
    <div class="row">
      <button id="draftgo">Draft the form &#8594;</button>
      <span class="hint" id="drafthint" hidden><span class="spin"></span> drafting&#8230;</span>
      <span class="hint">&#8984;&#8629; / Ctrl&#8629; to draft</span>
    </div>
    <div class="hint anatomy">A sentence or two is enough — the local model expands it into the full form for you to review and edit.<br>
    Nothing generates until you press Generate on the Form tab.</div>
    <div class="card" id="draftraw" hidden>
      <div class="cardhead"><span class="cardlbl">Raw draft output (could not parse fields)</span>
        <button id="copydraftraw">Copy</button></div>
      <pre id="draftrawtext"></pre></div>
  </div>

  <div id="formpane" hidden>
  <label class="lbl" for="goal">Goal</label>
  <textarea id="goal" placeholder="What do you want built? e.g. A kart-racing game that runs in the browser and feels as fun and polished as Mario Kart"></textarea>
  <div class="row">
    <div class="field"><label for="mode">Mode</label><select id="mode">
      <option value="fresh">Start fresh</option>
      <option value="polish">Polish an existing build</option></select></div>
    <div class="modehint"><span class="hint">Best results: build a solid MVP first, then run a gauntlet loop to polish it. Cold-start loops optimize toward whatever the agent guesses.</span></div>
  </div>
  <div class="row">
    <div class="field"><label for="wtype">Work type</label><select id="wtype">
      <option value="">Auto</option><option>Game</option><option>Website or app</option>
      <option>Writing</option><option>Backend or code</option><option>Design</option>
      <option>Marketing</option><option>Research</option><option>Other</option></select></div>
    <div class="field"><label for="harness">Target harness</label><select id="harness">
      <optgroup label="Agentic CLIs"><option>Claude Code</option><option>Codex</option>
        <option>Gemini CLI</option><option>opencode</option></optgroup>
      <optgroup label="Local &amp; API models"><option>Qwen3 Coder Next (local)</option>
        <option>Qwen 3.8 (local)</option><option>DeepSeek V4 Flash (local)</option>
        <option>Qwen 3.8 Max (API)</option></optgroup>
      <optgroup label="Online chat"><option>Claude (web)</option><option>ChatGPT (web)</option>
        <option>Google Gemini (web)</option><option>Grok (web)</option></optgroup>
      </select></div>
  </div>
  <div class="row">
    <label class="chk"><input type="checkbox" id="statuspage"> Structured status page (progress.html)</label>
    <span class="hint" id="statushint">Appends a fixed page contract to the prompt — auto-refreshing, real timestamps, no simulation.</span>
  </div>
  <p class="hnote" id="hnote_f" hidden></p>
  <label class="lbl" for="refs">References or quality bar you already have <span class="opt">optional</span></label>
  <textarea id="refs" class="short" placeholder="What should the critic compare against? e.g. real Call of Duty screenshots; 3 sites you admire; a test suite; your own reference photos or brand system. Leave blank and it will pick one."></textarea>
  <label class="lbl" for="cons">Hard constraints / must-haves <span class="opt">optional</span></label>
  <textarea id="cons" class="short" placeholder="e.g. Three.js only; must run in a phone browser; no external assets"></textarea>
  <label class="lbl" for="bounds">Hard boundaries (never cross) <span class="opt">optional</span></label>
  <textarea id="bounds" class="short" placeholder="e.g. local only — no deploys, no domains, nothing live; don't touch prod; no paid APIs"></textarea>
  <div class="row">
    <button id="go">Generate</button>
    <button id="stop" class="ghost" hidden>Stop</button>
    <span class="hint">⌘↵ / Ctrl↵ to submit</span>
  </div>
  <div class="hint anatomy">A Gauntlet Loop prompt = <b>The Task</b> (what) → <b>The Build Method</b> (how) → <b>The Bar</b> (when to stop).<br>
  The prompt doesn't describe the product — it describes who's allowed to call it finished.</div>
  </div>
</div>

<details class="think" id="thinkbox" hidden>
  <summary><span class="spin" id="tspin"></span> model thinking</summary>
  <pre id="think"></pre>
</details>

<div class="card" id="livebox" hidden>
  <div class="livehead">writing…</div><pre id="liveraw"></pre>
</div>

<div class="card errcard" id="errcard" hidden>
  <div class="cardlbl">Error</div><div id="errtext"></div>
</div>

<div id="result" hidden>
  <div class="stalebanner" id="stale" hidden>
    <span>Form changed since this prompt was generated — resubmit to update it</span>
    <button id="resub" class="resub">Resubmit &#8635;</button></div>
  <div class="card" id="barcard" hidden><div class="cardlbl">The Bar</div>
    <div id="bartext"></div><div class="why" id="whytext"></div></div>
  <div class="card promptcard" id="promptcard" hidden>
    <div class="cardhead"><span class="cardlbl">The prompt</span>
      <button id="copyprompt">Copy prompt</button></div>
    <pre id="prompttext"></pre></div>
  <div class="card" id="notescard" hidden><div class="cardlbl">Notes</div>
    <pre id="notestext" class="notes"></pre></div>
  <div class="card" id="rawcard" hidden>
    <div class="cardhead"><span class="cardlbl">Raw output (could not parse sections)</span>
      <button id="copyrawbtn">Copy</button></div>
    <pre id="rawtext"></pre></div>
  <div class="row actions">
    <button id="copyall" class="ghost">Copy all</button>
    <button id="again" class="ghost">Regenerate</button></div>
</div>

<div class="hist" id="hist" hidden>
  <div class="histhead"><h2>Earlier</h2>
    <button class="ghost small" id="clearhist">Clear history</button></div>
  <div id="hlist"></div>
</div>

<footer><b>gauntletx v__VERSION__</b> by Nathan Maine · <span id="fmodel">…</span><br>
Method: <a href="https://somethingbig.ai/gauntlet-loop" rel="noopener">Matt Shumer's Gauntlet Loop ↗</a></footer>

<script>
const $=i=>document.getElementById(i);
/* theme: dark is the default; the toggle persists */
$('tb').onclick=()=>{const c=document.documentElement.getAttribute('data-theme');
  const n=c==='light'?'dark':'light';document.documentElement.setAttribute('data-theme',n);
  localStorage.setItem('gx_theme',n)};
const th=localStorage.getItem('gx_theme');if(th)document.documentElement.setAttribute('data-theme',th);

fetch('/api/version').then(r=>r.json()).then(j=>{
  $('fmodel').textContent=(j.model||'model: auto-discover')+' · '+j.vllm_url+
    (j.vllm_reachable?'':' · ⚠ vLLM unreachable');
}).catch(()=>{$('fmodel').textContent='version lookup failed'});

/* Same tolerant parser as the server: split on ### BAR/WHY/PROMPT/NOTES
   headings; a reply that ignores the format falls back to a raw card. */
function parseSections(raw){
  const re=/^###[ \t]*(BAR|WHY|PROMPT|NOTES)\b[^\n]*$/gim;
  const heads=[];let m;
  while((m=re.exec(raw))!==null)heads.push({k:m[1].toUpperCase(),s:m.index,e:m.index+m[0].length});
  if(!heads.length)return null;
  const out={};
  heads.forEach((h,i)=>{
    const body=raw.slice(h.e,i+1<heads.length?heads[i+1].s:raw.length).trim();
    const k=h.k.toLowerCase();
    if(body&&!(k in out))out[k]=body});
  return out;
}

/* v0.2.3: the status-page contract, templated in by the server like
   __VERSION__ (as a JSON string literal). On the streaming path the append
   happens HERE, on the finished buffer, so the SSE frame order is untouched
   — and fixed text never goes through the model. Inserted inside the
   ### PROMPT section (same span surgery as the server's blocking door) so
   the prompt card, history, and every copy action all agree. */
const STATUS_CONTRACT=__STATUS_CONTRACT__;
function applyStatusContract(raw){
  const re=/^###[ \t]*(BAR|WHY|PROMPT|NOTES)\b[^\n]*$/gim;
  const heads=[];let m;
  while((m=re.exec(raw))!==null)heads.push({k:m[1].toUpperCase(),e:m.index+m[0].length,s:m.index});
  for(let i=0;i<heads.length;i++){
    if(heads[i].k!=='PROMPT')continue;
    const end=i+1<heads.length?heads[i+1].s:raw.length;
    const body=raw.slice(heads[i].e,end),core=body.trim();
    if(!core)return raw;
    const lead=body.slice(0,body.length-body.replace(/^\s+/,'').length);
    const trail=body.slice(body.replace(/\s+$/,'').length);
    return raw.slice(0,heads[i].e)+lead+core+'\n\n'+STATUS_CONTRACT+trail+raw.slice(end);
  }
  return raw; /* unparseable raw passes through, same as the server */
}

let ctrl=null,running=false,lastRaw='';
function setRunning(on){running=on;$('go').disabled=on;$('resub').disabled=on;$('stop').hidden=!on}
function showError(msg){$('errcard').hidden=false;$('errtext').textContent=msg}
function resetPanes(){
  $('errcard').hidden=true;$('result').hidden=true;
  ['barcard','promptcard','notescard','rawcard'].forEach(i=>$(i).hidden=true);
  $('think').textContent='';$('thinkbox').hidden=true;$('thinkbox').open=false;
  $('tspin').style.display='';
  $('liveraw').textContent='';$('livebox').hidden=true;
  snap=null;checkDirty(); /* stop/error/rerun paths never keep a stale snapshot */
}

/* ---- resubmit + dirty state: the form values are captured AT SUBMIT (what
   actually generated the prompt) and become the snapshot only when the run
   SUCCEEDS; any change vs the snapshot shows the stale banner near the
   results, and returning to the snapshot (or resubmitting) clears it.
   No snapshot (before first generation, after stop/error) = no banner. */
const FORM_IDS=['goal','mode','wtype','harness','refs','cons','bounds','statuspage'];
let snap=null;
/* checkbox-aware value read: the status-page toggle is part of the snapshot,
   so flipping it after a generation trips the stale banner like any field */
function fieldVal(i){const el=$(i);return el.type==='checkbox'?String(el.checked):el.value}
function formVals(){const v={};FORM_IDS.forEach(i=>v[i]=fieldVal(i));return v}
function checkDirty(){
  const dirty=!!snap&&FORM_IDS.some(i=>fieldVal(i)!==snap[i]);
  $('stale').hidden=!dirty;
  /* when dirty, Regenerate would do exactly what Resubmit does — hide it so
     the stale banner is the single call to action */
  $('again').hidden=dirty;
}

/* goal is the SUBMIT-TIME goal (captured in run()) — history must pair the
   prompt with the goal that generated it, not whatever sits in the textarea
   at render time (a mid-generation edit used to store a mismatched pair) */
function render(raw,partial,fromHist,goal){
  lastRaw=raw;
  const s=parseSections(raw);
  $('result').hidden=false;
  if(s&&s.prompt){
    if(s.bar){$('barcard').hidden=false;$('bartext').textContent=s.bar;
      $('whytext').textContent=s.why||'';$('whytext').hidden=!s.why}
    $('promptcard').hidden=false;$('prompttext').textContent=s.prompt;
    if(s.notes){$('notescard').hidden=false;$('notestext').textContent=s.notes}
    if(!partial&&!fromHist&&goal!=null)saveHist(goal,s.prompt,raw);
  }else{
    /* never show nothing: whatever the model said, it is copyable */
    $('rawcard').hidden=false;$('rawtext').textContent=raw;
  }
  $('result').scrollIntoView({behavior:'smooth',block:'nearest'});
}

async function run(){
  const goal=$('goal').value.trim();
  if(!goal){$('goal').focus();return}
  if(running)return;
  setRunning(true);resetPanes();
  ctrl=new AbortController();
  let content='',gotDone=false,streamErr=null,aborted=false,lintWarn=null;
  const vals=formVals(); /* snapshot candidate: exactly what is submitted */
  /* captured AT SUBMIT like the goal: the append must reflect the state that
     generated this prompt, not a toggle flipped mid-run. False for (web)
     harnesses — a chat target can't write files. */
  const wantContract=vals.statuspage==='true'&&!vals.harness.endsWith('(web)');
  const body={goal:goal,mode:vals.mode,work_type:vals.wtype,
    harness:vals.harness,references:vals.refs,
    constraints:vals.cons,boundaries:vals.bounds,
    status_page:wantContract,stream:true};
  try{
    const r=await fetch('/api/generate',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body),signal:ctrl.signal});
    const ct=r.headers.get('content-type')||'';
    if(ct.indexOf('text/event-stream')<0){
      let msg='HTTP '+r.status+' from /api/generate';
      try{const j=await r.json();if(j.error)msg=j.error}catch(e){}
      showError(msg);setRunning(false);return}
    const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
    while(true){
      const st=await rd.read();
      if(st.done)break;
      buf+=dec.decode(st.value,{stream:true});
      let i;
      while((i=buf.indexOf('\n\n'))>=0){
        const frame=buf.slice(0,i);buf=buf.slice(i+2);
        for(const line of frame.split('\n')){
          if(line.indexOf('data:')!==0)continue;
          let ev;try{ev=JSON.parse(line.slice(5))}catch(e){continue}
          if(ev.type==='reasoning'){
            $('thinkbox').hidden=false;
            $('think').textContent+=ev.text;
            $('think').scrollTop=$('think').scrollHeight}
          else if(ev.type==='content'){
            $('tspin').style.display='none';
            $('livebox').hidden=false;
            content+=ev.text;
            $('liveraw').textContent=content;
            $('liveraw').scrollTop=$('liveraw').scrollHeight}
          else if(ev.type==='done'){gotDone=true}
          /* replace: the server repaired the (web) closer after the stream —
             swap the buffer for the corrected raw before rendering */
          else if(ev.type==='replace'){content=ev.text}
          else if(ev.type==='lint'){lintWarn=ev.text}
          else if(ev.type==='error'){streamErr=ev.text}
        }
      }
    }
  }catch(e){
    if(e.name==='AbortError')aborted=true;
    else streamErr=String(e)+' (POST /api/generate)';
  }
  $('tspin').style.display='none';$('livebox').hidden=true;
  /* v0.2.3: deterministic client-side append on a COMPLETE generation only —
     a truncated or stopped prompt never gets a contract stapled to it */
  if(wantContract&&content&&gotDone&&!streamErr&&!aborted)content=applyStatusContract(content);
  if(streamErr&&!content)showError(streamErr);
  else{
    if(streamErr)showError(streamErr+' — showing what arrived before the failure');
    else if(aborted&&content)showError('stopped — showing partial output');
    else if(aborted)showError('stopped before any output arrived');
    if(content)render(content,!gotDone,false,goal);
    else if(!streamErr&&!aborted)showError('the model returned no output');
    /* snapshot only a clean, complete generation — a stopped or failed run
       leaves snap null, so no banner can call its output "fresh". The values
       are the ones submitted, so edits made mid-run read as stale. */
    if(content&&gotDone&&!streamErr&&!aborted){snap=vals;checkDirty()}
    /* lint is a warning on a COMPLETE generation (web-target leak the server
       could not repair) — the result stays rendered and snapshotted */
    if(lintWarn)showError(lintWarn);
  }
  setRunning(false);
}

$('go').onclick=run;
$('again').onclick=run;
$('resub').onclick=run;
$('stop').onclick=()=>{if(ctrl)ctrl.abort()};
/* dirty-state watchers: 'input' catches typing, 'change' catches selects */
FORM_IDS.forEach(i=>{$(i).addEventListener('input',checkDirty);
  $(i).addEventListener('change',checkDirty)});
/* per-target notices, shown under BOTH harness selects: chat targets get the
   real warning (a chat window cannot run the full loop), local targets a quiet
   hint, agentic CLIs nothing. Data-driven so future groups slot in. */
function updateHnotes(){
  const h=$('harness').value;let warn=false,txt='';
  if(h.endsWith('(web)')){warn=true;
    txt='⚠ Chat adaptation active — '+h.replace(' (web)','')+' is a chat window, not an agentic harness: it can’t fan out builder and critic agents, inspect its own output, or keep looping unattended. Your prompt runs the gauntlet as rounds inside the conversation instead — build → harsh critique against the bar → rebuild — and you type “continue” to drive each round. Expect a lighter version of the method; Claude Code or Codex will push much further on the same goal.';}
  else if(h==='opencode'){
    txt='opencode delegates to sub-agents but has no /loop and no ultracode, so the prompt asks it to keep iterating rather than to loop. Quality tracks whichever provider you point it at, not opencode itself — a small local model will build fine and critique weakly. If the goal is visual, check the critic model accepts images: a text-only model cannot blind-compare screenshots and will fall back to reading its own source and calling it good.';}
  else if(h.endsWith('(local)')||h.endsWith('(API)')){
    txt='Runs via whatever agentic CLI drives this model (local or API — e.g. Qwen Code in VSCode) — builders and critics run as separate sessions with fresh context.';}
  const ids=['hnote_d','hnote_f'];
  ids.forEach(id=>{const el=$(id);el.hidden=!txt;
    el.className=warn?'hnote warn':'hnote';el.textContent=txt});
  /* v0.2.3: the status-page toggle needs a filesystem — on a (web) harness
     both checkboxes disable together and the hint says why */
  const web=h.endsWith('(web)');
  ['statuspage','dstatuspage'].forEach(id=>{$(id).disabled=web});
  const st=web?'chat targets can’t write files'
    :'Appends a fixed page contract to the prompt — auto-refreshing, real timestamps, no simulation.';
  ['statushint','dstatushint'].forEach(id=>{$(id).textContent=st});
}
/* two-way harness sync: one choice, either select updates the other */
$('harness').addEventListener('change',()=>{$('dharness').value=$('harness').value;
  updateHnotes()});
$('dharness').addEventListener('change',()=>{$('harness').value=$('dharness').value;
  checkDirty();updateHnotes()});
/* two-way status-page sync, same shape as the harness selects: one state.
   The Form-tab box is the FORM_IDS member, so its own change event already
   runs checkDirty; the Describe-tab box mirrors in and calls it by hand
   (programmatic .checked changes fire no events). */
$('statuspage').addEventListener('change',()=>{$('dstatuspage').checked=$('statuspage').checked});
$('dstatuspage').addEventListener('change',()=>{$('statuspage').checked=$('dstatuspage').checked;
  checkDirty()});
updateHnotes();
/* Cmd/Ctrl+Enter submits whichever tab is active: draft on Describe, generate on Form */
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){
    if($('descpane').hidden)run();else runDraft()}});

async function copyText(t,btn){
  try{await navigator.clipboard.writeText(t)}
  catch(e){const ta=document.createElement('textarea');ta.value=t;
    document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove()}
  const old=btn.textContent;btn.textContent='Copied ✓';
  setTimeout(()=>{btn.textContent=old},1400);
}
/* copy EXACTLY the prompt — the pristine text, no labels, no decoration */
$('copyprompt').onclick=()=>copyText($('prompttext').textContent,$('copyprompt'));
$('copyrawbtn').onclick=()=>copyText($('rawtext').textContent,$('copyrawbtn'));
$('copyall').onclick=()=>copyText(lastRaw,$('copyall'));

/* history: last 10 generations, goal + prompt + timestamp */
let hist=[];
try{hist=JSON.parse(localStorage.getItem('gx_hist')||'[]')}catch(e){hist=[]}
function saveHist(goal,prompt,raw){
  hist.unshift({goal:goal,prompt:prompt,raw:raw,ts:Date.now()});
  hist=hist.slice(0,10);
  try{localStorage.setItem('gx_hist',JSON.stringify(hist))}catch(e){}
  drawHist();
}
function drawHist(){
  if(!hist.length){$('hist').hidden=true;return}
  $('hist').hidden=false;
  const hl=$('hlist');hl.innerHTML='';
  hist.forEach(h=>{
    const d=document.createElement('div');d.className='hitem';
    d.innerHTML='<div class="hq"></div><div class="hm"></div>';
    d.children[0].textContent=h.goal.length>140?h.goal.slice(0,140)+'…':h.goal;
    d.children[1].textContent=new Date(h.ts).toLocaleString();
    d.onclick=()=>{showTab('form');$('goal').value=h.goal;resetPanes();
      render(h.raw||('### PROMPT\n'+h.prompt),false,true)};
    hl.appendChild(d)});
}
$('clearhist').onclick=()=>{hist=[];
  try{localStorage.removeItem('gx_hist')}catch(e){}
  drawHist()};
drawHist();

/* ---- Describe-it tab: draft the form from a one-shot description -------- */
/* Switching tabs only toggles visibility — both panes keep all their state. */
function showTab(which){
  const desc=which==='desc';
  $('descpane').hidden=!desc;$('formpane').hidden=desc;
  $('tabdesc').classList.toggle('active',desc);
  $('tabform').classList.toggle('active',!desc);
}
$('tabdesc').onclick=()=>showTab('desc');
$('tabform').onclick=()=>showTab('form');

function flashField(id){
  const el=$(id);
  el.classList.remove('flash');
  void el.offsetWidth; /* restart the animation on a re-draft */
  el.classList.add('flash');
}

let drafting=false;
async function runDraft(){
  const d=$('desc').value.trim();
  if(!d){$('desc').focus();return}
  if(drafting)return;
  drafting=true;$('draftgo').disabled=true;$('drafthint').hidden=false;
  $('errcard').hidden=true;$('draftraw').hidden=true;
  /* a non-default harness choice rides along as the worked-example line the
     draft prompt knows; the description itself can still override it */
  const dh=$('dharness').value;
  const payload=dh!=='Claude Code'
    ?'Target harness already chosen by user: '+dh+'\n'+d:d;
  try{
    const r=await fetch('/api/draft',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({description:payload})});
    let j=null;try{j=await r.json()}catch(e){}
    if(!r.ok||!j){
      showError((j&&j.error)||('HTTP '+r.status+' from /api/draft'));return}
    /* the server coerces to this same whitelist; the guard keeps an off-list
       value from leaving the select empty. The drafted harness lands in BOTH
       selects — one choice, both tabs. */
    const HS=['Claude Code','Codex','Gemini CLI','opencode','Qwen3 Coder Next (local)',
      'Qwen 3.8 (local)','DeepSeek V4 Flash (local)','Qwen 3.8 Max (API)','Claude (web)',
      'ChatGPT (web)','Google Gemini (web)','Grok (web)'];
    if(!j.goal){
      /* parse failure: stay on this tab, show whatever the model said,
         keep the user's text untouched — but a salvaged harness (the model
         often answers HARNESS even when GOAL is empty) still lands on both
         selects, so the inference is not thrown away */
      if(j.harness&&HS.indexOf(j.harness)>=0){
        $('harness').value=j.harness;$('dharness').value=j.harness;
        flashField('dharness');checkDirty();updateHnotes()}
      $('draftraw').hidden=false;
      $('draftrawtext').textContent=j.raw||'(the model returned no output)';
      return}
    /* populate the form and hand control back — NEVER auto-generate */
    const fills=['goal','mode','wtype','harness'];
    $('goal').value=j.goal;
    $('mode').value=j.mode==='polish'?'polish':'fresh';
    $('wtype').value=(j.work_type&&j.work_type!=='Auto')?j.work_type:'';
    $('harness').value=HS.indexOf(j.harness)>=0?j.harness:'Claude Code';
    $('dharness').value=$('harness').value;
    $('refs').value=j.references||'';if(j.references)fills.push('refs');
    $('cons').value=j.constraints||'';if(j.constraints)fills.push('cons');
    $('bounds').value=j.boundaries||'';if(j.boundaries)fills.push('bounds');
    showTab('form');
    fills.forEach(flashField);
    checkDirty();updateHnotes(); /* programmatic fills fire no input events */
  }catch(e){showError(String(e)+' (POST /api/draft)')}
  finally{drafting=false;$('draftgo').disabled=false;$('drafthint').hidden=true}
}
$('draftgo').onclick=runDraft;
$('copydraftraw').onclick=()=>copyText($('draftrawtext').textContent,$('copydraftraw'));
</script></div></body></html>"""


# --------------------------------------------------------------- HTTP server

class Handler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.0 is deliberate, not an oversight: the streaming response has no
    # Content-Length, so "the body ends when the connection closes" is the
    # framing. HTTP/1.1 would require chunked encoding by hand.
    protocol_version = "HTTP/1.0"
    server_version = "gauntletx/" + VERSION
    # Applies to the client socket. Stops a half-sent POST body from pinning a
    # thread forever; long generations are unaffected because the wait happens
    # on the upstream socket, which has its own timeout.
    timeout = 60

    def log_message(self, *a):
        pass  # quiet like promptx; the terminal is for the banner, not access logs

    # -- plumbing ------------------------------------------------------------

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, obj):
        """One SSE frame, flushed immediately — buffering would defeat the
        entire point of streaming."""
        self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode())
        self.wfile.flush()

    # -- routes --------------------------------------------------------------

    def do_GET(self):
        try:
            self._get()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client went away; nobody left to tell
        except Exception as e:  # noqa: BLE001 — a traceback must never hit the wire
            try:
                self._json({"error": "internal error: {}: {}".format(type(e).__name__, e)}, 500)
            except OSError:
                pass

    def _get(self):
        route = self.path.split("?")[0]
        if route == "/api/version":
            self._json(version_info())
            return
        if route in ("/", "/index.html"):
            # __STATUS_CONTRACT__ is templated in like __VERSION__ (as a JSON
            # string literal) so the UI's client-side append and the server's
            # blocking-door append can never drift apart.
            body = (PAGE.replace("__VERSION__", VERSION)
                    .replace("__STATUS_CONTRACT__", json.dumps(STATUS_CONTRACT))
                    .encode())
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        # Flips once the event-stream headers have gone out. After that point
        # a fresh "HTTP/1.0 500" status line would be written INTO the open
        # SSE body — the browser would drop it as garbage and render silently
        # truncated output — so late failures must become SSE error events.
        self._sse_started = False
        try:
            self._post()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        except Exception as e:  # noqa: BLE001
            msg = "internal error: {}: {}".format(type(e).__name__, e)
            try:
                if self._sse_started:
                    self._sse({"type": "error", "text": msg})
                else:
                    self._json({"error": msg}, 500)
            except OSError:
                pass

    def _post(self):
        route = self.path.split("?")[0]
        if route == "/api/generate":
            self._generate()
            return
        if route == "/api/draft":
            self._draft()
            return
        self._json({"error": "not found"}, 404)

    def _read_json_body(self):
        """The request body as a dict, or None with the 400 already written.
        Shared by both POST routes so the size cap and the shape check stay
        identical no matter which door the request came through."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 256 * 1024:
                self._json({"error": "request body too large"}, 400)
                return None
            p = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(p, dict):
                raise ValueError("body must be a JSON object")
            return p
        except (ValueError, OSError):
            self._json({"error": "bad request: body must be a JSON object"}, 400)
            return None

    def _draft(self):
        """POST /api/draft — blocking only (the output is a handful of short
        fields; streaming would buy nothing). Expands a one-shot description
        into coerced form fields via DRAFT_PROMPT."""
        p = self._read_json_body()
        if p is None:
            return
        v = p.get("description")
        description = v if isinstance(v, str) else ("" if v is None else str(v))
        if not description.strip():
            self._json({"error": "description is required"}, 400)
            return
        if len(description) > DESC_MAX:
            self._json({"error": "description is too long ({} chars; max {})".format(
                len(description), DESC_MAX)}, 400)
            return
        result, err = draft_blocking(description)
        if err:
            # Same 502 semantics as /api/generate: the message names the
            # vLLM URL it tried.
            self._json({"error": err}, 502)
            return
        self._json(result)

    def _generate(self):
        p = self._read_json_body()
        if p is None:
            return

        def field(key):
            v = p.get(key)
            if v is None:
                return ""
            return v if isinstance(v, str) else str(v)

        goal = field("goal")
        mode = field("mode")  # "fresh" (default) or "polish"; unknown → fresh
        work_type = field("work_type")
        references = field("references")
        constraints = field("constraints")
        boundaries = field("boundaries")
        # Same whitelist landing as /api/draft — v0.2.1 e2e caught an unknown
        # harness ("FooCLI") flowing verbatim into the meta-prompt from here.
        harness = coerce_harness(field("harness"))
        # v0.2.3 toggle, default false. Applied on the BLOCKING door only:
        # the streaming door leaves the SSE frame order untouched and the UI
        # performs the same deterministic append client-side from its
        # embedded copy of STATUS_CONTRACT.
        status_page = bool(p.get("status_page"))
        err = validate_inputs(goal, references, constraints, boundaries)
        if err:
            self._json({"error": err}, 400)
            return

        if not p.get("stream"):
            result, err = generate_blocking(goal, mode, work_type, references,
                                            constraints, boundaries, harness,
                                            status_page)
            if err:
                self._json({"error": err}, 502)
                return
            self._json(result)
            return

        # Streaming. Open the upstream first: a connect failure should be a
        # clean 502, not a 200 that immediately errors.
        resp, err = open_vllm(
            build_user_message(goal, mode, work_type, references, constraints,
                               boundaries, harness),
            stream=True)
        if err:
            self._json({"error": err}, 502)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")  # if a proxy ever fronts this
        self.end_headers()
        self._sse_started = True
        saw_done = False
        acc = []  # streamed content, for the (web) post-generation guards
        try:
            with resp:
                for kind, text in sse_events(resp):
                    if kind == "done":
                        saw_done = True
                        break
                    if kind == "content":
                        acc.append(text)
                    self._sse({"type": kind, "text": text})
            if saw_done:
                # (web) guards on the finished stream: the tokens already went
                # out live, so a repaired closer arrives as one `replace` frame
                # (the full corrected raw — the UI swaps its buffer before
                # rendering) and a leak arrives as a `lint` warning frame.
                # Non-web harnesses take this path untouched.
                raw, changed, lint = harden_output("".join(acc), harness)
                if changed:
                    self._sse({"type": "replace", "text": raw})
                if lint:
                    self._sse({"type": "lint", "text": lint})
                self._sse({"type": "done", "text": ""})
            else:
                # Upstream closed at a chunk boundary without [DONE] — the
                # only sign of truncation is the missing terminator, and
                # "done" here would save a half-written prompt as a success.
                self._sse({"type": "error",
                           "text": "stream from {} ended before completion — "
                                   "output truncated".format(VLLM_URL)})
        # IncompleteRead (FIN mid-chunk) is an HTTPException, not an OSError.
        except (OSError, ValueError, http.client.HTTPException) as e:
            # Upstream died mid-stream (or the client did — in which case this
            # write fails too and the outer handler swallows it).
            self._sse({"type": "error",
                       "text": "stream from {} failed: {}".format(VLLM_URL, e)})


class GXServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True  # in-flight generations die with the process; that is fine


def run_server(args):
    try:
        srv = GXServer((args.host, args.port), Handler)
    except OSError as e:
        sys.exit("gauntletx: cannot bind {}:{} — {}".format(args.host, args.port, e))
    print("gauntletx v{} serving on http://{}:{}".format(VERSION, args.host, args.port))
    print("  vLLM: {}  model: {}".format(
        VLLM_URL, MODEL_ENV or "(auto-discover from {})".format(models_url())))
    with srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\ngauntletx: shutting down")
    return 0


# ------------------------------------------------------------------ CLI mode

class SectionStream:
    """Prints each ### section the moment its end is known.

    The end of section N is the start of heading N+1; the final section ends
    at end-of-stream, so finish() must be called. Anything before the first
    heading (models sometimes chat) is printed once, unlabelled, when the
    first heading shows up — and a reply with no headings at all is printed
    raw by finish(), so a malformed reply reaches the terminal instead of
    vanishing.
    """

    LABELS = {"BAR": "THE BAR", "WHY": "WHY IT WORKS",
              "PROMPT": "PROMPT — paste into your harness", "NOTES": "NOTES"}

    def __init__(self, status_contract=None):
        self.buf = ""
        self.emitted = 0  # headings whose section body has been printed
        self.preamble_done = False
        # v0.2.3: when set, appended to the PROMPT section at print time.
        # The body is complete by then (a section prints only once its end
        # is known), so this is still "append after parse" — the stream
        # itself is untouched. run_cli only sets it for non-web harnesses.
        self.status_contract = status_contract

    def feed(self, text):
        self.buf += text
        self._drain(final=False)

    def finish(self):
        self._drain(final=True)
        sys.stdout.flush()

    def _drain(self, final):
        heads = list(SECTION_RE.finditer(self.buf))
        if heads and not self.preamble_done:
            pre = self.buf[:heads[0].start()].strip()
            if pre:
                print(pre)
            self.preamble_done = True
        # While streaming, a section is complete only once the NEXT heading
        # has arrived; the last section is only safe to print at the end.
        limit = len(heads) if final else len(heads) - 1
        while self.emitted < limit:
            h = heads[self.emitted]
            end = (heads[self.emitted + 1].start()
                   if self.emitted + 1 < len(heads) else len(self.buf))
            self._section(h.group(1).upper(), self.buf[h.end():end])
            self.emitted += 1
        if final and not heads:
            leftover = self.buf.strip()
            if leftover:
                print(leftover)

    def _section(self, name, body):
        body = body.strip()
        if not body:
            return
        if name == "PROMPT" and self.status_contract:
            body = body + "\n\n" + self.status_contract
        print("\n\033[2m── {} ──\033[0m".format(self.LABELS.get(name, name)))
        print(body)
        sys.stdout.flush()


def _print_final(raw, args):
    """Non-streamed output paths: --raw, --quiet, or formatted sections."""
    if args.raw:
        print(raw)
        return
    if args.quiet:
        prompt = parse_sections(raw).get("prompt")
        if prompt is None:
            sys.stderr.write("gauntletx: no ### PROMPT section found; printing raw output\n")
        print(prompt if prompt is not None else raw.strip())
        return
    p = SectionStream()
    p.feed(raw)
    p.finish()


def run_cli(args):
    goal = " ".join(args.goal).strip()
    mode = "polish" if args.polish else "fresh"
    # Same whitelist landing as the API doors: "codex" still means Codex,
    # but nothing off-list ever reaches the meta-prompt verbatim.
    harness = coerce_harness(args.harness)
    # v0.2.3 toggle. Same door policy as the API — ignored for a (web)
    # harness, never an error — but a CLI user asked explicitly, so say so.
    status_page = bool(args.status_page)
    if status_page and is_web_harness(harness):
        sys.stderr.write("gauntletx: warning: --status-page ignored — {} is a "
                         "chat target and can't write files\n".format(harness))
        status_page = False
    err = validate_inputs(goal, args.refs, args.constraints, args.boundaries)
    if err:
        sys.exit("gauntletx: " + err)

    if args.no_stream:
        result, err = generate_blocking(goal, mode, args.type, args.refs,
                                        args.constraints, args.boundaries,
                                        harness, status_page)
        if err:
            sys.exit("gauntletx: " + err)
        if result.get("lint"):
            sys.stderr.write("gauntletx: warning: {}\n".format(result["lint"]))
        _print_final(result["raw"], args)
        return 0

    resp, err = open_vllm(
        build_user_message(goal, mode, args.type, args.refs, args.constraints,
                           args.boundaries, harness),
        stream=True)
    if err:
        sys.exit("gauntletx: " + err)

    # Default streamed output: reasoning suppressed, each section printed as
    # it completes. --verbose mirrors the thinking to stderr (dim) so stdout
    # stays clean for piping; --raw passes content straight through.
    if args.raw and status_page:
        # --raw streamed is a verbatim passthrough (no parse happens, same
        # reason the harden_output guards skip it) — the contract cannot be
        # inserted mid-stream without misplacing it after NOTES.
        sys.stderr.write("gauntletx: note: --status-page has no effect on "
                         "streamed --raw output — use --no-stream --raw for "
                         "raw output with the contract in place\n")
    printer = SectionStream(STATUS_CONTRACT if status_page else None)
    parts = []
    reasoned = False
    saw_done = False
    try:
        with resp:
            for kind, text in sse_events(resp):
                if kind == "done":
                    saw_done = True
                    continue
                if kind == "reasoning":
                    if args.verbose:
                        sys.stderr.write("\033[2m" + text + "\033[0m")
                        sys.stderr.flush()
                        reasoned = True
                    continue
                if args.raw:
                    sys.stdout.write(text)
                    sys.stdout.flush()
                elif args.quiet:
                    parts.append(text)
                else:
                    printer.feed(text)
    # IncompleteRead (FIN mid-chunk) is an HTTPException, not an OSError —
    # without it here a dying vLLM prints a raw traceback.
    except (OSError, ValueError, http.client.HTTPException) as e:
        sys.exit("gauntletx: stream from {} failed mid-generation: {}".format(VLLM_URL, e))
    if reasoned:
        sys.stderr.write("\n")
        sys.stderr.flush()
    if not saw_done:
        # Clean close without [DONE]: vLLM went away at a chunk boundary.
        # Whatever printed so far is truncated — exit nonzero and say so, or
        # a half-written prompt pipes onward looking finished.
        if args.raw:
            sys.stdout.write("\n")
            sys.stdout.flush()
        sys.exit("gauntletx: stream from {} ended before completion — "
                 "output truncated".format(VLLM_URL))
    if args.raw:
        sys.stdout.write("\n")
    elif args.quiet:
        # --quiet buffers, so the (web) closer repair lands before printing —
        # same guarantee as the blocking API path.
        raw, _fixed, lint = harden_output("".join(parts), harness)
        if lint:
            sys.stderr.write("gauntletx: warning: {}\n".format(lint))
        prompt = parse_sections(raw).get("prompt")
        if prompt is None:
            sys.stderr.write("gauntletx: no ### PROMPT section found; printing raw output\n")
        else:
            # v0.2.3: appended after parse, before printing — same guarantee
            # as the blocking API door.
            prompt = apply_status_contract(prompt, harness, status_page)
        print(prompt if prompt is not None else raw.strip())
    else:
        printer.finish()
        # Sections already streamed to the terminal and cannot be retracted —
        # the (web) guards downgrade to honest stderr warnings here.
        _raw, changed, lint = harden_output(printer.buf, harness)
        if changed:
            sys.stderr.write("gauntletx: warning: the (web) closer above was "
                             "paraphrased by the model — rerun, or paste the "
                             "exact closer from the method docs\n")
        if lint:
            sys.stderr.write("gauntletx: warning: {}\n".format(lint))
    return 0


def main():
    ap = argparse.ArgumentParser(
        prog="gauntletx",
        description="Generate a Gauntlet Loop prompt (Matt Shumer's method behind "
                    "Claude of Duty) from a goal, using the local vLLM.\n\n"
                    "With a goal: generate and print. Without one: run the web UI.",
        epilog="examples:\n"
               "  gauntletx.py \"a kart racer that runs in the browser\"\n"
               "  gauntletx.py --type Writing --refs \"Paul Graham essays\" \"a landing page essay\"\n"
               "  gauntletx.py --quiet \"...\" | pbcopy\n"
               "  gauntletx.py --host 0.0.0.0 --port 7332      # server for the NAS container\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("goal", nargs="*",
                    help="the goal, in plain words; omit to run the web server")
    ap.add_argument("--type", default="", metavar="KIND",
                    help="work type: game, website, writing, backend, design, "
                         "marketing, research (default: auto-detect)")
    ap.add_argument("--refs", default="", metavar="TEXT",
                    help="references / quality bar you already have")
    ap.add_argument("--constraints", default="", metavar="TEXT",
                    help="hard constraints / must-haves (e.g. 'Three.js only')")
    ap.add_argument("--boundaries", default="", metavar="TEXT",
                    help="hard boundaries the loop must never cross "
                         "(e.g. 'local only — no deploys, nothing live')")
    ap.add_argument("--polish", action="store_true",
                    help="polish an existing build to the bar instead of "
                         "starting fresh")
    ap.add_argument("--harness", default="Claude Code",
                    help="target harness: 'Claude Code' (default), 'Codex', "
                         "'Gemini CLI', 'opencode', 'Qwen3 Coder Next (local)', "
                         "'Qwen 3.8 (local)', 'DeepSeek V4 Flash (local)', 'Qwen 3.8 Max (API)', "
                         "'Claude (web)', 'ChatGPT (web)', "
                         "'Google Gemini (web)', or 'Grok (web)'")
    ap.add_argument("--status-page", action="store_true",
                    help="append the fixed structured-status-page contract "
                         "(a single auto-refreshing progress.html with real "
                         "timestamps) to the generated prompt; ignored with "
                         "a warning for (web) harnesses")
    ap.add_argument("--no-stream", action="store_true",
                    help="wait for the full reply instead of streaming")
    ap.add_argument("--raw", action="store_true",
                    help="print the raw model output including all ### sections")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the prompt (for piping)")
    ap.add_argument("--verbose", action="store_true",
                    help="mirror the model's reasoning to stderr while streaming")
    ap.add_argument("--port", type=int, default=7332,
                    help="server mode: port (default 7332)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="server mode: bind address (default 127.0.0.1; "
                         "use 0.0.0.0 in the container)")
    ap.add_argument("--version", action="version", version="gauntletx " + VERSION)
    args = ap.parse_args()

    if args.goal:
        return run_cli(args)
    return run_server(args)


if __name__ == "__main__":
    sys.exit(main())
