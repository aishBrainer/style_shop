"""Test fixtures.

The suite is split by what it needs:

* `test_imaging.py` and `test_credits_math.py` are pure and run anywhere.
* `test_api.py` needs Postgres (the schema uses JSONB and ARRAY, which SQLite
  cannot represent) and is skipped automatically when TEST_DATABASE_URL is not
  set. Run those against the compose stack.
"""

from __future__ import annotations

import os
import uuid

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a Postgres database to run integration tests.",
)


@pytest.fixture
def sample_png() -> bytes:
    """A real 512x512 PNG, generated rather than committed as a fixture blob."""
    import io

    from PIL import Image

    img = Image.new("RGB", (512, 512), (200, 120, 90))
    # Add structure so blank-image detection does not flag it.
    for x in range(0, 512, 64):
        for y in range(0, 512, 64):
            if (x // 64 + y // 64) % 2 == 0:
                img.paste((40, 60, 120), (x, y, x + 64, y + 64))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def blank_png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (512, 512), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:12]}@example.test"
