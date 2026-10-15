"""The real async dispatcher must wake its background loop and return completion."""
import hindsight_test_provider as provider


def test_actual_async_transport_dispatch():
    async def complete():
        return "settled"
    assert provider._run_sync(complete(), timeout=5) == "settled"
