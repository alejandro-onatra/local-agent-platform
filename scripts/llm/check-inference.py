#!/usr/bin/env python3
"""Synthetic local-only checks. Persist summary metrics, never prompts or responses."""
import argparse
import datetime
import json
import yaml
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def normalize_digest(value):
    return value.removeprefix("sha256:")


def verify_model(tags, lock):
    model = next((m for m in tags.get("models", []) if m.get("name") == lock["model"]["name"]), None)
    if model is None:
        raise ValueError("Model missing: run llm:pull.")
    if normalize_digest(model.get("digest", "")) != normalize_digest(lock["model"]["digest"]):
        raise ValueError("Model digest differs from lock; review upstream changes before using it.")
    return model


def verify_generation(data):
    if not data.get("done") or data.get("done_reason") == "length":
        raise ValueError("Generation incomplete or truncated.")
    answer = json.loads(data.get("response", ""))
    if answer.get("answer") != 4 or isinstance(answer.get("answer"), bool):
        raise ValueError("Synthetic arithmetic check failed.")
    count, duration = data.get("eval_count", 0), data.get("eval_duration", 0)
    if count <= 0 or duration <= 0:
        raise ValueError("Missing generation token/timing metrics.")
    return round(count * 1e9 / duration, 2)


def verify_gpu(data, lock):
    model = next((m for m in data.get("models", []) if m.get("name") == lock["model"]["name"]), None)
    if model is None or model.get("size_vram", 0) <= 0:
        raise ValueError("Model is not reported resident on GPU; CPU-only does not pass this check.")
    if normalize_digest(model.get("digest", "")) != normalize_digest(lock["model"]["digest"]):
        raise ValueError("Loaded model digest differs from lock.")
    return model["size_vram"]


def verify_tool_call(data):
    if not data.get("done") or data.get("done_reason") == "length":
        raise ValueError("Tool generation incomplete or truncated.")
    calls = data.get("message", {}).get("tool_calls", [])
    if len(calls) != 1:
        raise ValueError("Expected one synthetic tool call.")
    function = calls[0].get("function", {})
    arguments = function.get("arguments", {})
    if function.get("name") != "add" or arguments != {"a": 2, "b": 3}:
        raise ValueError("Synthetic tool name/arguments incorrect; OpenHands integration remains gated.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-only", action="store_true")
    args = parser.parse_args()
    lock = yaml.safe_load((ROOT / "infra/llm/versions.yaml").read_text())
    # Exact loopback destination; ignore environment proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, payload=None, timeout=600):
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(lock["base_url"] + path, data=body,
                                     headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=timeout) as response:
            result = json.load(response)
        if "error" in result:
            raise ValueError("Ollama returned an error; review service locally.")
        return result

    summary = {"time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "model": lock["model"]["name"], "expected_digest": lock["model"]["digest"],
               "status": "failed"}
    failure = None
    try:
        version = request("/api/version", timeout=10)["version"]
        if version != lock["ollama"]["version"]:
            raise ValueError("Server version differs from lock.")
        summary["server_version"] = version
        verify_model(request("/api/tags", timeout=10), lock)
        summary["model_digest_verified"] = True
        if not args.model_only:
            options = {"temperature": 0, "seed": 42,
                       "num_ctx": lock["model"]["context_length"],
                       "num_predict": lock["model"]["num_predict"]}
            generated = request("/api/generate", {
                "model": lock["model"]["name"], "prompt": "Calculate 2 + 2. Return answer as JSON.",
                "format": {"type": "object", "properties": {"answer": {"type": "integer"}},
                           "required": ["answer"], "additionalProperties": False},
                "think": False, "stream": False, "options": options, "keep_alive": "5m"})
            summary["tokens_per_second"] = verify_generation(generated)
            summary["generated_tokens"] = generated["eval_count"]
            # Keep the legacy total-time field; expose each phase separately.
            summary["generation_seconds"] = round(generated.get("total_duration", 0) / 1e9, 3)
            summary["token_generation_seconds"] = round(generated["eval_duration"] / 1e9, 3)
            for source, target in (("load_duration", "model_load_seconds"),
                                   ("prompt_eval_duration", "prompt_processing_seconds")):
                if source in generated:
                    summary[target] = round(generated[source] / 1e9, 3)
            summary["size_vram_bytes"] = verify_gpu(request("/api/ps", timeout=10), lock)
            tool_data = request("/api/chat", {
                "model": lock["model"]["name"], "messages": [
                    {"role": "system", "content": "Use the add tool for addition. Do not calculate yourself."},
                    {"role": "user", "content": "Call add with a=2 and b=3."}],
                "tools": [{"type": "function", "function": {
                    "name": "add", "description": "Add two integers.",
                    "parameters": {"type": "object", "properties": {
                        "a": {"type": "integer"}, "b": {"type": "integer"}},
                        "required": ["a", "b"]}}}],
                "think": False, "stream": False, "options": options, "keep_alive": "5m"})
            verify_tool_call(tool_data)
            summary["synthetic_tool_call_verified"] = True
            # Exercise the endpoint format that an OpenAI-compatible client will use.
            compatible = request("/v1/chat/completions", {
                "model": lock["model"]["name"], "messages": [
                    {"role": "user", "content": "Reply only LOCAL_LLM_OK. /no_think"}],
                "stream": False, "temperature": 0, "max_tokens": 128})
            choices = compatible.get("choices", [])
            if not choices or choices[0].get("finish_reason") == "length" or not choices[0].get("message", {}).get("content", "").strip():
                raise ValueError("OpenAI-compatible completion missing or truncated.")
            summary["openai_compatible_completion_verified"] = True
        summary["status"] = "passed"
    except (ValueError, KeyError, urllib.error.URLError, TimeoutError, OSError) as exc:
        failure = exc
        # No raw provider response/error body in reports.
        summary["error_class"] = type(exc).__name__
    finally:
        target = ROOT / "artifacts/diagnostics"
        target.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix="llm-", suffix=".json", dir=target)
        with os.fdopen(fd, "w") as out:
            json.dump(summary, out, indent=2)
            out.write("\n")
        print(json.dumps(summary, indent=2))
        print("Report:", filename)
    if failure is not None:
        if isinstance(failure, urllib.error.URLError):
            raise SystemExit("LLM check failed: local API unavailable; start llm:up and inspect llm:logs.")
        raise SystemExit(f"LLM check failed: {failure}")
    print("RESULT: model verified." if args.model_only else
          "RESULT: generation, GPU residency, synthetic tool call and API compatibility passed.")


if __name__ == "__main__":
    main()
