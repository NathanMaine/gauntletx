# Issue log

Every defect found and fixed. Each links to a GitHub issue with the symptom, root cause and
resolution. Four have long-form write-ups in this directory.

| # | Issue | Fixed in |
|---|---|---|
| [#1](https://github.com/NathanMaine/gauntletx/issues/1) | Degenerate metric: a run reported 100% accuracy that meant nothing | 0.2.8 / 0.2.9 |
| [#2](https://github.com/NathanMaine/gauntletx/issues/2) | Streaming: completed generation rendered nothing, Generate button stuck disabled | 0.2.10 / 0.2.11 |
| [#3](https://github.com/NathanMaine/gauntletx/issues/3) | coerce_harness silently coerced 'opencode' to Claude Code | 0.2.5 |
| [#4](https://github.com/NathanMaine/gauntletx/issues/4) | Gemini CLI target was retired by Google and the roster did not know | 0.2.6 |
| [#5](https://github.com/NathanMaine/gauntletx/issues/5) | Add Antigravity as a target (successor to Gemini CLI) | 0.2.6 |
| [#6](https://github.com/NathanMaine/gauntletx/issues/6) | README: /api/generate harness list missing Qwen 3.8 Max (API); aliases stale since 0.2.2 | 0.2.6 |
| [#7](https://github.com/NathanMaine/gauntletx/issues/7) | README: targets table broken by a footnote inserted mid-table | 0.2.6 |
| [#8](https://github.com/NathanMaine/gauntletx/issues/8) | Self-test reported 3/5 on the container: test suites were not in the image | 0.2.12 |
| [#9](https://github.com/NathanMaine/gauntletx/issues/9) | Self-test did not check the model backend; button was on only one tab | 0.2.13 |
| [#10](https://github.com/NathanMaine/gauntletx/issues/10) | Config page: set the prompting model from the UI, not just env vars | 0.3.0 |
| [#11](https://github.com/NathanMaine/gauntletx/issues/11) | Explicit model override silently ignored by the 404 retry path | 0.3.0 |
| [#12](https://github.com/NathanMaine/gauntletx/issues/12) | Connection errors named the default URL, not the overridden one | 0.3.0 |
| [#13](https://github.com/NathanMaine/gauntletx/issues/13) | Prompt told agents to fan out sub-agents with no fallback when the harness has none | 0.3.1 |
| [#14](https://github.com/NathanMaine/gauntletx/issues/14) | Autonomy was assumed, not instructed — one harness stopped for approval, another looped without progress | 0.3.5 |
| [#15](https://github.com/NathanMaine/gauntletx/issues/15) | BASELINE_CONTRACT was satisfied by a baseline that was computed wrong | 0.3.6 |
| 16 † | A working generation reported as "the model returned no output": token budget half what a reasoning model needed, thinking pane blanked by an upstream field rename, truncation indistinguishable from success | 0.3.7 |

† No GitHub issue filed — found and fixed in one session.

## Long-form write-ups

- [issue-001-degenerate-metric.md](issue-001-degenerate-metric.md) — a run reported 100%
  accuracy that meant nothing.
- [issue-002-streaming-result-loss.md](issue-002-streaming-result-loss.md) — a completed
  generation rendered nothing, through valid-but-unreachable JavaScript.
- [issue-003-broken-guard.md](issue-003-broken-guard.md) — the guard was present, called,
  reported, and wrong. Worse than absent, because it manufactured confidence.
- [issue-004-silent-truncation.md](issue-004-silent-truncation.md) — six minutes of
  nothing, from a model that was working fine. Three defects stacked to hide a healthy
  generation, and the most satisfying root cause turned out not to be the cause.

## Patterns worth keeping visible

**Silent wrong answers are the expensive ones.** #1, #3, #11 and #15 all produced
confident, successful-looking output that was wrong. None raised an error.

**Fixes introduce defects.** #2, #7 and #8 were created while fixing something else; #11
and #12 by the feature in #10.

**Test the feature, do not read it.** #11 and #12 were found by feeding the config
overrides a model that does not exist and a port that is closed. #13's first fix was a
SYSTEM_PROMPT sentence the model silently dropped, caught by generating and grepping.

**Falsify the satisfying cause.** #16's investigation turned up a real contradiction in
SYSTEM_PROMPT, visible in the model's own reasoning, that was *not* the cause — removing
it reproduced the failure unchanged. A plausible cause found mid-investigation still needs
the one run that would rule it out.

**A terminator is not a completion.** #2 and #16 both mistook a transport signal for a
work signal: the stream closed, so the generation must have finished. Where a protocol
offers a separate completion field, reading the transport instead is a bug waiting for a
slow day.

**Upstreams rename things.** #4 (a retired harness) and #16 (`reasoning_content` →
`reasoning` in a vLLM minor release) are the same failure from opposite directions —
something outside the repo changed and nothing inside it noticed.

**Advice competes for budget; a contract does not.** #1, #2, #13 and #14 each ended with
the fix moving out of SYSTEM_PROMPT into a deterministic append the model never sees.

**A contract must assert a property of the value, not just its presence.** #15 is the
counterexample to the rule above: the append was there, honoured, and useless, because
"print the baseline" is satisfied by printing a wrong baseline.

**The method assumed the harness.** #13 and #14 are cases where the Gauntlet Loop took for
granted something true of Claude Code and false of a flash-tier IDE agent or a small local
model. Generalising to thirteen harnesses means writing down what its author never had to.
