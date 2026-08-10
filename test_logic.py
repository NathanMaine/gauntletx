#!/usr/bin/env python3
"""Coverage suite for gauntletx's pure logic.

Companion to test_units.py, which owns coerce_harness and the two contract
doors. This file covers every remaining function that can be exercised without
a network or a running server: env parsing, URL derivation, input validation,
section parsing, the (web) closer repair, harden_output, the raw-reflection
doors, and SectionStream.

Deliberately NOT covered, and why — these need a live vLLM or a bound socket,
so a unit suite that "covered" them would only be asserting against mocks it
wrote itself:

    resolve_model, open_vllm, call_blocking, generate_blocking,
    draft_blocking, run_server, run_cli, _print_final, Handler, GXServer

`version_info` is excluded for the same reason: it performs a reachability
probe. `sse_events` IS covered, using a fake iterable that mimics the response
object's line protocol — that is a data transform, not a network call.

Run:  python3 test_logic.py        (exit 0 and "N/N" on success)
      python3 test_logic.py --cov  (adds a stdlib-trace line-coverage report)
"""
import io
import json
import sys

import gauntletx as G

FAILS = []
N = 0


def check(label, got, want):
    global N
    N += 1
    if got != want:
        FAILS.append("  [{}]\n      got  {!r}\n      want {!r}".format(label, got, want))


def check_true(label, cond):
    check(label, bool(cond), True)


# ---------------------------------------------------------------- _num
import os

os.environ["GX_T_OK"] = "42"
os.environ["GX_T_BAD"] = "not-a-number"
check("_num reads env", G._num("GX_T_OK", 7, int), 42)
check("_num default when unset", G._num("GX_T_MISSING", 7, int), 7)
check("_num float cast", G._num("GX_T_OK", 0.0, float), 42.0)
try:
    G._num("GX_T_BAD", 7, int)
    check("_num raises on garbage", "no raise", "SystemExit or ValueError")
except (SystemExit, ValueError):
    check("_num raises on garbage", True, True)

# ---------------------------------------------------------- _harness_key
check("_harness_key drops parens", G._harness_key("Qwen 3.8 (local)"), "qwen3.8")
check("_harness_key casefolds", G._harness_key("CODEX"), "codex")
check("_harness_key strips punctuation", G._harness_key("Claude Code"), "claudecode")
check("_harness_key keeps dots", G._harness_key("qwen 3.8"), "qwen3.8")
check("_harness_key on None", G._harness_key(None), "")

# ------------------------------------------------------------ models_url
check_true("models_url ends /v1/models", G.models_url().endswith("/v1/models"))
check_true("models_url drops chat path", "/chat/completions" not in G.models_url())

# -------------------------------------------------------------- _headers
h = G._headers()
check("_headers content-type", h.get("Content-Type"), "application/json")
check_true("_headers auth only when key set",
           ("Authorization" in h) == bool(getattr(G, "API_KEY", "")))

# --------------------------------------------------------- is_web_harness
for w in ("Claude (web)", "ChatGPT (web)", "Google Gemini (web)", "Grok (web)"):
    check_true("is_web_harness true: " + w, G.is_web_harness(w))
for a in ("Claude Code", "Codex", "Gemini CLI", "opencode", "Antigravity",
          "Qwen 3.8 (local)", "Qwen 3.8 Max (API)"):
    check("is_web_harness false: " + a, G.is_web_harness(a), False)

# -------------------------------------------------------- validate_inputs
check("validate empty goal", G.validate_inputs("", "", "", ""), "goal is required")
check("validate whitespace goal", G.validate_inputs("   ", "", "", ""), "goal is required")
check("validate None goal", G.validate_inputs(None, "", "", ""), "goal is required")
check("validate ok", G.validate_inputs("build a thing", "", "", ""), None)
check_true("validate goal cap", "too long" in G.validate_inputs("x" * (G.GOAL_MAX + 1), "", "", ""))
check_true("validate refs cap", "references too long" in
           G.validate_inputs("g", "x" * (G.REFS_MAX + 1), "", ""))
check_true("validate constraints cap", "constraints too long" in
           G.validate_inputs("g", "", "x" * (G.CONS_MAX + 1), ""))
check_true("validate boundaries cap", "boundaries too long" in
           G.validate_inputs("g", "", "", "x" * (G.BOUND_MAX + 1)))
check("validate accepts None optionals", G.validate_inputs("g", None, None, None), None)

# ---------------------------------------------------- build_user_message
msg = G.build_user_message("build a kart racer", "fresh", "Game", "Mario Kart 8",
                           "no deps", "local only", "Claude Code")
for token in ("build a kart racer", "Game", "Mario Kart 8", "no deps",
              "local only", "Claude Code"):
    check_true("build_user_message carries " + token, token in msg)
# Empty optionals are NOT omitted — they become explicit "none" markers, so the
# model knows a section was considered rather than forgotten. (An earlier
# version of this test asserted omission; the code's behaviour is the better
# design and the test was wrong.)
bare = G.build_user_message("g", "fresh", "", "", "", "", "Codex")
check_true("build_user_message names the harness", "Codex" in bare)
check_true("build_user_message marks empty work type", "auto-detect" in bare)
check_true("build_user_message marks empty constraints", "none" in bare)
check_true("build_user_message tasks the agent to find a bar when refs empty",
           "finding one" in bare)

# -------------------------------------------------------- parse_sections
RAW = ("### BAR\nthe bar\n\n### WHY\nbecause\n\n"
       "### PROMPT\nthe prompt body\n\n### NOTES\n- one\n")
s = G.parse_sections(RAW)
check("parse bar", s.get("bar"), "the bar")
check("parse why", s.get("why"), "because")
check("parse prompt", s.get("prompt"), "the prompt body")
check("parse notes", s.get("notes"), "- one")
check("parse missing section", G.parse_sections("### BAR\nonly\n").get("prompt"), None)
check("parse no headings", G.parse_sections("just prose").get("prompt"), None)
check("parse empty section", G.parse_sections("### BAR\n\n### WHY\nw\n").get("bar"), None)

# ----------------------------------------------------------- _prompt_span
span = G._prompt_span(RAW)
check_true("_prompt_span found", span is not None)
check("_prompt_span body", RAW[span[0]:span[1]].strip(), "the prompt body")
check("_prompt_span absent", G._prompt_span("### BAR\nx\n"), None)

# ------------------------------------------------------ _repair_web_closer
good = "Do the thing. " + G.WEB_CLOSER
p, changed = G._repair_web_closer(good)
check("_repair_web_closer leaves good alone", changed, False)
p2, changed2 = G._repair_web_closer("Do the thing.")
check("_repair_web_closer appends", changed2, True)
check_true("_repair_web_closer result ends with closer", p2.rstrip().endswith(G.WEB_CLOSER.rstrip()))

# --------------------------------------------------------- harden_output
web_raw = RAW.replace("the prompt body", "Do it. Use sub-agents, /loop, and ultracode.")
out, fixed, lint = G.harden_output(web_raw, "Claude (web)")
check_true("harden_output flags agentic leak on (web)", bool(lint) or bool(fixed))
out2, fixed2, lint2 = G.harden_output(RAW, "Claude Code")
check("harden_output leaves agentic target alone", out2, RAW)
check("harden_output no lint for agentic", lint2, None)

# ------------------------------------------- contract raw-reflection doors
sr = G._status_contract_raw(RAW, "Claude Code", True)
check_true("status raw door inserts", G.STATUS_CONTRACT in sr)
check_true("status raw door keeps NOTES", "### NOTES" in sr)
check_true("status raw door inside prompt section",
           sr.index(G.STATUS_CONTRACT) < sr.index("### NOTES"))
check("status raw door off", G._status_contract_raw(RAW, "Claude Code", False), RAW)
check("status raw door web-gated", G._status_contract_raw(RAW, "Claude (web)", True), RAW)
check("status raw door unparseable", G._status_contract_raw("no headings", "Codex", True), "no headings")

br = G._baseline_contract_raw(RAW, True)
check_true("baseline raw door inserts", G.BASELINE_CONTRACT in br)
check_true("baseline raw door inside prompt section",
           br.index(G.BASELINE_CONTRACT) < br.index("### NOTES"))
check("baseline raw door off", G._baseline_contract_raw(RAW, False), RAW)
check("baseline raw door unparseable", G._baseline_contract_raw("no headings", True), "no headings")
both = G._baseline_contract_raw(G._status_contract_raw(RAW, "Codex", True), True)
check_true("both doors, status first", both.index(G.STATUS_CONTRACT) < both.index(G.BASELINE_CONTRACT))

# ------------------------------------------------------- method contract
check_true("method contract appended for agentic", G.METHOD_CONTRACT in
           G.apply_method_contract("Do it.", "Codex"))
check("method contract skipped for web",
      G.apply_method_contract("Do it.", "Claude (web)"), "Do it.")
check("method contract no prompt", G.apply_method_contract("", "Codex"), "")
check("method contract None", G.apply_method_contract(None, "Codex"), None)
mr = G._method_contract_raw(RAW, "Antigravity")
check_true("method raw door inserts", G.METHOD_CONTRACT in mr)
check_true("method raw door inside prompt section",
           mr.index(G.METHOD_CONTRACT) < mr.index("### NOTES"))
check("method raw door web-gated", G._method_contract_raw(RAW, "Grok (web)"), RAW)
check("method raw door unparseable", G._method_contract_raw("no headings", "Codex"), "no headings")
check_true("method contract forbids frameworks",
           "never build an agent framework" in G.METHOD_CONTRACT)
check_true("method contract forbids key requests",
           "never ask for an API key" in G.METHOD_CONTRACT)
# Retry hygiene, added after a run repeated one SyntaxError-producing command ~10
# times. Worded to leave an artifact (a notes entry) rather than to ask for pure
# restraint — behavioural clauses have a poor record here, structural ones do not.
check_true("method contract caps retries",
           "fails twice with the same error" in G.METHOD_CONTRACT)
check_true("method contract demands a written blocker",
           "into your notes on disk" in G.METHOD_CONTRACT)
# Autonomy. The method assumes the agent will not get blocked — true of Claude
# Code, false of a flash-tier IDE agent and of a small local model. Both observed
# failures are covered: stopping for approval on a decision it was told to make,
# and looping without progress. Judgement calls and missing preconditions are
# deliberately distinguished: a blanket "never ask" would push an agent to invent
# a holdout, which is the failure in issue #1.
check_true("autonomy: decide, do not seek approval",
           "do not stop for approval on anything you were told to decide" in G.METHOD_CONTRACT)
check_true("autonomy: record the decision",
           "record what you chose and why" in G.METHOD_CONTRACT)
check_true("autonomy: stop only when blocked",
           "Stop only when you cannot proceed" in G.METHOD_CONTRACT)
check_true("autonomy: ask rather than substitute",
           "rather than inventing a substitute" in G.METHOD_CONTRACT)
check_true("autonomy: stall detection",
           "treat that as a stall" in G.METHOD_CONTRACT)

# ------------------------------------------------------ sanitize_overrides
def _ok(raw):
    ov, err = G.sanitize_overrides(raw)
    return ov if err is None else ("ERR: " + err)


check("overrides none", _ok(None), {})
check("overrides empty", _ok({}), {})
check("overrides ignores blanks", _ok({"model": "", "vllm_url": "", "temperature": ""}), {})
check("overrides model", _ok({"model": "m1"}), {"model": "m1"})
check("overrides trims model", _ok({"model": "  m1  "}), {"model": "m1"})
check("overrides url http", _ok({"vllm_url": "http://x/v1"}), {"vllm_url": "http://x/v1"})
check("overrides url https", _ok({"vllm_url": "https://x/v1"}), {"vllm_url": "https://x/v1"})
check_true("overrides rejects file scheme", str(_ok({"vllm_url": "file:///etc/passwd"})).startswith("ERR"))
check_true("overrides rejects gopher", str(_ok({"vllm_url": "gopher://x"})).startswith("ERR"))
check_true("overrides rejects overlong url", str(_ok({"vllm_url": "http://" + "x" * 600})).startswith("ERR"))
check_true("overrides rejects overlong model", str(_ok({"model": "x" * 300})).startswith("ERR"))
check("overrides temperature", _ok({"temperature": 0.5}), {"temperature": 0.5})
check("overrides temperature as string", _ok({"temperature": "1.5"}), {"temperature": 1.5})
check_true("overrides temperature high", str(_ok({"temperature": 2.5})).startswith("ERR"))
check_true("overrides temperature negative", str(_ok({"temperature": -1})).startswith("ERR"))
check_true("overrides temperature garbage", str(_ok({"temperature": "hot"})).startswith("ERR"))
check("overrides max_tokens", _ok({"max_tokens": 100}), {"max_tokens": 100})
check_true("overrides max_tokens zero", str(_ok({"max_tokens": 0})).startswith("ERR"))
check_true("overrides max_tokens huge", str(_ok({"max_tokens": 999999})).startswith("ERR"))
check("overrides timeout", _ok({"timeout": 60}), {"timeout": 60})
check_true("overrides timeout too small", str(_ok({"timeout": 1})).startswith("ERR"))
check_true("overrides timeout too big", str(_ok({"timeout": 99999})).startswith("ERR"))
check("overrides combined", _ok({"model": "m", "temperature": 0.2, "max_tokens": 10, "timeout": 30}),
      {"model": "m", "temperature": 0.2, "max_tokens": 10, "timeout": 30})
check("overrides non-dict ignored", _ok("nope"), {})

# ---------------------------------------------------------- config_info
# Shape only — the served-model list depends on a live endpoint, so assert the
# contract the UI relies on rather than the contents.
ci = G.config_info()
for key in ("version", "defaults", "served_models", "limits",
            "model_pinned_by_env", "api_key_set", "discovery_error"):
    check_true("config_info has " + key, key in ci)
for key in ("vllm_url", "model", "temperature", "max_tokens", "timeout"):
    check_true("config_info defaults has " + key, key in ci["defaults"])
check_true("config_info leaks no key value",
           "api_key" not in json.dumps(ci).lower().replace("api_key_set", ""))
check_true("config_info served_models is a list", isinstance(ci["served_models"], list))

# ----------------------------------------------------------- sse_events
class _FakeResp:
    """Mimics the line iteration open_vllm's response provides."""
    def __init__(self, lines):
        self._lines = [l.encode() if isinstance(l, str) else l for l in lines]

    def __iter__(self):
        return iter(self._lines)

    def readline(self):
        return self._lines.pop(0) if self._lines else b""


try:
    ev = list(G.sse_events(_FakeResp([
        'data: {"choices":[{"delta":{"content":"hello "}}]}',
        'data: {"choices":[{"delta":{"reasoning_content":"thinking"}}]}',
        'data: {"choices":[{"delta":{"content":"world"}}]}',
        'data: [DONE]',
    ])))
    kinds = [k for k, _ in ev]
    text = "".join(t for k, t in ev if k == "content")
    check("sse_events content assembled", text, "hello world")
    check_true("sse_events surfaces reasoning", "reasoning" in kinds)
except Exception as e:                                    # pragma: no cover
    check("sse_events raised: " + type(e).__name__, False, True)

# --------------------------------------------------------- SectionStream
buf = io.StringIO()
_stdout = sys.stdout
try:
    sys.stdout = buf
    ss = G.SectionStream(None)
    ss.feed(RAW)
    ss.finish()
finally:
    sys.stdout = _stdout
printed = buf.getvalue()
check_true("SectionStream prints prompt body", "the prompt body" in printed)
check_true("SectionStream labels sections", "THE BAR" in printed or "BAR" in printed)

buf2 = io.StringIO()
try:
    sys.stdout = buf2
    ss2 = G.SectionStream(G.STATUS_CONTRACT)
    ss2.feed(RAW)
    ss2.finish()
finally:
    sys.stdout = _stdout
check_true("SectionStream appends its tail", G.STATUS_CONTRACT[:40] in buf2.getvalue())

buf3 = io.StringIO()
try:
    sys.stdout = buf3
    ss3 = G.SectionStream(None)
    ss3.feed("no headings at all")
    ss3.finish()
finally:
    sys.stdout = _stdout
check_true("SectionStream prints headless reply raw", "no headings at all" in buf3.getvalue())


def main():
    print("test_logic: {}/{} checks pass".format(N - len(FAILS), N))
    if FAILS:
        print("\n".join(FAILS))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
