"""Shared admission limit for CPU-heavy forecasts and analysis."""

from contextlib import contextmanager
from threading import BoundedSemaphore

from fastapi import HTTPException

SCENARIO_GATE = BoundedSemaphore(value=2)


@contextmanager
def forecast_capacity():
    if not SCENARIO_GATE.acquire(blocking=False):
        raise HTTPException(
            status_code=503, detail="The forecast engine is busy. Try again shortly."
        )
    try:
        yield
    finally:
        SCENARIO_GATE.release()


async def cancellable_calculation(request, calculate):
    """Propagate an HTTP disconnect to a cooperative CPU calculation.

    The calculation owns its capacity lease until it has actually finished.
    No per-client state or personal inputs are stored in a global job registry.
    """
    import asyncio
    from threading import Event

    cancelled = Event()
    task = asyncio.create_task(asyncio.to_thread(calculate, cancelled.is_set))
    try:
        while not task.done():
            completed, _ = await asyncio.wait({task}, timeout=0.05)
            if not completed and await request.is_disconnected():
                cancelled.set()
        return await task
    except asyncio.CancelledError:
        cancelled.set()
        try:
            await asyncio.shield(task)
        finally:
            raise
