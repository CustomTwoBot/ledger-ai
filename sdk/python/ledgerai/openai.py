from __future__ import annotations

from ._tracker import CostTracker


class _Completions:
    def __init__(self, completions, tracker: CostTracker) -> None:
        self._completions = completions
        self._tracker = tracker

    def create(self, **kwargs):
        if kwargs.get("stream"):
            raise NotImplementedError(
                "ledgerai does not support streaming yet; pass stream=False"
            )
        model = kwargs.get("model", "unknown")
        self._tracker.check_budget()
        response = self._completions.create(**kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._tracker.log_cost(
                "openai", model, usage.prompt_tokens, usage.completion_tokens
            )
        return response

    def __getattr__(self, name):
        return getattr(self._completions, name)


class _Chat:
    def __init__(self, chat, tracker: CostTracker) -> None:
        self._chat = chat
        self.completions = _Completions(chat.completions, tracker)

    def __getattr__(self, name):
        return getattr(self._chat, name)


class LedgerOpenAI:
    """OpenAI client with automatic budget gating and cost logging."""

    def __init__(self, *args, ledger_url: str, agent_id: str, **kwargs) -> None:
        import openai

        self._client = openai.OpenAI(*args, **kwargs)
        tracker = CostTracker(ledger_url, agent_id)
        self.chat = _Chat(self._client.chat, tracker)

    def __getattr__(self, name):
        return getattr(self._client, name)
