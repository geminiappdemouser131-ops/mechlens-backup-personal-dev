# Model-adapter authoring checklist (loading_from_pretrained.py)

The repeatable unit of work. Every new HF model family that gets a HookedTransformer
weight-conversion table goes through this. Bram owns this area and can self-merge with
green CI; a cross-cutting helper (shared RoPE, an ActivationCache signature) needs a +1
from another core maintainer first (T5).

- [ ] Read the public HF `modeling_*.py`; draft `Adapters/<model>-arch.md`
      (attention flavor, norm type + eps placement, RoPE variant + theta, tied weights,
      activation, embedding scaling, quirks). Claude Max on the PUBLIC file only.
- [ ] Branch. Copy the closest existing adapter as the base (note which one).
- [ ] Fill the weight-conversion table entry: config field mapping, per-layer flags
      (local/global attn, RoPE-on/off), head_dim from config (never inferred).
- [ ] Map any NEW tensors explicitly (QK-norm, extra norms, routers if in scope).
- [ ] Write the acceptance test in `tests/acceptance/`: HF reference forward vs
      HookedTransformer forward, float32 logits match to 1e-4 absolute, smallest public
      checkpoint. Local 24GB box if it fits, else a RunPod spot pod.
- [ ] Update `docs/` supported-models list.
- [ ] Open the PR (code + docs + test together). Description states what the code does,
      never why any client wants it (T1).
- [ ] Green CI. Peer +1 if cross-cutting. Merge. Credit external contributors by handle.
- [ ] Add the family to `Adapters/adapter_support_matrix.xlsx` and the coverage CSV.

## Common silent-failure traps
- head_dim assumed = d_model // n_heads (LLaMA-4).
- QK-norm tensors dropped (Qwen-3).
- norm eps placed outside the rsqrt (Gemma-3, the 2.16.0 miss).
- input embedding scaling dropped (Gemma).
- MoE router treated as dense (LLaMA-4 Maverick, out of scope for first adapter).
