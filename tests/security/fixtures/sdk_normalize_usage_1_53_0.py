# MIT License
# 
# Copyright (c) 2026 OpenHands contributors
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Reference function from OpenHands/software-agent-sdk v1.53.0 (MIT).
# https://github.com/OpenHands/software-agent-sdk/blob/v1.53.0/openhands-sdk/openhands/sdk/llm/utils/telemetry.py
def normalize_usage(usage: Usage | ResponseAPIUsage | None) -> UsageSnapshot | None:
    """Return a :class:`UsageSnapshot` for either provider usage shape.

    ``None`` means "no token accounting": the provider reported no usage, or
    reported a shape this module does not recognize. Unrecognized shapes are
    ignored rather than guessed at, so adding a provider cannot silently feed
    invented token counts into cost and cache accounting.
    """
    if isinstance(usage, Usage):
        prompt_details = usage.prompt_tokens_details
        completion_details = usage.completion_tokens_details
        # ``cache_creation_tokens`` defaults to ``None``, so presence in
        # ``model_fields_set`` is what distinguishes "provider reported a cache
        # write" from "provider said nothing about cache writes". litellm,
        # however, deletes the attribute from the instance when the value is
        # ``None`` (e.g. minimax-m3 reports ``cache_creation_tokens: null``),
        # so ``model_fields_set`` alone is insufficient; guard with ``hasattr``.
        cache_write = 0
        if (
            prompt_details is not None
            and "cache_creation_tokens" in prompt_details.model_fields_set
            and hasattr(prompt_details, "cache_creation_tokens")
        ):
            cache_write = int(prompt_details.cache_creation_tokens or 0)
        return UsageSnapshot(
            prompt_tokens=int(usage.prompt_tokens or 0),
            completion_tokens=int(usage.completion_tokens or 0),
            reasoning_tokens=(
                int(completion_details.reasoning_tokens or 0)
                if completion_details is not None
                else 0
            ),
            cache_read_tokens=(
                int(prompt_details.cached_tokens or 0)
                if prompt_details is not None
                else 0
            ),
            cache_write_tokens=cache_write,
        )

    if isinstance(usage, ResponseAPIUsage):
        input_details = usage.input_tokens_details
        output_details = usage.output_tokens_details
        return UsageSnapshot(
            prompt_tokens=int(usage.input_tokens or 0),
            completion_tokens=int(usage.output_tokens or 0),
            reasoning_tokens=(
                int(output_details.reasoning_tokens or 0)
                if output_details is not None
                else 0
            ),
            cache_read_tokens=(
                int(input_details.cached_tokens or 0)
                if input_details is not None
                else 0
            ),
        )

    return None
