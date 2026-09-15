"""Shared admission limit for CPU-heavy forecasts and analysis."""
from contextlib import contextmanager
from threading import BoundedSemaphore

from fastapi import HTTPException

SCENARIO_GATE = BoundedSemaphore(value=2)


@contextmanager
def forecast_capacity():
    if not SCENARIO_GATE.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="The forecast engine is busy. Try again shortly.")
    try:
        yield
    finally:
        SCENARIO_GATE.release()
