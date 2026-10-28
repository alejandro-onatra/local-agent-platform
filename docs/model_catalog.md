# Hardware-aware local model catalogue

The owner requested a range: fast/light, balanced, and a more demanding reasoning
option that remains usable on the RTX 4060 Ti 16 GiB. The catalogue is
`config/llm/catalog.yaml`. The original Qwen entries are compatibility baselines,
not a claim that Qwen dominates other open-weight families. They pin official
Ollama manifests; separate cross-family candidates remain explicitly unlocked.
The catalogue does not install
weights, publish profiles, certify quality or enable automatic routing.

| Tier | Candidate | Approximate download | Initial context | Purpose |
| --- | --- | --- | --- | --- |
| Fast | Qwen3 4B Q4_K_M | 2.5 GB | 8192 | Short everyday tasks; thinking off |
| Balanced | Qwen3 8B Q4_K_M | 5.2 GB | 16384 | General agent work; existing installed model |
| Reasoning | Qwen3 14B Q4_K_M | 9.3 GB | 8192 | Candidate for harder tasks; thinking on |

A larger model is not automatically better on every task. File sizes are not
peak VRAM requirements. Validate model weights plus KV cache, desktop VRAM,
load time, generation speed and tool-call correctness before deployment. Keep
one model loaded and one inference request at a time, leaving at least 2 GiB
VRAM headroom during acceptance. These are proposed per-profile context limits;
the current Ollama service configuration is not changed by this catalogue.
Only Qwen3 8B was observed installed on October 26. No speed/quality ranking or
heavy-model GPU fit has been measured. New downloads and activation remain pending.
Cross-family evaluation is required before choosing the tier winners. Parameter
count, family label and vendor benchmarks alone do not establish a local ranking.

## Browser sessions and model setup

Each browser has its own Authentik cookies, Canvas backend registry, onboarding
completion and local health retry state. The same username reaches the same
personal instance, files and server-side profiles; it is not a new tenant per
browser. Signing out of one browser is not assumed to revoke every other session.

Pinned Canvas 1.26.0 deliberately shows onboarding for the launcher-seeded local
backend until that browser's completion flag is set, even if the server has a
usable LLM. Its provider `qwen` form is not our local Ollama profile. Do not save
an arbitrary remote model/API-key draft to dismiss onboarding. Skip the wizard
without saving and inspect the local `local-qwen3-8b` profile when the backend
is healthy. An active LLM profile and the active agent's LLM reference are
separate; verify both rather than assuming either is missing from the wizard.

## Diagnose connection before changing profiles

```bash
mise exec -- task household:models:check
```

This checks verified household containers, native `/api/settings` and `/server_info` at
18000, Canvas proxy for the same paths at 8000, saved Qwen and default agent reference, and
model relay discovery. It never returns keys, prompt data or custom settings,
never creates profiles and does not generate text. It distinguishes a healthy
backend from model/profile issues. Browser Authentik cookies and external HTTPS
fetches are separate checks; a redirect to login is not proof that the native
backend is stopped. Five failed browser probes can persist a disconnected state
until a retry/configuration refresh occurs. Native execution requires owner sudo.

Sources: [Qwen3 4B](https://ollama.com/library/qwen3:4b),
[Qwen3 8B](https://ollama.com/library/qwen3:8b),
[Qwen3 14B](https://ollama.com/library/qwen3:14b),
[installed Canvas onboarding logic](https://github.com/OpenHands/OpenHands/blob/3500d9e5c7cbdfb5a2cbfe9499ce4448eb10c0a2/src/components/features/onboarding/onboarding-host.tsx).


## Native diagnostic contract correction

The first diagnostic incorrectly prefixed server_info with `/api` and read the
frontend-normalized `llm_api_key_set` flag. SDK 1.53.0 uses root `/server_info`;
the native settings response contains `llm_api_key_is_set`, which Canvas renames
on the frontend. Earlier 4xx and false key flags from that diagnostic are not
evidence of an unavailable backend or missing credentials. The corrected check
uses exact native paths/fields and reports allowlisted HTTP status codes.


## Cross-family comparison candidates

| Candidate | Role to evaluate | Approximate download | Current decision |
| --- | --- | --- | --- |
| Phi-4 mini 3.8B | Fast/light general and tool tasks | 2.5 GB | Compare with Qwen3 4B |
| Mistral NeMo 12B | Balanced multilingual/general and tool tasks | 7.1 GB | Compare with the existing Qwen3 8B |
| Gemma 4 12B Q4 candidate | General/multimodal, tools and reasoning | 8.0 GB | Check Ollama/backend compatibility and GPU fit first |
| Qwen3.5 9B Q4 candidate | Updated general/multimodal and tool tasks | 6.6 GB | Compare with other families, not automatic replacement |
| GPT-OSS 20B MXFP4 | Experimental heavier reasoning | 14 GB | Not a default on a shared-display 16 GiB GPU; headroom unproven |

These are candidates, not installed/accepted profiles or a universal quality
ranking. Resolve exact backend/quantization/manifests before downloads. Vendor
family descriptions advertise tool/multimodal support; the specific runtime,
quantization and OpenHands adapter still require validation. File sizes are
rounded package sizes, not measured peak VRAM. GPT-OSS's documented low memory
footprint does not guarantee headroom for this desktop, KV cache and workload.

Compare warm/cold latency, generation speed, peak GPU/host memory, Spanish
answers with fixed acceptance criteria, tool-call correctness and completion of
small OpenHands tasks. Keep prompts, quantization/context/output budgets and
Ollama version recorded. Larger advertised context windows are not the local
configuration. Promote a winner per task/tier only after local acceptance; keep
auto-escalation off until routing and resource controls have their own tests.

Sources: [Phi-4 mini](https://ollama.com/library/phi4-mini),
[Mistral NeMo](https://ollama.com/library/mistral-nemo),
[Gemma 4](https://ollama.com/library/gemma4:12b),
[Qwen3.5](https://ollama.com/library/qwen3.5:9b),
[GPT-OSS](https://ollama.com/library/gpt-oss:20b).

### Local Qwen thinking control

Ollama 0.35.1's OpenAI-compatible endpoint maps `reasoning_effort: none` to
`think: false`. The native `think` field is not a field of its OpenAI chat request.
The initial household profile now uses `reasoning_effort: none`. Run
`task household:models:tune` to repair existing managed local profiles. The task
verifies runtime boundaries, preserves credentials in the container, and updates
active defaults only when Qwen was already selected. Existing conversation settings
are unchanged; start a new conversation to validate the corrected defaults.
This controls reasoning overhead; it does not establish end-to-end agent latency.
