#!/usr/bin/env bash
# Smoke test for a RUNNING gauntletx server. Starts nothing itself.
#
#   ./test_smoke.sh                                   # against http://127.0.0.1:7332
#   BASE_URL=http://a-host-on-your-lan:7332 ./test_smoke.sh   # against another box
#
# Exercises /api/version, two real stream=false generations (plain, and with
# status_page=true asserting the appended contract's final sentence), and one
# real /api/draft, so a full pass means the server AND the vLLM behind it are
# both alive. The generate and draft steps wait up to 630s each — just past the
# server's own 600s GAUNTLETX_TIMEOUT default, so a slow-but-successful call
# is never misreported as FAIL.
#
# Prints PASS/FAIL per check; exits non-zero if anything failed.

set -u

BASE_URL="${BASE_URL:-http://127.0.0.1:7332}"
FAILS=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }

command -v curl >/dev/null 2>&1 || { echo "FAIL: curl not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 not found (needed to parse JSON)"; exit 1; }

echo "gauntletx smoke test against $BASE_URL"
echo

# ---- /api/version ---------------------------------------------------------

VERSION_JSON="$(curl -sf --max-time 10 "$BASE_URL/api/version" 2>/dev/null)" || VERSION_JSON=""

if [ -z "$VERSION_JSON" ]; then
  fail "/api/version reachable at $BASE_URL"
else
  pass "/api/version reachable"
  # Field checks run in one python3 pass; its exit code is the fail count.
  printf '%s' "$VERSION_JSON" | python3 -c '
import json, sys
fails = 0
def check(cond, name):
    global fails
    if cond:
        print("PASS: " + name)
    else:
        print("FAIL: " + name)
        fails += 1
try:
    d = json.load(sys.stdin)
except Exception as e:
    print("FAIL: /api/version returned valid JSON (%s)" % e)
    sys.exit(1)
check(bool(str(d.get("version") or "").strip()), "/api/version: version non-empty")
check("model" in d, "/api/version: model field present")
check(bool(str(d.get("vllm_url") or "").strip()), "/api/version: vllm_url non-empty")
check(isinstance(d.get("vllm_reachable"), bool), "/api/version: vllm_reachable is a boolean")
sys.exit(fails)
'
  FAILS=$((FAILS + $?))
fi

# ---- /api/generate, stream=false ------------------------------------------
# Tiny goal on purpose — this is a smoke test, not a benchmark. --max-time
# sits just past the server's GAUNTLETX_TIMEOUT default (600s): the server
# gets to report its own timeout rather than curl giving up first.

echo
echo "generating (stream=false, up to 630s)..."

GEN_JSON="$(curl -s --max-time 630 -X POST "$BASE_URL/api/generate" \
  -H 'Content-Type: application/json' \
  -d '{"goal": "a tiny browser snake game that feels great to play", "stream": false}')"

if [ -z "$GEN_JSON" ]; then
  fail "/api/generate returned a response"
else
  pass "/api/generate returned a response"
  printf '%s' "$GEN_JSON" | python3 -c '
import json, sys
fails = 0
def check(cond, name):
    global fails
    if cond:
        print("PASS: " + name)
    else:
        print("FAIL: " + name)
        fails += 1
try:
    d = json.load(sys.stdin)
except Exception as e:
    print("FAIL: /api/generate returned valid JSON (%s)" % e)
    sys.exit(1)
if d.get("error"):
    # Surface the server-side reason (e.g. the 502 message names the vLLM
    # URL it tried) instead of three opaque FAILs.
    print("FAIL: /api/generate succeeded (server said: %s)" % d["error"])
    sys.exit(1)
prompt = d.get("prompt") or ""
bar = d.get("bar") or ""
check(bool(prompt.strip()), "generate: prompt non-empty")
check("### " not in prompt, "generate: prompt free of \"### \" headings")
check(bool(bar.strip()), "generate: bar non-empty")
sys.exit(fails)
'
  FAILS=$((FAILS + $?))
fi

# ---- /api/generate, stream=false + status_page ----------------------------
# v0.2.3: the toggle appends the fixed STATUS_CONTRACT deterministically —
# never through the model — so the prompt must END with the contract's final
# sentence, byte for byte.

echo
echo "generating with status_page (stream=false, up to 630s)..."

SP_JSON="$(curl -s --max-time 630 -X POST "$BASE_URL/api/generate" \
  -H 'Content-Type: application/json' \
  -d '{"goal": "a tiny browser snake game that feels great to play", "stream": false, "status_page": true}')"

if [ -z "$SP_JSON" ]; then
  fail "status_page: prompt ends with the status-contract final sentence"
else
  printf '%s' "$SP_JSON" | python3 -c '
import json, sys
name = "status_page: prompt ends with the status-contract final sentence"
try:
    d = json.load(sys.stdin)
except Exception as e:
    print("FAIL: %s (invalid JSON: %s)" % (name, e))
    sys.exit(1)
if d.get("error"):
    print("FAIL: %s (server said: %s)" % (name, d["error"]))
    sys.exit(1)
prompt = (d.get("prompt") or "").rstrip()
if prompt.endswith("Update the page every working turn."):
    print("PASS: " + name)
    sys.exit(0)
print("FAIL: " + name)
sys.exit(1)
'
  FAILS=$((FAILS + $?))
fi

# ---- /api/draft -----------------------------------------------------------
# The worked example straight out of DRAFT_PROMPT — the one input the model
# has seen the ideal answer for, so a FAIL here means plumbing, not taste.

echo
echo "drafting (blocking, up to 630s)..."

DRAFT_JSON="$(curl -s --max-time 630 -X POST "$BASE_URL/api/draft" \
  -H 'Content-Type: application/json' \
  -d '{"description": "i want to analyze this platform located here XXXXX and i want you to improve it. I need it to run faster"}')"

if [ -z "$DRAFT_JSON" ]; then
  fail "/api/draft returned a response"
else
  pass "/api/draft returned a response"
  printf '%s' "$DRAFT_JSON" | python3 -c '
import json, sys
fails = 0
def check(cond, name):
    global fails
    if cond:
        print("PASS: " + name)
    else:
        print("FAIL: " + name)
        fails += 1
try:
    d = json.load(sys.stdin)
except Exception as e:
    print("FAIL: /api/draft returned valid JSON (%s)" % e)
    sys.exit(1)
if d.get("error"):
    print("FAIL: /api/draft succeeded (server said: %s)" % d["error"])
    sys.exit(1)
goal = d.get("goal") or ""
check(bool(goal.strip()), "draft: goal non-empty")
check(d.get("mode") in ("fresh", "polish"), "draft: mode is fresh or polish")
check(d.get("work_type") in ("Auto", "Game", "Website or app", "Writing",
                             "Backend or code", "Design", "Marketing",
                             "Research", "Other"),
      "draft: work_type is an allowed value")
sys.exit(fails)
'
  FAILS=$((FAILS + $?))
fi

# ---- verdict --------------------------------------------------------------

echo
if [ "$FAILS" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
  exit 0
else
  echo "$FAILS CHECK(S) FAILED"
  exit 1
fi
