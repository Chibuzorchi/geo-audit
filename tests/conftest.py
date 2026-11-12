import pytest
from shapely.geometry import box


@pytest.fixture
def zone():
    return box(2050, -500, 7950, 500)


@pytest.fixture
def valid_row():
    return dict(
        ping_id="P001",
        driver_id="SYN-D01",
        ts_utc="2026-11-04T03:00:00Z",
        received_at_utc="2026-11-04T03:00:01Z",
        lat="37.5",
        lon="127.0",
        is_synthetic="true",
    )
