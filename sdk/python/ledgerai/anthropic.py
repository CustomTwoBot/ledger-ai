from __future__ import annotations

from types import SimpleNamespace

from ._tracker import CostTracker

_MOCK_INPUT_TOKENS = 100
_MOCK_OUTPUT_TOKENS = 50


def _make_mock_response(model: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="mock-response",
        type="message",
        role="assistant",
        model=model,
        content=[SimpleNamespace(type="text", text="[mock response]")],
        stop_reason="end_turn",
        usage=SimpleNamespace(
            input_tokens=_MOCK_INPUT_TOKENS,
            output_tokens=_MOCK_OUTPUT_TOKENS,
        ),
    )


class _Messages:
    def __init__(self, messages, tracker: CostTracker, mock: bool) -> None:
        self._messages = messages
        self._tracker = tracker
        self._mock = mock

    def create(self, **kwargs):
        if kwargs.get("stream"):
            raise NotImplementedError(
                "ledgerai does not support streaming yet; pass stream=False"
            )
        model = kwargs.get("model", "unknown")
        self._tracker.check_budget()
        if self._mock:
            response = _make_mock_response(model)
        else:
            response = self._messages.create(**kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._tracker.log_cost(
                "anthropic", model, usage.input_tokens, usage.output_tokens
            )
        return response

    def __getattr__(self, name):
        return getattr(self._messages, name)


class LedgerAnthropic:
    """Anthropic client with automatic budget gating and cost logging."""

    def __init__(self, *args, ledger_url: str, agent_id: str, api_key: str, mock: bool = False, **kwargs) -> None:
        import anthropic

        self._client = anthropic.Anthropic(*args, **kwargs)
        tracker = CostTracker(ledger_url, agent_id, api_key)
        self.messages = _Messages(self._client.messages, tracker, mock)

    def __getattr__(self, name):
        return getattr(self._client, name)
