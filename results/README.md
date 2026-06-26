# Worked results — `real_eval_v1`

The first real-model evaluations produced by this harness, kept as committed evidence that
the pipeline reproduces published behavior. Target: **`claude-haiku-4-5`** (Anthropic).
Attacker/grader where applicable: **`gpt-4o-mini`** (OpenAI). Datasets are commit-pinned and
sha256-verified (AdvBench, MIT; XSTest, CC-BY-4.0). Raw leaderboards are alongside this file.

| Run | Dataset · attack · n | Headline | Reading |
|---|---|---|---|
| `advbench_static` | AdvBench · static · 50 | `asr 0.0`, `refusal_rate 1.0`, $0.015 | An aligned model refuses 100% of *direct* harmful requests — the undefended baseline the GCG/PAIR papers begin from. |
| `advbench_pair` | AdvBench · PAIR · 20 | `asr` **0.15** (StrongREJECT) / **1.0** (refusal_match), $0.009 | static≈0 → PAIR≫0: the attack genuinely jailbreaks **through the harness**. |
| `xstest_frr` | XSTest · static · 50 | `frr 0.0`, `refusal_rate 0.24`, $0.045 | No over-refusal of safe prompts; the 24% refusals were the unsafe `contrast_*` twins (correctly refused). |

## Fidelity gate

- **Static baseline matches the literature** — direct AdvBench requests are refused (`asr 0.0`).
- **PAIR reproduces the jailbreak effect** — ASR climbs well above the static baseline once
  the attacker LLM iterates, confirming the attack works end-to-end through redharness, not
  just mechanically.

## Judge sensitivity (the headline)

On the **same 20 PAIR transcripts**, two judges disagree sharply:

| Judge | `asr` | `strongreject_score` |
|---|---|---|
| `refusal_match` (string heuristic) | **1.00** | 1.00 |
| `strongreject` (rubric grader, `gpt-4o-mini`) | **0.15** | 0.019 |

The regex judge reports a **~6.7× higher** attack-success rate than the rigorous rubric
grader — a live reproduction of StrongREJECT's central finding [Souly et al. 2024] that weak
judges overestimate jailbreak success. This is exactly the ambiguity the harness's
`(dataset_version, judge, metric)` provenance triple is designed to surface, and the
`redharness judge-agreement <run-dir>` command quantifies it (per-judge ASR + Cohen's κ).

## Reproduce

```bash
uv pip install -e '.[openai,anthropic]'
export OPENAI_API_KEY=...  ANTHROPIC_API_KEY=...
export SSL_CERT_FILE="$(uv run python -m certifi)"   # macOS; or the certifi-hardened loader handles it
uv run redharness run configs/advbench_static.yaml
uv run redharness run configs/advbench_pair.yaml
uv run redharness run configs/xstest_frr.yaml
uv run redharness judge-agreement runs/advbench_pair_haiku --judge refusal_match --judge strongreject
```

Numbers from stochastic live models are single-sample point estimates; see the multi-seed /
bootstrap-CI options in [`docs/configuration.md`](../docs/configuration.md) for interval
estimates.
