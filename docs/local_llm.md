# First local inference — Ollama + Qwen3 8B

## Decision and scope

Use Ollama 0.35.1 in Docker and `qwen3:8b` Q4_K_M as initial inference and tooling test. The model occupies approximately 5.23 GB of download. With 16 GB of VRAM and initial context of 8192 tokens is a conservative selection; its actual consumption and performance will be measured on the host.

Qwen3 8B is a first technical reference, not a guarantee of quality for long OpenHands tasks. The model page declares tool support and Apache 2.0 license. The MIT license of the repository does not change the licenses of Ollama, models or other components.

## Preparation

From a normal host terminal:

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
export PATH="$HOME/.local/bin:$PATH"
mise install
mise exec -- task llm:plan
mise exec -- task llm:setup
```

`llm:setup` validates the repository and Compose, starts Ollama, waits for its healthy state, downloads the model, checks its digest and runs inference tests. Docker explicitly uses the context `default`, to avoid a Docker Desktop or accidentally configured socket. It may ask for sudo to access the Engine; the script does not modify groups or privileges.

The first run downloads the Ollama image and about 5.23 GB of weights. Check storage space in Docker, not just in CloudDrive. The script attempts to verify it and warns if it cannot read that path. It does not remove other models or volumes.

## Security and persistence

- API: `http://127.0.0.1:11434`; published only in loopback, without authentication. Local processes can use it.
- Cloud functions disabled via `OLLAMA_NO_CLOUD=1`. This is not a network restriction: the service needs outgoing to download weights.
- GPU 0 reserved, a loaded model and a parallel request, initial context of 8192.
- RAM memory limits of 12 GB and 8 CPU; they do not equate to limiting VRAM. If memory is lacking, check the logs before increasing limits.
- No Docker socket or personal folders mounted in Ollama; capabilities are removed and elevation of privileges is prevented.
- Weights saved in the Docker volume `agent-platform-local_ollama-data`, outside the repository and CloudDrive synchronization.
- `llm:down` preserves the weights. The service uses `unless-stopped`; it resumes with Docker if not explicitly stopped.
- Docker logs have rotation. Do not introduce sensitive information until the entire data policy has been reviewed.

## Pinned versions

`infra/llm/versions.yaml` preserves version and Linux amd64 digest of Ollama, model manifest digest and test options. Compose fixes the image by digest.

The model tag is downloaded via Ollama and compared with the expected digest. If the upstream modifies the tag, the process fails before inference; it does not automatically update the lock. We do not guarantee eternal availability of the pinned tag. To preserve a reproducible copy, save the weights and their manifest in the volume or a reviewed backup.

The weights are verified via Ollama's download mechanisms; the additional script verifies the identity of the installed manifest.

## What checks llm:check

1. Server version and installed model digest.
2. Generation of a correct JSON response to a synthetic sum, completed without truncation.
3. Model loaded with `size_vram > 0` according to `/api/ps`. Demonstrates GPU assignment, not that all layers are on GPU nor constitutes a sustained load test.
4. A synthetic call `add(a=2, b=3)` with correct arguments; does not execute tools or external actions.
5. A valid and non-truncated response from `/v1/chat/completions`.
6. Tokens/second calculated with `eval_count / eval_duration`, which exclude the initial load. The historical field `generation_seconds` contains the total time; `token_generation_seconds`, `model_load_seconds` and `prompt_processing_seconds` are added to distinguish phases. It is a short sample, not a comparable benchmark.

The test uses only synthetic data. Saves summaries of status, version, digest, times and VRAM in `artifacts/diagnostics/llm-*.json`; does not save prompts, responses or reasoning. The report does not yet validate full compatibility or OpenHands quality.

## Operation and diagnosis

```bash
mise exec -- task llm:status
mise exec -- task llm:check
mise exec -- task llm:logs
mise exec -- task llm:down
# Reanudar conservando pesos:
mise exec -- task llm:up
# Comprobar host y modelo:
mise run env:check
mise exec -- task llm:check
```

- **sudo blocked in Work:** run from the normal host terminal.
- **Port 11434 occupied:** check existing service; it is not stopped automatically nor the port changed silently.
- **Different digest:** check upstream change and update configuration explicitly; do not ignore the control.
- **No VRAM or CUDA error:** check host and Docker/GPU and review service logs. Do not reinstall the driver without diagnosis.
- **Invalid response/call:** infrastructure and quality are separate controls; register the failure and evaluate model/options before OpenHands.
- **Timeout:** check memory and loaded model; each inference request has a timeout of 600 seconds and is not retried automatically.

## Validation status

Availability of the image and model manifest, shell syntax, Compose configuration and consistency with the lock were verified. The validators' tests use fixtures and check real failures like drift, CPU-only, truncation and incorrect calls.

The user ran `task llm:setup` from the host and shared a satisfactory result on October 5, 2026: correct version and digest, JSON generation, GPU residency, synthetic call and compatible API verified. The report has a UTC timestamp of October 4 at 22:16, equivalent to October 5 at 00:16 in Europe/Berlin.

The following 0.78 tokens/s, 10 tokens generated, 68.809 total seconds, and 6,295,440,588 bytes of VRAM allocated (approximately 5.86 GiB) were observed. The functional test passed; performance requires diagnosis. The speed uses only `eval_duration`, so it cannot be solely attributed to initial load. The percentage of layers on GPU has not been verified yet.

Before OpenHands, repeat the test and consult the CPU/GPU distribution immediately after, while the model is still loaded:

```bash
mise exec -- task llm:check
mise exec -- task llm:status
mise exec -- task llm:logs
```

Share these results for reviewing times, `PROCESSOR` and backend CUDA. Do not change driver, model, or limits without evidence. The original report remains in `artifacts/diagnostics/llm-y546ryve.json` on the host; this state is based on the output shared by the user.

## Second Validation — October 5, 2026

The user shared a new host execution at 07:49 UTC (09:49 Europe/Berlin), with all controls satisfactory:

| Metric | Result |
| --- | --- |
| Generation via API | 38.07 tokens/s; 10 tokens |
| Total time of the first request | 3.565 s |
| Model loading | 3.153 s |
| Prompt processing | 0.148 s |
| Token generation | 0.263 s |
| VRAM allocated | 6,295,440,588 bytes, approximately 5.86 GiB |
| Distribution shown by `ollama ps` | 100% GPU |
| Context loaded | 8192 tokens |
| Synthetic call and API compatibility | Verified |

The container appears healthy. The logs show HTTP requests 200 and internal generation speeds of approximately 34–45 tokens/s across the three requests. The internal rate of the runner and the rate calculated using the API counters use different counting conventions; equality between the two is not required.

The slowness of 0.78 tokens/s from the first execution did not reproduce. These logs do not explain the cause; it is not conclusively attributed to initial load, driver, or CPU. No changes to the driver or limits are required with the current evidence.

Original report on the host: `artifacts/diagnostics/llm-eofbwzvb.json`. This record is based on the shared output, not on an execution from Work. These are short and synthetic tests; they still do not demonstrate sustained performance, quality of complex tasks, or full compatibility with OpenHands.

The inference infrastructure is ready for the next phase: integrating OpenHands and running a small demonstration task in a dedicated workspace. Keep the model and context current as an initial reference and evaluate separately the needs of context and agent quality.

## Sources

- [Ollama in Docker](https://docs.ollama.com/docker)
- [Qwen3 8B: size, capabilities, and license](https://ollama.com/library/qwen3:8b)
- [API generate](https://docs.ollama.com/api/generate)
- [API chat](https://docs.ollama.com/api/chat)
- [Loaded models and VRAM](https://docs.ollama.com/api/ps)
- [Ollama local-only and configuration](https://docs.ollama.com/faq)

## Context Change for the Agent

After the first tool usage failure in OpenHands, the server's context of 8192 was expanded to 32768 tokens, preserving the model's identity. The previous measures correspond to 8192 and should not be treated as a benchmark of the new context. Applying the change requires restarting via `task openhands:up`; the new consumption and agent behavior are pending verification.
