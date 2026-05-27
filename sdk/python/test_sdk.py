from ledgerai import LedgerAnthropic

client = LedgerAnthropic(
    ledger_url="http://127.0.0.1:8000",
    agent_id="test-agent",
    mock=True
)

response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=10,
    messages=[{"role": "user", "content": "say hi"}]
)

print(response.content[0].text)
print("Done - check your dashboard")