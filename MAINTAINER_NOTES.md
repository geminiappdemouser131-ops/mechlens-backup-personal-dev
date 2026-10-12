# Release readiness gate

This small, standard-library CLI reads recorded project evidence. It does not load
models, import TransformerLens/torch, run CI, contact services, or change evidence.
The JSON audit and standalone HTML dashboard are generated from one audit object.

**An old green result does not establish readiness for the current release. Missing
evidence remains PENDING, not FAIL.** The config's `gates.ci: green` and
`gates.demo_notebook_sweep: green` specify the required state, not a dated candidate
execution or maintainer confirmation.

## Run and regenerate both outputs

From the repository root:

```bash
uv run --no-project --offline python release_gate/gate.py
```

This writes `release_readiness_audit.json` and `release_readiness_dashboard.html` in
the repository root. Open the HTML directly in a browser; it needs no server,
network, JavaScript, fonts, or adjacent files. Every metric has a text label. The
embedded audit contains the same data as the JSON file. Both are dated evidence
snapshots, not live release status. Regenerate after evidence changes.

Optional paths:

```bash
uv run --no-project --offline python release_gate/gate.py --root /path/to/repo --output-dir /path/to/output
```

Python 3.10+ and uv must already be installed. No `uv sync` is needed.

## Gate states and process exit codes

- PASS: the recorded requirement is satisfied.
- FAIL: evidence establishes a breach, contradictory candidate pass claim, failed
  sweep, or negative CI confirmation. Nonfinite/negative numerical errors are also
  rejected, rather than silently accepted.
- PENDING: required evidence is missing, unreadable, unsupported, incomplete, or
  cannot be tied to the configured release.

The top-level decision is READY only if every gate is PASS. Otherwise it is
NOT_READY. Exit code 0 means READY; exit code 1 means at least one candidate gate
FAIL; exit code 2 means NOT_READY with pending evidence and no failed candidate
gate. Nonzero exits are expected for the supplied evidence and do not mean that
output generation failed. Historical FAIL findings do not automatically fail the
current candidate. Filesystem write errors are operational errors, not gate states.

## Checks

1. All eleven specified files are present and readable; provenance records their
   folder paths and SHA-256 hashes of the public copies.
2. Target release is read from `Configs/release_config.yaml`, `next.version`.
3. Candidate float32 acceptance results cover every family in the historical
   suite. Each maximum absolute logit error must be finite, nonnegative and at most
   `1e-4`. Exactly `1e-4` passes. No averages and no tolerance inferred from a pass flag.
4. Candidate summaries and case flags agree with recorded measurements and the
   incident evidence. The old 6/6 JSON is retained unchanged. Its historical
   all-pass summary is flagged against the longer-prompt breach in the triage note.
5. Candidate Gemma-3 evidence includes the longer prompt and an intermediate
   measurement with an explicit positive tolerance.
6. Demo CSV rows must match the target release, report green, run a positive number
   of notebooks, and have all notebooks passing with zero failures. Earlier rows
   are displayed only as history.
7. Explicit CI confirmation must match the target release and record its author
   and evidence reference. The original files contain no v2.17.0 confirmation.

The supplied records produce NOT_READY for v2.17.0: candidate acceptance,
consistency, Gemma-3 regression, demo sweep and CI confirmation are PENDING.
The historical Gemma measurements are 3.9e-5 on the short suite prompt,
approximately 1.3e-4 on the longer prompt (FAIL), and approximately 2.9e-5 after
repair in v2.16.1. These are reported measurements, not newly executed tests.

## Evidence format and future updates

All eleven original paths are listed in `release_gate/gate.py:PATHS` and in the
output provenance. The fixed historical JSON remains an input. For a new target,
the CLI additionally looks for `Configs/acceptance_test_output_v<VERSION>.json`.
That file is listed separately under candidate evidence, including when absent.
Copy real results only; never fabricate confirmation or measurements to clear a gate.

Candidate JSON uses the existing format: `release`, `dtype: "float32"`, a
`results` list containing `family`, `checkpoint`, `max_logit_delta`, and boolean
`pass`, and a `summary` with `total`, `passed`, and `failed`. Add a Gemma-3 result
with `case: "longer_prompt"` and a top-level `gemma3_intermediate_check` mapping
with numeric `max_absolute_delta` and `tolerance`. The intermediate tolerance must
be chosen and reviewed by maintainers; the CLI does not invent it. Summary counts
must include all cases. This is evidence validation, not independent verification
that reported runs really occurred or that their test design is sufficient.

Record an actual CI confirmation in the existing config using this shape (the
values below are placeholders, not confirmation):

```yaml
ci_confirmation:
  release: "<target version>"
  status: "<green or red>"
  confirmed_by: "<maintainer>"
  evidence: "<public CI run or confirmation reference>"
```

The dependency-free config reader supports the supplied inline `next: { version:
"...", date: "..." }` syntax and indented scalar mappings for `next` and
`ci_confirmation`. It is deliberately not a full YAML parser: nested structures,
tags, anchors, commas inside inline scalar values, and multiline values are not
supported. Unrecognized required mappings leave the relevant gate PENDING.

The Markdown incident reader extracts the supplied note's labelled symptom and
resolution measurements. It does not interpret arbitrary prose or automatically
classify new incidents. Changed formats need a reviewed parser update. All open
issues are not automatically blockers: this CLI implements the agreed gate scope,
not a general bug triage engine. Repository context is an implementation snapshot,
not a network query. Candidate commit identity is not independently verified by
these legacy evidence files.

## Non-blocking issue disposition

Bram explicitly designated #1108 as non-blocking for this gate. Its current status
is read from `Notes/issue_triage_queue.csv` and displayed, with that disposition,
in both outputs. This is not a claim that the issue is fixed. It never holds the
gate. #1121 is recorded as closed in v2.16.1; its historical failure remains visible.

## Run the tests with uv

```bash
uv run --no-project --offline python -m unittest discover -s release_gate -p 'test_*.py' -v
```

Both the CLI and its unittest suite live in `release_gate/`, outside `tests/`.
Unittest does not load pytest `tests/conftest.py`; `--no-project` prevents project
dependency syncing. Tests use temporary copies of the evidence and synthetic
candidate records, never models. The implementation was validated with one run:
10 tests passed. Full project/model tests were not run, as requested.

## Branch and publication context

The fork is `geminiappdemouser131-ops/mechlens-backup-personal-dev`. Before this work,
the observed branches were only `main` and `gh-pages`; there was no `dev` branch.
`release-readiness-gate` was created from `main` at
`33387b7def1ead3a8cba532a729da5599e875873`, following Bram's explicit instruction.
No PR was opened and nothing was merged. These facts are recorded in
`release_gate/repository_context.json` and copied into the audit and dashboard.
The upstream AGENTS.md defaults to dev and full-project checks; this task's explicit
main-base, no-PR, standalone/offline validation instructions govern this work.

## Public evidence scope

Only the eleven specified project evidence files were imported. No consulting
records, financial records, private advisory, private account links or credentials
were copied. One nontechnical funding/receipt reference was omitted from the public
copy of `Adapters/acceptance_test_notes.md`, with a visible omission marker and
provenance note. Its numerical methodology is unchanged. Generic public release
policy language is preserved. The original acceptance JSON is unchanged. Input
files remain read-only at runtime; the CLI writes only the two named outputs.
