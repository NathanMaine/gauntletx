# Issue log

Every defect found and fixed. Each links to a GitHub issue carrying the symptom, the
root cause and the resolution. Two have long-form write-ups in this directory where the
reasoning is worth more than the fix.

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

## Long-form write-ups

- [issue-001-degenerate-metric.md](issue-001-degenerate-metric.md) — a run reported 100%
  accuracy that meant nothing. Root cause, why five separate guards all failed to fire,
  and the structure-vs-behaviour finding about deterministic contracts.
- [issue-002-streaming-result-loss.md](issue-002-streaming-result-loss.md) — a completed
  generation rendered nothing. Valid JavaScript, unreachable function, and why a syntax
  check could not have caught it.

## Patterns worth keeping visible

**Silent wrong answers are the expensive ones.** #1, #3 and #11 all produced confident,
successful-looking output that was wrong: a metric with no information, a prompt for the
wrong harness, a generation from a model you did not ask for. None raised an error. None
would have been caught by reading the diff.

**Fixes introduce defects.** #2, #7 and #8 were all created while fixing something else,
and #11 and #12 were created by the feature in #10. Every change here is now gated behind
the self-test button for that reason.

**Test the feature, do not read it.** #11 and #12 were both found by exercising the new
config overrides with deliberately bad input — a model that does not exist, a port that
is closed — rather than by reviewing the patch.
