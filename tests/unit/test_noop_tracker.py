"""Unit tests for the NoopTracker."""

from agentml.tracking.noop_tracker import NoopTracker


async def test_noop_does_not_raise() -> None:
    tracker = NoopTracker()
    await tracker.log_metrics("x", {"a": 1.0})
    await tracker.log_params("x", {"b": "c"})
    await tracker.log_artifact("x", "/some/path")
    metrics = await tracker.get_metrics("x")
    assert metrics == {}
    await tracker.close()
