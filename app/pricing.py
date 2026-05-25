PRICING: dict[str, dict[str, float]] = {
    "gpt-4o":             {"input": 2.50,  "output": 10.00},
    "gpt-3.5-turbo":      {"input": 0.50,  "output": 1.50},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":   {"input": 0.80,  "output": 4.00},
}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model)
    if rates is None:
        raise ValueError(f"Unknown model: {model!r}. Supported: {list(PRICING)}")
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
