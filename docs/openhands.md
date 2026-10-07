# OpenHands local — first experience with Agent Canvas

## Version selection

On October 5, 2026 the official repository publishes Agent Canvas 1.24.0 as a stable release. The old Local GUI appears as a deprecated project in the documentation. The official all-in-one image of Agent Canvas is used, which includes Agent Server 1.49.6 and Automation 1.15.1. The frontend continues to run the OpenHands agent; no cloud provider is needed.

Linux amd64 image pinned by digest in `infra/openhands/versions.yaml`; approximately 1.40 GB compressed. The digest identifies the entire image and its components. Node and the OpenHands Python runtime are inside the image. The host Python, pinned by mise, is only used for the configuration and validation scripts of the repository. mise maintains Task and Python; go-task coordinates and `scripts/openhands/` implements.

## Startup

From the normal host terminal:

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
mise exec -- task openhands:setup
```

The task checks Ollama and its inference, downloads the image, creates the workspace, and starts the container. It may request sudo to access Docker. It applies a second compose file to the project `agent-platform-local`, preserving the existing weights volume. It may recreate Ollama to connect it to the internal network; do not run it during another inference.

At the end, open **http://127.0.0.1:8000/canvas**. The check verifies HTML HTTP 200 and the DNS/API route from OpenHands to Ollama, as well as the model digest. It does not yet test an agent conversation.

## Configure the model in the interface

In Settings / LLM Profiles, create and activate the profile `local-qwen3-8b`. Use advanced options if the model does not appear:

| Field | Value |
| --- | --- |
| Custom model | `openai/qwen3:8b` |
| Base URL | `http://ollama:11434/v1` |
| API key | `local-only` (placeholder, not a real secret) |

The prefix `openai/` selects the compatible client; the weights continue to run on Ollama. Inside the container `localhost` points to OpenHands, hence the DNS name `ollama` is used. Save and activate the profile before creating the conversation. Do not select subscriptions, cloud provider, or enter GitHub credentials in this test.

The initial context of 8192 tokens was used for the inference test; it has been expanded to 32768 to test OpenHands. If the form allows input/output limits, avoid values greater than the available context and start with output of 1024 tokens. An agent incorporates instructions and tool descriptions; the context must also cover the agent's instructions and tools. Evaluate context errors and quality before increasing memory or changing the model.

Disable analytics/product telemetry consent in the interface. Agent Server has exporter `none` and consent denied. The image includes a frontend with analytics compiled: the internal network of the container does not control the requests that the browser makes. No claim is made about the absence of browser telemetry without additional verification.

## First demo task

Select the OpenHands agent and the folder `/projects/demo` (the default path is also configured there). If the interface asks for execution or approval, review the commands and activate manual confirmation when it is available. The platform's own approval policy is not yet implemented.

Send this task:

> Work only in /projects/demo. Create sum.py with an add(a, b) function and test_sum.py with unittest. Include tests for positive integers, negatives, and zero. Run python -m unittest -v and summarize the results. Use only the standard library, without downloading dependencies or accessing the Internet. Do not modify other files.

Check that the two files appear in `artifacts/openhands/projects/demo/`, that the tests pass, and that the conversation ends. A sum is a test of tools and execution, not a representative evaluation of complex programming. Save a summary of the results without copying personal prompts, secrets, or full conversations to Git.

## Access, persistence, and limits

- UI published only in `127.0.0.1:8000`. Session API and encryption key are generated and preserved in the volume `agent-platform-local_openhands-state`; they are not printed nor added to the repository.
- Only `artifacts/openhands/projects` is mounted as `/projects`. The full repository, HOME, SSH keys, or Docker socket are not mounted. That folder is inside CloudDrive: any file from the demo can be synchronized; use only synthetic data.
- The image runs as a non-root user. The host user's primary group is added, and the two folders are created with mode 2770. No recursive chown or changes to the host's groups are made. Startup verifies the real permissions of the container.
- OpenHands uses exclusively a shared internal Docker network with Ollama; it has no direct Internet access. Ollama preserves its download network and loopback port. This does not protect against a service vulnerability nor prevent browser traffic.
- 6 GB RAM, 4 CPU, maximum 512 processes, no Linux capabilities, and no privilege escalation. The agent can run commands inside its container, modify the workspace, and access its own state; the state is not an immutable audit.
- No automations or connectors are enabled in this phase. The Automation component is included in the image, but no recurring jobs are created. The integrated editor is disabled for this test.
- OpenHands does not receive GPU: Ollama is the service that uses it. It does not restart automatically on Docker startup; it is started explicitly.

## Operation and issues

```bash
mise exec -- task openhands:plan
mise exec -- task openhands:status
mise exec -- task openhands:check
mise exec -- task openhands:logs
mise exec -- task openhands:down
mise exec -- task openhands:up
```

`openhands:down` stops OpenHands and its proxy; preserves state, workspace and Ollama. Do not use `compose down -v` to operate this local platform.

If executed after `llm:up` with its individual Compose, it can restore Ollama's network configuration. Run `openhands:up` to reapply the shared connection.

If the UI fails, check `openhands:logs`. Do not share keys or conversation bodies: upstream logs do not yet have our layer of redaction. If access to `/projects/demo` fails, check the group and permissions without using chmod 777. If attempting to download dependencies, the internal network must prevent it; maintain the initial task with the standard library. If the model fails to call tools or exceeds context, log the error: a past synthetic check does not guarantee agent quality.

## Validation performed and pending

The official amd64 digest was resolved and code, image configuration and component versions were checked. The combined Compose configuration, mounts and network, and script syntax were validated. Real execution requires the host terminal with access to Docker; startup, LLM profile and conversation remain pending until results are shared.

## Sources

- [Release v1.24.0 and Official Quickstart](https://github.com/OpenHands/OpenHands/tree/v1.24.0)
- [Dockerfile of the image](https://github.com/OpenHands/OpenHands/blob/v1.24.0/docker/Dockerfile)
- [Entrypoint and persistence](https://github.com/OpenHands/OpenHands/blob/v1.24.0/docker/entrypoint.sh)
- [Agent Server: configuration](https://github.com/OpenHands/software-agent-sdk/blob/v1.49.6/openhands-agent-server/openhands/agent_server/config.py)
- [Local Models](https://docs.openhands.dev/openhands/usage/llms/local-llms)

## Fix for sudo step — October 5, 2026

The first host execution validated Ollama (40.88 tokens/s), but Compose failed before downloading OpenHands: sudo removed `OH_HOST_GID` and `OH_WORKSPACE` from the environment. The helper was fixed to preserve only those two variables when invoking Compose via sudo. The full environment is not preserved nor is sudoers modified. Retry `task openhands:up`; no need to repeat the download or model check. The actual startup remains pending.

## Fix for UI publishing — October 5, 2026

The host logs confirmed that Agent Canvas and Automation started. However, `compose ps` only showed `8000/tcp`, without binding to the host. The previous configuration published the port directly from a service connected exclusively to the internal network; it did not produce an accessible port in this Engine.

 `openhands-proxy` was added, with Nginx 1.30.5 pinned by digest. Only the proxy publishes `127.0.0.1:8000`, forwarding HTTP, WebSocket and streaming to the internal 8000 port of Agent Canvas. OpenHands remains connected exclusively to `agent-link`. The proxy has normal and internal network, non-root user, read-only filesystem and no Docker socket; it does not function as a generic navigation proxy. Its access log is disabled. The proxy image is a small additional download.

Retry `task openhands:up`. The status/logs/down checks include both services. The state volume and model are not deleted. The real validation of access from the host remains pending until the new deployment is executed.

Reference: [Docker Port Publishing](https://docs.docker.com/engine/network/port-publishing/).

## Next step — first conversation and acceptance

The UI is already accessible as confirmed by the user. The active profile and a completed task remain pending. Keep sub-agents and automatic profile switching disabled. Create a new conversation with OpenHands, profile `local-qwen3-8b` and workspace `/projects/demo`.

Use the task of this guide's summation; request at least three unittest cases. Do not create the solution files ourselves before: it is evaluated that the agent produces and executes them.

Upon completion, run in the host terminal:

```bash
mise exec -- task openhands:demo:check
```

The check requires `sum.py` with `add(a, b)`, correct results for four synthetic entries and at least three successful and non-omitted unittests in `test_sum.py`. Run the generated files inside the container, not on the host. The checker verifies that normal files exist in the workspace and fails if they are missing; it does not write or correct the solution. Functional validation does not demonstrate that all agent changes have remained within the workspace: also check the conversation events.

If the agent stops due to an error, share the error message and the last action; do not change the model, context or permissions without identifying it. If it finishes, share the summary and the check output. Record after success/failure, approximate time, number of attempts and tool errors. Do not declare the phase completed just because the UI or API respond.

## Incident of tool usage and context adjustment

The user shared a cycle in which the agent lost the terminal request, chose `think` and finished without executing the requested command. The synthetic tool test passed previously, but it does not validate an agent with all its instructions and tools.

The official guide for local models of OpenHands recommends at least 22000 tokens, ideally 32768 or more. Our initial setting of 8192 was conservative to test GPU, but insufficient as a reference for the full agent. Ollama was updated and the lock was set to 32768, keeping weights, digest and model. This may increase VRAM; confirm residency and performance again before proceeding. Context loss is a hypothesis, not a confirmed cause through the real request.

From the host:

```bash
mise exec -- task openhands:up
mise exec -- task llm:check
mise exec -- task llm:status
mise exec -- task openhands:profile:check
```

The last command queries the persisted defaults of Agent Server and prints only allowed fields of the profile and tool names; it does not show keys, prompts or conversations. Existing conversations may retain another configuration. Create a new conversation after correcting the profile and confirming that the tools include terminal and files. Disable browser tools that are not needed if the UI allows configuring them.

Review input/output limits of the profile to ensure they are consistent with 32768. Do not confuse the 128 tokens of the smoke test with the agent's limit; that value is only in the synthetic test script. For Qwen3, try reasoning effort `none` if the setting is available; Ollama documents that this value disables thinking in compatible models. Do not assume that the visual Thinking indicator implies a failure on its own.

Repeat in a new conversation a single request: execute `pwd` and show the real output of the terminal tool. After that, try `cd /projects/demo && pwd && ls -la`. If it still does not call terminal, review the configuration and evaluate a different model. Fine-tuning is still not performed and no other model is downloaded.

Sources: [Recommended context by OpenHands](https://docs.openhands.dev/openhands/usage/llms/local-llms), [reasoning_effort in Ollama](https://docs.ollama.com/api/openai-compatibility).

## Validation of extended context and correction of diagnosis

The user shared on October 5 at 18:45 UTC: UI and internal connection correct, context loaded 32768, 100% GPU and 9,969,650,892 bytes of VRAM. Generation, synthetic tool and API compatibility passed, but the first request after recreating Ollama gave 0.79 tokens/s: load 32.566 s, prompt 21.998 s and token generation 12.625 s. The slowness is not attributed only to load; repeat the test to check if it persists before modifying more parameters.

`openhands:profile:check` failed because `agent_settings.tools` was null. The treatment of that value was corrected and `tools_explicitly_configured` is added; null may represent inherited defaults and does not demonstrate absence of tools in a conversation. The task queries the persisted defaults, not the effective configuration of each session.

Repeat `task openhands:profile:check`, `task llm:check`, `task llm:status` and `task llm:logs`. The agent's task is still not validated.

## Second measurement with 32768 and active profile

The user shared at 18:48 UTC on October 5: profile `local-qwen3-8b`, model `openai/qwen3:8b`, internal base URL correct, `reasoning_effort=high`; input/output limits and temperature null (defaults, does not mean zero). Tools without explicit configuration; the effective list of the conversation is still unknown.

The repetition of the smoke test gave 52.22 tokens/s, 0.265 total seconds, 0.002 seconds of load, 0.035 seconds of prompt and 0.192 seconds of generation; 100% GPU and context 32768. The logs show prompt cache reuse, so it is not a representative comparison with a cold request or a long instruction benchmark. The functional failure of the agent is still pending to be repeated.

Next experiment: in the LLM profile, change reasoning effort from high to none if the interface offers it, save and activate. Ollama documents none as a request to disable thinking in compatible boolean models. Do not claim that high is the confirmed cause of the failure. Create a new conversation with profile change and disabled subagents; request a single execution of `pwd` with the terminal tool. If the none option does not exist, review the advanced options screen before choosing another setting.

## Validated milestone — first complete task, October 5, 2026

The user shared the output of `task openhands:demo:check`: `test_negative`, `test_positive` and `test_zero` passed, three tests executed without omissions, and the additional check of the add function was satisfactory. The check executes the files present in `/projects/demo` inside the container. The folder corresponds to `artifacts/openhands/projects/demo` on the host.

Result: the local platform completed its first synthetic code and OpenHands and Qwen3 local test. The sequence included confirmation of the working path and independent verification of the solution. The execution was performed in the user's terminal; it was not rerun from Work. The change to context 32768 preceded this result. No new profile reading has been recorded yet that confirms the effective value of reasoning effort nor is the success attributed to a single change.

This milestone verifies basic functionality, not sustained quality, full security or compliance with all prompt constraints. Centralized observability, auditing, policies and platform adapters are still pending.

Next proposed experiment: fix a small bug in an example project with existing tests, checking previous failure and subsequent success, and recording duration, tool errors and file changes. Keep one agent, fixed profile and synthetic data to compare with this reference.

The second test is described in [openhands_bugfix.md](openhands_bugfix.md), with tasks `openhands:bugfix:prepare`, `baseline` and `check`.

## Next step — observability with existing integrations

The [observability guide](observability.md) explains how to interleave LiteLLM between OpenHands and Ollama, activate the three backends and provision Grafana. It includes the profile `local-qwen3-8b-observed`, acceptance commands, log location, privacy and return to the direct profile. The [diagrams](architecture/observability_diagrams.md) show the LLM path, networks, storage and evolution.

The configuration is ready; it is not asserted as deployed. The LiteLLM callback excludes messages; the Collector sanitizes traces and logs. The native tracing of OpenHands is optional for synthetic data because it can capture arguments/results before the filter. The product telemetry exporter `none` is a distinct control from OTLP of the SDK. Do not disable it thinking that the capture at source is already completely removed.
