# Weight-conversion acceptance test methodology

Every model-adapter PR ships with a weight-conversion test (policy, T5). No adapter
merges without it.

## The test
- Load the smallest PUBLIC checkpoint of the family in HF and in HookedTransformer.
- Run both forward on a fixed short prompt in float32.
- Assert max absolute logit delta <= 1e-4.
- Compare a handful of intermediate hook activations (resid_pre at layer 0, attn
  pattern at layer 0, final resid) as a secondary check.

## VRAM policy
- Prefer the local 24GB box. If the smallest useful checkpoint will not fit in float32,
  spin up a RunPod on-demand CUDA spot pod, run the test, save the log, kill the pod.
  [Non-project funding and receipt reference omitted from this public copy.]

## Interpreting failures
- A delta of 1e-3 or larger: structural (head_dim, missing norm/QK-norm, RoPE apply).
- A delta 1e-4 .. 1e-3: usually norm eps placement or embedding scaling (see Gemma-3).
- A delta just under 1e-4 that drifts by prompt: nondeterminism / dtype; pin float32.

## Log retention
- Save each acceptance log; record pass/fail and the box (local vs RunPod) in the
  adapter matrix and `Releases/demo_sweep_results.csv`.
