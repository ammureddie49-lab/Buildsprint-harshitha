"""Scored CLI model policy, conservative request budgeting, and cost metering.

Default is auto: a configured API key enables CLI language interpretation. An
explicit TRACEMIND_USE_LLM=0 always disables it. Studio remote calls have a
separate explicit consent gate and are not changed by this file.
"""
from __future__ import annotations
import json
import os

TRUE = {"1", "true", "yes", "on"}
FALSE = {"0", "false", "no", "off"}
PRICES_USD_PER_M = {"gpt-4.1-mini": (0.40, 1.60), "gpt-4o-mini": (0.15, 0.60)}


def model_name():
    return os.getenv("TRACEMIND_MODEL") or os.getenv("TRACEMIND_OPENAI_MODEL") or "gpt-4.1-mini"


def model_key():
    return (os.getenv("TRACEMIND_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def model_enabled():
    mode = os.getenv("TRACEMIND_USE_LLM", "auto").strip().lower()
    if mode in FALSE:
        return False
    if mode not in TRUE | {"auto", ""}:
        return False  # Unknown modes fail closed.
    return bool(model_key()) and rates() is not None


def rates():
    model = model_name()
    default = PRICES_USD_PER_M.get(model)
    inp, out = os.getenv("TRACEMIND_PRICE_INPUT_PER_M"), os.getenv("TRACEMIND_PRICE_OUTPUT_PER_M")
    if inp and out:
        try:
            a, b = float(inp), float(out)
            if a >= 0 and b >= 0:
                return a, b
        except ValueError:
            pass
    return default  # Unknown model is unpriced; never claim a real zero-dollar call.


def cost_usd(input_tokens, output_tokens):
    price = rates()
    if price is None:
        return None
    return (int(input_tokens) * price[0] + int(output_tokens) * price[1]) / 1_000_000


def conservative_input_tokens(instruction, payload):
    """Estimate input *before* sending; fall back to an upper bound for byte-BPE.

    With tiktoken installed use the named model's encoding; reserve 256 tokens
    for Responses framing. Without it, UTF-8 byte count is a conservative
    ceiling for byte-based tokenizers (not a formal guarantee for every model).
    The server response's usage.input_tokens is still authoritative.
    """
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    combined = instruction + "\n" + raw
    try:
        import tiktoken
        try:
            encoding = tiktoken.encoding_for_model(model_name())
        except KeyError:
            encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(combined)) + 256
    except Exception:
        # The byte-based fallback deliberately sacrifices context to avoid a
        # token-budget overrun if tiktoken is missing in the evaluator's image.
        return len(combined.encode("utf-8")) + 256


def fits_input_budget(instruction, payload, limit):
    return conservative_input_tokens(instruction, payload) <= int(limit)
