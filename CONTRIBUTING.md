# Contributing to redharness

Thanks for your interest in extending redharness. The harness is a research
instrument, so contributions are held to two non-negotiable standards: the
**offline core stays dependency-free and importable with zero extras**, and
**no harmful corpora or real attack strings are ever committed**. Everything
below follows from those two rules.

## Adding a plugin

Every axis (target, attack, dataset, judge, metric, injection, scenario) is a
plugin resolved by name from a YAML config. To add one you write a small class
(or function), register it with the axis decorator, import it so the registry is
populated, and reference its name in a config. The complete, copy-pasteable
recipe for each axis lives in [`docs/extending.md`](docs/extending.md); read it
first. Confirm registration with:

```bash
uv run redharness list
```

## Project rules

### 1. Never commit harmful corpora or real attack strings

Real benchmark behavior sets (AdvBench, HarmBench, JBB-Behaviors, StrongREJECT,
XSTest, OR-Bench, ...) are **fetched by reference**, never vendored:

- A dataset loader subclasses `RemoteDataset`. The shipped `DEFAULT_URL` is an
  **inert placeholder**: its commit segment is the obvious sentinel
  `REPLACE_WITH_VERIFIED_COMMIT_SHA` (not a real SHA), and the committed `sha256`
  is the self-evident placeholder `"0" * 64`. Before enabling the download the
  operator **MUST pin both** a verified commit-SHA source URL **and** its matching
  `sha256`. The download is **opt-in** (`allow_download=True`) and the content is
  **hash-verified** before any row is yielded, so the placeholder hash fails closed:
  no silent fetch can succeed against the default URL.
- Tests use **synthetic `file://` fixtures** with `PLACEHOLDER`-style harmless
  text (see `tests/test_strongreject.py` and `tests/test_benchmark_datasets.py`).
  No real prompt ever enters the repository, a fixture, or CI.
- The same applies to injection/leakage corpora: only benign sentinels
  (`attacker@evil.example`, `CANARY-...`, `*.example.invalid` PII) are bundled.

### 2. Lazy-import heavy dependencies behind an optional extra

`src/redharness/plugins.py` eagerly imports every plugin submodule at core load,
so a single module-level `import torch` would break `import redharness` for
everyone. Therefore:

- A heavy dependency (`torch`, `transformers`, `garak`, `pyrit`, ...) is imported
  **lazily inside a method body**, never at module top — mirror
  `targets/_http.py::load_httpx`.
- The dependency is declared as a coarse **optional extra** in `pyproject.toml`
  (`gcg`, `garak`, `pyrit`, ...), and a missing install raises a **typed, helpful
  error** naming the extra (see `attacks/external/gcg.py` and the other
  scaffolds), never a bare `ImportError` deep in a call stack.

### 3. Keep the offline core dependency-free

The offline core imports and runs with only the base dependencies. CI proves this
with `tests/test_offline_imports.py`, which asserts `import redharness.plugins`
succeeds and that none of `{torch, transformers, boto3, vllm, garak, pyrit}` are
in `sys.modules` afterwards. Do not add a heavy dependency to the core or `dev`
extras, and do not import one at module scope.

### 4. No code comments; clean, modular code

Code is documented with module/class/function docstrings, not inline `#`
comments. Functions do one thing, carry type hints, raise typed errors, and stay
deterministic offline (no wall clock, no unseeded randomness). New runnable code
ships with offline-deterministic tests (`httpx.MockTransport`, injected
`ReferenceTarget`s, synthetic `file://` fixtures, no network).

## Per-dataset license / provenance

Datasets are fetched from their canonical source and **used in place, not
redistributed**. The committed loaders carry placeholder source URLs (the
`REPLACE_WITH_VERIFIED_COMMIT_SHA` sentinel commit) and placeholder hashes
(`"0" * 64`); operators pin a verified commit-SHA URL and supply the verified
`sha256` at runtime. Respect each upstream license:

| Dataset | Source | License | Use |
|---|---|---|---|
| AdvBench | github.com/llm-attacks/llm-attacks (`data/advbench/harmful_behaviors.csv`) | MIT | fetch, not redistribute |
| HarmBench | github.com/centerforaisafety/HarmBench (`data/behavior_datasets`) | MIT | fetch, not redistribute |
| JBB-Behaviors | github.com/JailbreakBench/jailbreakbench (`JBB-Behaviors`) | MIT | fetch, not redistribute |
| StrongREJECT | github.com/alexandrasouly/strongreject | MIT | fetch, not redistribute |
| XSTest | github.com/paul-rottger/xstest | CC-BY-4.0 | fetch, not redistribute |
| OR-Bench | huggingface.co/datasets/bench-llm/or-bench | CC-BY-4.0 | fetch, not redistribute |

When adding a dataset loader, add a row here with its source URL, license, and the
fetch-not-redistribute note.

## Before you open a PR

```bash
uv run ruff check
uv run pytest --cov=redharness --cov-report=term-missing
uv run pytest tests/test_offline_imports.py    # the zero-extras tripwire
uv run redharness run configs/smoke.yaml
uv run redharness run configs/injection_smoke.yaml
uv run redharness run configs/leakage_smoke.yaml
```

All must pass. By contributing you agree your contribution is licensed under the
project's Apache-2.0 [LICENSE](LICENSE).
