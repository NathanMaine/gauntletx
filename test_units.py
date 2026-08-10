#!/usr/bin/env python3
"""The unit suite cited in the CHANGELOG: 47 coerce_harness
cases (27 v0.2.1 + 20 v0.2.2 family-alias) + 12 v0.2.3 apply_status_contract
cases = 67. Stdlib only, no server, no network — importing gauntletx runs
nothing but module-level definitions.

Run:  python3 test_units.py        (exit 0 and "59/59" totals on success)

Committed after the 0.2.2 verification pass found the cited suite was not in
the repo (the numbers were real but unreproducible). This file is now the
canonical suite — extend it here, and keep the CHANGELOG count in sync.
"""

import sys

from gauntletx import (HARNESSES, STATUS_CONTRACT, apply_status_contract,
                       coerce_harness)

# Sanity: the roster the cases coerce onto, in UI <optgroup> order.
assert HARNESSES == (
    "Claude Code", "Codex", "Gemini CLI", "opencode", "Antigravity",
    "Qwen3 Coder Next (local)", "Qwen 3.8 (local)", "DeepSeek V4 Flash (local)",
    "Qwen 3.8 Max (API)",
    "Claude (web)", "ChatGPT (web)", "Google Gemini (web)", "Grok (web)",
), "HARNESSES roster changed — update this suite deliberately"

# 27 v0.2.1 cases: the six exact values, casefold variants, the qualifier/
# nickname drops the draft model actually produces, and the fallbacks.
# Every one of these coerced identically in 0.2.1 (the six-harness roster).
V021_CASES = [
    # exact (6)
    ("Claude Code", "Claude Code"),
    ("Codex", "Codex"),
    ("Gemini CLI", "Gemini CLI"),
    ("Qwen3 Coder Next (local)", "Qwen3 Coder Next (local)"),
    ("Qwen 3.8 (local)", "Qwen 3.8 (local)"),
    ("DeepSeek V4 Flash (local)", "DeepSeek V4 Flash (local)"),
    # casefold / whitespace (6)
    ("claude code", "Claude Code"),
    ("codex", "Codex"),
    ("CODEX", "Codex"),
    ("  Codex  ", "Codex"),
    ("gemini cli", "Gemini CLI"),
    ("GEMINI CLI", "Gemini CLI"),
    # qualifier drops and nicknames (11)
    ("Qwen3 Coder (local)", "Qwen3 Coder Next (local)"),  # the 0.2.1 bug case
    ("qwen 3 coder", "Qwen3 Coder Next (local)"),
    ("qwen coder", "Qwen3 Coder Next (local)"),
    ("qwen3 coder next", "Qwen3 Coder Next (local)"),
    ("qwen", "Qwen3 Coder Next (local)"),
    ("Qwen 3.8", "Qwen 3.8 (local)"),
    ("qwen 3.8 (local)", "Qwen 3.8 (local)"),
    ("deepseek", "DeepSeek V4 Flash (local)"),
    ("DeepSeek V4 Flash", "DeepSeek V4 Flash (local)"),
    ("deepseek v4", "DeepSeek V4 Flash (local)"),
    ("deepseek v4 flash (local)", "DeepSeek V4 Flash (local)"),
    # fallbacks — off-list and junk land on the default, never verbatim (4)
    ("", "Claude Code"),
    (None, "Claude Code"),
    ("FooCLI", "Claude Code"),  # the 0.2.1 /api/generate leak case
    ("x", "Claude Code"),
]
assert len(V021_CASES) == 27, "v0.2.1 case count drifted: %d" % len(V021_CASES)

# 20 v0.2.2 alias cases: the four (web) exact values plus the family aliases
# (bare name means the chat app; "code"/"cli" still means the CLI target).
ALIAS_CASES = [
    # exact (4)
    ("Claude (web)", "Claude (web)"),
    ("ChatGPT (web)", "ChatGPT (web)"),
    ("Google Gemini (web)", "Google Gemini (web)"),
    ("Grok (web)", "Grok (web)"),
    # claude family (4)
    ("claude", "Claude (web)"),
    ("Claude", "Claude (web)"),
    ("claude.ai", "Claude (web)"),
    ("claude web", "Claude (web)"),
    # gpt family (4)
    ("chatgpt", "ChatGPT (web)"),
    ("chat gpt", "ChatGPT (web)"),
    ("gpt", "ChatGPT (web)"),
    ("ChatGPT", "ChatGPT (web)"),
    # gemini family (5)
    ("gemini", "Google Gemini (web)"),
    ("Gemini", "Google Gemini (web)"),
    ("google gemini", "Google Gemini (web)"),
    ("google gemini (web)", "Google Gemini (web)"),
    ("gemini web", "Google Gemini (web)"),
    # grok family (3)
    ("grok", "Grok (web)"),
    ("Grok", "Grok (web)"),
    ("grok (web)", "Grok (web)"),
]
assert len(ALIAS_CASES) == 20, "alias case count drifted: %d" % len(ALIAS_CASES)

# 8 v0.2.4 cases: the Qwen 3.8 Max (API) target — "max"/"api" next to qwen means
# the Token-Plan flagship via Qwen Code, and bare "qwen 3.8" must STAY local
# (each key is a prefix of the other; the generic loops cannot split them).
API_CASES = [
    ("Qwen 3.8 Max (API)", "Qwen 3.8 Max (API)"),
    ("qwen 3.8 max", "Qwen 3.8 Max (API)"),
    ("qwen max", "Qwen 3.8 Max (API)"),
    ("qwen 3.8 max api", "Qwen 3.8 Max (API)"),
    ("qwen 3.8 over the api", "Qwen 3.8 Max (API)"),
    ("qwen38max", "Qwen 3.8 Max (API)"),
    ("qwen 3.8", "Qwen 3.8 (local)"),          # regression pin
    ("qwen 3 coder", "Qwen3 Coder Next (local)"),  # regression pin
]
assert len(API_CASES) == 8, "api case count drifted: %d" % len(API_CASES)

# 8 v0.2.5 cases: the opencode target. It sits AFTER Codex in the roster on
# purpose — coerce_harness walks _HARNESS_KEYS in order with a two-way prefix
# test, so a bare "code" has to keep landing on Codex exactly as it did before
# opencode existed. The last three are regression pins for that.
OPENCODE_CASES = [
    ("opencode", "opencode"),
    ("OpenCode", "opencode"),
    ("  opencode  ", "opencode"),
    ("open code", "opencode"),
    ("opencode cli", "opencode"),
    ("code", "Codex"),           # regression pin — must NOT become opencode
    ("codex", "Codex"),          # regression pin
    ("claude code", "Claude Code"),  # regression pin
]
assert len(OPENCODE_CASES) == 8, "opencode case count drifted: %d" % len(OPENCODE_CASES)

# 8 v0.2.6 cases: the Antigravity target. Named "Antigravity", NOT "Google
# Antigravity" — the latter's key would prefix-match a bare "google" from the
# Agentic CLIs group, ahead of Google Gemini (web) in the Online chat group,
# silently breaking that alias. The last three pin the aliases that must survive.
ANTIGRAVITY_CASES = [
    ("Antigravity", "Antigravity"),
    ("antigravity", "Antigravity"),
    ("  ANTIGRAVITY  ", "Antigravity"),
    ("anti gravity", "Antigravity"),
    ("antigravity cli", "Antigravity"),
    ("google", "Google Gemini (web)"),   # regression pin — must NOT become Antigravity
    ("gemini", "Google Gemini (web)"),   # regression pin
    ("gemini cli", "Gemini CLI"),        # regression pin — retired, but still on the roster
]
assert len(ANTIGRAVITY_CASES) == 8, "antigravity case count drifted: %d" % len(ANTIGRAVITY_CASES)

# 12 v0.2.3 cases: apply_status_contract — flag × harness family, plus the
# nothing-to-append-to guards. The append is deterministic (the fixed
# STATUS_CONTRACT paragraph, never the model), so equality checks are exact.
# The smoke test's final-sentence assertion is pinned here too.
assert STATUS_CONTRACT.endswith("Update the page every working turn."), \
    "STATUS_CONTRACT final sentence changed — update test_smoke.sh's check too"

_P = "Build the thing.\n\nFan out sub-agents.\n\nDon't stop until wowed."
_APPENDED = _P + "\n\n" + STATUS_CONTRACT
STATUS_CASES = [
    # (prompt, harness, flag, want)
    # flag on, non-web harnesses: appended (4)
    (_P, "Claude Code", True, _APPENDED),
    (_P, "Codex", True, _APPENDED),
    (_P, "Gemini CLI", True, _APPENDED),
    (_P, "Qwen 3.8 (local)", True, _APPENDED),
    # flag on, (web) harnesses: ignored, never an error (4)
    (_P, "Claude (web)", True, _P),
    (_P, "ChatGPT (web)", True, _P),
    (_P, "Google Gemini (web)", True, _P),
    (_P, "Grok (web)", True, _P),
    # flag off: untouched either way (2)
    (_P, "Claude Code", False, _P),
    (_P, "Grok (web)", False, _P),
    # nothing to append to: pass through, no crash (2)
    ("", "Claude Code", True, ""),
    (None, "Claude Code", True, None),
]
assert len(STATUS_CASES) == 12, "status case count drifted: %d" % len(STATUS_CASES)


def main():
    failures = []
    total = 0
    for label, cases in (("v0.2.1", V021_CASES), ("0.2.2-alias", ALIAS_CASES),
                         ("0.2.4-api", API_CASES),
                         ("0.2.5-opencode", OPENCODE_CASES),
                         ("0.2.6-antigravity", ANTIGRAVITY_CASES)):
        for value, want in cases:
            total += 1
            got = coerce_harness(value)
            if got != want:
                failures.append("  [{}] coerce_harness({!r}) = {!r}, want {!r}"
                                .format(label, value, got, want))
    print("coerce_harness: {}/{} cases pass".format(total - len(failures), total))

    before = len(failures)
    for prompt, harness, flag, want in STATUS_CASES:
        total += 1
        got = apply_status_contract(prompt, harness, flag)
        if got != want:
            failures.append(
                "  [0.2.3-status] apply_status_contract({!r}, {!r}, {!r}) = "
                "{!r}, want {!r}".format(prompt, harness, flag, got, want))
    print("apply_status_contract: {}/{} cases pass".format(
        len(STATUS_CASES) - (len(failures) - before), len(STATUS_CASES)))

    print("total: {}/{}".format(total - len(failures), total))
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
