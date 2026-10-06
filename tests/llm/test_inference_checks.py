import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / "scripts/llm/check-inference.py"
spec = importlib.util.spec_from_file_location("inference", path)
inference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inference)


class InferenceValidationTests(unittest.TestCase):
    def setUp(self):
        self.lock = {"model": {"name": "qwen3:8b", "digest": "sha256:expected"}}

    def test_changed_model_is_rejected(self):
        with self.assertRaises(ValueError):
            inference.verify_model({"models": [{"name": "qwen3:8b", "digest": "changed"}]}, self.lock)

    def test_missing_model_is_rejected(self):
        with self.assertRaises(ValueError):
            inference.verify_model({"models": []}, self.lock)

    def test_digest_prefix_is_normalized(self):
        inference.verify_model({"models": [{"name": "qwen3:8b", "digest": "expected"}]}, self.lock)

    def test_cpu_only_does_not_pass_gpu_check(self):
        with self.assertRaises(ValueError):
            inference.verify_gpu({"models": [{"name": "qwen3:8b", "digest": "expected", "size_vram": 0}]}, self.lock)

    def test_gpu_allocation_is_reported(self):
        value = inference.verify_gpu({"models": [{"name": "qwen3:8b", "digest": "expected", "size_vram": 100}]}, self.lock)
        self.assertEqual(value, 100)

    def test_wrong_answer_is_rejected(self):
        with self.assertRaises(ValueError):
            inference.verify_generation({"done": True, "response": '{"answer": 5}', "eval_count": 10, "eval_duration": 1000000000})

    def test_truncated_generation_is_rejected(self):
        with self.assertRaises(ValueError):
            inference.verify_generation({"done": True, "done_reason": "length", "response": '{"answer": 4}'})

    def test_token_rate_has_correct_units(self):
        value = inference.verify_generation({"done": True, "response": '{"answer": 4}', "eval_count": 10, "eval_duration": 2000000000})
        self.assertEqual(value, 5)

    def test_text_without_tool_call_is_rejected(self):
        with self.assertRaises(ValueError):
            inference.verify_tool_call({"done": True, "message": {"content": "5"}})

    def test_wrong_tool_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            inference.verify_tool_call({"done": True, "message": {"tool_calls": [{"function": {"name": "add", "arguments": {"a": 2, "b": 4}}}]}})

    def test_expected_tool_call_passes(self):
        inference.verify_tool_call({"done": True, "message": {"tool_calls": [{"function": {"name": "add", "arguments": {"a": 2, "b": 3}}}]}})


if __name__ == "__main__":
    unittest.main()
