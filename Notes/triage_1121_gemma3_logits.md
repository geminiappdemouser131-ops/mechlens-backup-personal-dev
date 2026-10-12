# Triage note: issue #1121 (Gemma-3 logits do not match HF) POST-RELEASE

- Filed: 2026-06-26 by a user, inside the 48h monitoring window after v2.16.0.
- Severity: adapter correctness regression (the went-badly case; recorded honestly).

## Symptom
- Gemma-3 HookedTransformer logits diverged from HF by ~1.3e-4 max absolute, over the
  1e-4 acceptance threshold. The acceptance test in v2.16.0 had passed on a prompt where
  the error stayed just under threshold; a longer prompt exposed it.

## Root cause
- norm-epsilon placement in the Gemma-3 conversion table. Gemma applies RMSNorm as
  (1 + weight) * x with eps INSIDE the rsqrt; the v2.16.0 table put eps outside.

## Resolution
- Fixed the eps placement; strengthened the acceptance test with a longer prompt and a
  tighter intermediate-activation check. Max delta back to 2.9e-5.
- Cut v2.16.1 hotfix 2026-06-27; published to PyPI; advised users to upgrade. The miss
  is noted accurately in the release tracker (not hidden, T6).
