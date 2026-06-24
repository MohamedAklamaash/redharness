# redharness documentation

Hands-on guides for using and extending the harness. For the project's motivation,
methodology, and research grounding, see the [top-level README](../README.md).

| Guide | What it covers |
|---|---|
| [OVERVIEW.md](OVERVIEW.md) | What redharness is, the three threat surfaces, **installation, running an evaluation, reading the outputs, and using the leaderboard dashboard**. Start here. |
| [configuration.md](configuration.md) | The YAML config schema: top-level fields, run modes (jailbreak vs injection), plugin reference forms, worked examples per surface, and the output files. |
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

Everything runs fully offline, deterministically, with no API keys.
