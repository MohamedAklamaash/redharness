# redharness documentation

Hands-on guides for using and extending the harness. For the project's motivation,
methodology, and research grounding, see the [top-level README](../README.md).

| Guide | What it covers |
|---|---|
| [OVERVIEW.md](OVERVIEW.md) | What redharness is, the three threat surfaces, **installation, running an evaluation, reading the outputs, and using the leaderboard dashboard**. Start here. |
| [configuration.md](configuration.md) | The YAML config schema: top-level fields, run modes (jailbreak vs injection), plugin reference forms, worked examples per surface, the output files, and **live evaluation** against real models (`openai_compat`/`anthropic` adapters, the `pair` attack, the `strongreject` dataset + grader) with the `max_queries` spend budget. |
| [extending.md](extending.md) | A copy-pasteable example for adding a **custom Target, Attack, Dataset, Judge, Metric, Injection, and Scenario**, plus authoring behaviors/probes and injection scenarios as data. |

## TL;DR

```bash
uv venv && uv pip install -e '.[dev]'

uv run redharness run configs/smoke.yaml             # jailbreak
uv run redharness run configs/injection_smoke.yaml   # prompt injection
uv run redharness run configs/leakage_smoke.yaml     # data leakage

uv run redharness list                               # every registered plugin by axis

uv pip install -e '.[dashboard]'                     # optional: the Streamlit dashboard
uv run redharness dashboard                           # launches Streamlit at http://localhost:8501
```

Everything above runs fully offline, deterministically, with no API keys.

To evaluate a **real** model (your keys, your cost), install the live extras and use the
`pair` attack + `strongreject` dataset/grader behind a `max_queries` budget — see the
**Live evaluation** section of [configuration.md](configuration.md):

```bash
uv pip install -e '.[openai,anthropic]'
uv run redharness run configs/real_eval.example.yaml   # set env keys + budget first
```
