# Issue 004 — six minutes of nothing, from a model that was working fine

**Status: RESOLVED in v0.3.7** · Raised 2026-08-15 · Closed 2026-08-15

A goal with references, constraints and boundaries filled in returned **"the model
returned no output"** after roughly six minutes of blank spinner. Nothing was down. The
endpoint was reachable, the model was loaded, the request was accepted, and the upstream
streamed for 358 seconds before closing cleanly.

Three unrelated defects stacked up to make a healthy generation look like a dead one. Any
of the three alone would have been visible in seconds.

---

## What was reported

> ERROR
> the model returned no output

That message is honest about what the client saw and useless about what happened. It is
also, as written, indistinguishable from four different failures: a model that replied
with an empty string, a stream that dropped, a parser that ate the content, and the one
that actually occurred.

## What was actually happening

Called directly, with gauntletx's own `SYSTEM_PROMPT` and the same form values:

```
finish_reason = length
completion_tokens = 8192          ← the entire budget
delta keys seen  = {'role': 1, 'reasoning': 3120}
```

**Every one of the 8192 tokens was a thinking token. Not one was content.** The model was
still working out the brief when the budget ran out, so there was no answer to render —
the client was reporting the literal truth.

Raising the cap and rerunning the identical request:

| max_tokens | Thinking | Wall clock | finish_reason | Completion tokens | Result |
| --- | --- | --- | --- | --- | --- |
| 8192 | on | 358s | `length` | 8192 (100% reasoning) | nothing |
| 40960 | on | 657s | `stop` | 15,006 | full BAR/WHY/PROMPT/NOTES |
| 8192 | **off** | **27.5s** | `stop` | **599** | full BAR/WHY/PROMPT/NOTES |

The model needed **~13,400 tokens of thinking before writing its first word**, and ~15,006
to finish. The budget was 8192. It was not close.

Measured on Qwen3.8-27B (NVFP4) under vLLM 0.27.2rc1, temperature 0.7, single run per row.
Reasoning length varies run to run — two thinking-on generations of the same prompt used
53,486 and 65,457 characters of reasoning — which is why the new default leaves headroom
rather than sitting just above the observed maximum.

## Defect 1 — the budget was half what the model needed

`GAUNTLETX_MAX_TOKENS` defaulted to 8192, a number chosen when the prompt was shorter and
the served model did not think before answering. A reasoning model spends the budget in a
different order: all of the thinking first, the answer last. A cap that would merely
truncate a non-reasoning model's reply **deletes a reasoning model's reply entirely.**

`GAUNTLETX_TIMEOUT` had the same problem one layer up, and this is the part worth copying
down: the successful 15k-token run took **657 seconds** against a 600-second timeout.
Raising the token budget alone would have converted a blank result into a timeout and
looked like a regression. **The two knobs are one knob.**

Now 32768 and 1800.

## Defect 2 — a field rename blanked the thinking pane

vLLM 0.27.x streams thinking as `delta.reasoning`. Earlier builds used
`delta.reasoning_content`, and that was the only name the client knew:

```python
r = delta.get("reasoning_content")     # 0.3.6 — matches nothing on 0.27.x
```

The blocking door had the same blind spot. So the one signal that would have explained the
wait — thousands of visible thinking tokens, arriving from 1.5 seconds in — was dropped on
the floor, and a long-but-healthy run became indistinguishable from a hang.

This is the failure mode that makes the other two expensive. With the pane working, the
budget problem is self-evident: you watch it think for six minutes and get cut off.

```python
def delta_reasoning(d):
    """The thinking text out of a delta or a message object, whatever this
    build of vLLM decided to call the field this month."""
    if not isinstance(d, dict):
        return ""
    return d.get("reasoning") or d.get("reasoning_content") or ""
```

Reading both names is not defensive clutter. An upstream that renames a field in a minor
release will do it again.

## Defect 3 — truncation was reported as success-with-nothing

`sse_events` detected truncation by a **missing** `data: [DONE]`, on the reasoning that a
connection dropped mid-generation is the only way a stream ends early.

`[DONE]` arrives after a truncated generation exactly as it does after a clean one. The
terminator says the stream ended, not that the generation completed — and `finish_reason`,
the field that distinguishes them, was never read.

`sse_events` now yields `("finish", reason)`, emitted **after** any text in the same chunk
so a caller that stops on it cannot drop the final tokens. A `length` finish becomes an
error naming the budget it hit and the knob that changes it:

> the model used all 8192 tokens thinking and never wrote an answer — raise Max tokens in
> Config, or set Thinking to off for a much faster reply

Critically it does **not** become a `done` frame. `done` is what tells the UI a prompt is
complete, worth appending a contract to and worth saving to history. A truncated
generation that arrives as `done` is a half-written prompt filed as a finished one.

## Added — a thinking toggle

`GAUNTLETX_ENABLE_THINKING`, and a **Thinking** control in the Config panel. Both are
**tri-state**, and unset is the meaningful default: it sends no `chat_template_kwargs` at
all and lets the model's own chat template decide. Absent is not the same as false.

Off answers the same brief in ~600 tokens and 29 seconds instead of ~15,000 tokens and 11
minutes. Whether it answers it *better* is an open question this issue does not settle —
the two outputs above are both well-formed, and no blind comparison has been run.

## The hypothesis that was wrong

Reading the model's own reasoning during diagnosis turned up this:

> Conflict: "Each harness gets ONLY its own closer, as the final sentence of this third
> paragraph … And stop there" But boundaries: "the last paragraph ends with the boundary
> sentence and the critic automatic-fail sentence." Which takes precedence? Need parse.

That is a genuine contradiction in `SYSTEM_PROMPT` — `BOUNDARIES` and the harness-closer
rule both claimed the final sentence of part 3 — and it is visibly where the model was
spending time. It is a satisfying root cause. It is also **not the cause.**

Removing boundaries entirely and rerunning reproduced the failure unchanged: still
`finish_reason=length`, still 8192 tokens, still zero content. The contradiction was real,
was fixed (boundaries second-to-last, closer always last), and would have been the wrong
fix to ship alone.

The lesson is not "don't read the reasoning" — reading it is what surfaced the
contradiction at all. It is that **a plausible cause found mid-investigation still needs
the test that would falsify it**, and here that test took one run.

## What this teaches

**A budget that fits the answer does not fit the thinking.** Sizing `max_tokens` against
observed reply length is correct for a non-reasoning model and catastrophic for a
reasoning one, because the visible reply is a rounding error on the total. The failure is
not a shorter answer; it is no answer.

**Timeouts and token budgets must move together.** Raising one alone converts a silent
failure into a different silent failure. Any change to either should be checked against
the wall-clock of the longest successful run, not against how long a user will wait.

**A terminator is not a completion.** `[DONE]`, exit code 0, HTTP 200 and "the connection
closed normally" all describe transport. None of them describe whether the work finished.
Where the protocol offers a separate completion signal — `finish_reason` here — reading
the transport signal instead is a bug waiting for a slow day.

**Absent is not false.** The thinking toggle is tri-state for the same reason the model
override is: collapsing "unset" into a default at the edge of the system removes the
caller's ability to say "you decide", and silently changes behaviour for everyone who
never touched the setting.

**Blank is worse than slow.** Two of these three defects were about feedback, not
function. The generation at 32768 tokens still takes eleven minutes — but it now shows
65,000 characters of thinking while it does, and nobody has to wonder whether it hung.
