# Issue 003 — the guard was present, called, reported, and wrong

**Status: RESOLVED in v0.3.6** · Raised 2026-08-10 · Closed 2026-08-10

A run satisfied `BASELINE_CONTRACT` to the letter and produced a meaningless result
anyway. This is the most instructive failure in the set, because the defence built after
issue 001 was in place and did nothing.

---

## What was reported

> Best accuracy: 0.625 (beat constant predictor **0.0**, random 0.25)
> Most rounds achieve 0.33–0.45 accuracy
> **All results beat the constant predictor baseline**
> No train/eval overlap (strictly enforced)

Read as a report, that is exactly what the contract asked for: a model score, a constant
predictor, a random predictor, and an overlap check. It looks like rigour.

## The bug

`eval/harness.py`:

```python
def compute_constant_predictor_scores(eval_data):
    labels = [d['label'] for d in eval_data]
    most_common = Counter(labels).most_common(1)[0][1]   # ← [1] is the COUNT
    correct = sum(1 for l in labels if l == most_common)
    return correct / len(labels)
```

`Counter.most_common(1)[0]` returns a `(label, count)` tuple. Taking `[1]` yields the
**count**, which is then compared against the labels themselves.

On the 42-item holdout:

```
label distribution        : {0: 11, 1: 5, 2: 13, 3: 5, 4: 8}
most_common(1)[0]         : (2, 13)
their code takes [1]      : 13          ← compared against labels 0-4
their constant predictor  : 0.000       ← the 0.0 that was reported
CORRECT constant predictor: 0.310
```

Nothing can equal 13, so the baseline is always `0.0`, and **"beat the constant
predictor" is vacuously true for any model whatsoever.**

## What the real numbers were

| Claim | vs reported 0.0 | vs real 0.310 |
|---|---|---|
| Best round, 0.625 | "beats it" | genuinely beats it |
| Typical round, 0.33–0.45 | "beats it" | 0.33 barely clears; 0.40 is +0.09 |

The best round survives. The typical round goes from "comfortably ahead of baseline" to
"marginally above chance" — a materially different report.

## Why this is worse than having no guard

| Run | Guard | Outcome |
|---|---|---|
| 001 | absent | meaningless 100%, no baseline cited |
| 003 (this) | **present but wrong** | meaningless comparison, **cited as evidence of rigour** |
| — | present and correct | honest 0.10%, round correctly failed |

An absent guard leaves an obvious hole. A broken guard **manufactures confidence**. The
report was more persuasive precisely because it contained a baseline comparison.

## Root cause in the contract, not the code

`BASELINE_CONTRACT` was worded as a property of the artifact — deliberately, because
behavioural clauses get dropped (see issue 001):

> The evaluation harness must **print**, on the same line as any score it reports: the
> model's score, the score of a constant predictor…

It printed all of them. **Nothing required the numbers to be correct.** The contract
specified the *shape* of the output and not a single property of its *value*.

That is the generalisable lesson: an artifact requirement is only as good as the
properties it asserts about the artifact. "Print X" is satisfiable by printing a wrong X.

## Resolution — v0.3.6

`BASELINE_CONTRACT` now asserts a checkable property of the value, not only its presence:

> Sanity-check the baselines before trusting any score: a constant predictor that returns
> zero on a multi-class evaluation set is a bug in your harness, not a good result, and a
> constant predictor must never score below the least frequent class's share. Validate it
> against a case whose answer you have worked out by hand, and print the label
> distribution beside every score so a collapsed or degenerate metric is visible.

Two properties, both machine-checkable by the agent itself:

1. **A constant predictor cannot be 0.0** on a multi-class set — it must equal the most
   frequent class's share, which is at least `1/num_classes`.
2. **Hand-validated against a known case**, so an index error surfaces immediately.

## Secondary findings from the same run

- **Classification again.** `model/classifier.py`, `MLPClassifier`, target `item['label']`
  — the domain tag, not answer text — despite the brief stating that classifying the
  domain must never be the headline score. Third run of four to substitute the easier task.
- **Synthetic corpus.** `data/corpus_generator.py` generated its own training questions
  where the brief called for researched material. Questions you invent are not domain
  knowledge.
- **What held:** the provided 42-item holdout was untouched, and the overlap check was
  genuinely implemented and genuinely zero.

## The lesson in one line

**A guard that reports is not a guard that checks.** Specify a property of the value, not
just the presence of a field — and prefer properties the agent can verify without you.
