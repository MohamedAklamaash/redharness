# redharness documentation

Hands-on guides for using and extending the harness. For the project's motivation,
methodology, threat model, and research grounding, see the
[top-level README](../README.md).

| Guide | What it covers |
|---|---|
| [OVERVIEW.md](OVERVIEW.md) | What redharness is, the three threat surfaces, and the hands-on basics: **installation, running an evaluation, reading the outputs, and using the leaderboard dashboard**. Start here. |
| [configuration.md](configuration.md) | The YAML config schema: top-level fields, run modes (jailbreak vs injection), plugin reference forms, worked examples per surface, the output files, and **live evaluation** against real models (`openai_compat`/`anthropic` adapters, the `pair` attack, the `strongreject` dataset + grader) with the `max_queries` spend budget. |
| [extending.md](extending.md) | A copy-pasteable example for adding a **custom Target, Attack, Dataset, Judge, Metric, Injection, and Scenario**, plus authoring behaviors/probes and injection scenarios as data. |
