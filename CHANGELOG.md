# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

## [0.1.0] — 2026-06-26

First tagged release. A standardized, reproducible benchmark for the adversarial robustness of
LLMs across three threat surfaces, with a fully offline/deterministic core and opt-in live
evaluation.

### Harness
- Pluggable `Attack × Target × Dataset × Judge × Metric` matrix (plus `Scenario`/`Injection`
  axes for agentic prompt injection), resolved by name from declarative YAML via a typed registry.
- Three surfaces: jailbreak, prompt injection (direct + indirect/agentic), data leakage
  (extraction, canary, PII, system-prompt).
- Reproducibility contract: hash-pinned datasets, deterministic seeded execution, JSONL
  transcripts, and a `(dataset_version, judge, metric)` provenance triple on every result.
- Markdown/HTML reports, a `leaderboard.json` export, and an aggregating Streamlit dashboard.

### Attacks, judges, datasets
- Attacks: `static`, `template`, and the multi-turn `pair` (Chao et al. 2023), `tap`
  (Mehrotra et al. 2023), `crescendo`; `gcg`/`garak`/`pyrit` registered as scaffolds.
- Judges: `refusal_match`, a StrongREJECT-style `rubric` and a faithful `strongreject` grader,
  `injection_detector`, `leak_detector`, and a generic `hf_classifier` (Llama Guard family, opt-in).
- Datasets: bundled synthetic sets plus opt-in, sha256-pinned, SSRF-hardened loaders for
  AdvBench, HarmBench, JailbreakBench (JBB-Behaviors), XSTest, and OR-Bench. No corpora committed.

### Live evaluation
- Hardened `openai_compat` and `anthropic` adapters (shared httpx transport, retry/backoff,
  typed errors, env-only credentials, tool-calling), behind optional extras.
- Fail-closed `max_queries` budget counting real HTTP calls; normalized `token_usage`/`cost`
  metrics; opt-in bounded concurrency (`--concurrency`).

### Research tooling
- `redharness judge-agreement` — re-score a run's transcripts across judges; per-judge ASR,
  pairwise agreement, and Cohen's κ.
- Bootstrap confidence intervals on rate metrics and multi-seed trials (`--trials`).

### First real result
- Committed worked example (`results/real_eval_v1`): `claude-haiku-4-5` on AdvBench/XSTest —
  static `asr 0.0` → PAIR `asr 0.15` (StrongREJECT) vs `1.0` (string-match), a live reproduction
  of StrongREJECT's judge-sensitivity finding.

### Quality
- Apache-2.0 licensed; CI runs ruff, mypy (typed, `py.typed` shipped), pip-audit, the full test
  suite (~98% coverage), an offline-import guard, and three offline smoke evals.
