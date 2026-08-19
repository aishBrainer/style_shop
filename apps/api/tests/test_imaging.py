"""Upload validation and image helpers.

These cover the §58 rule that matters most: what a file *is* comes from its
bytes, never from what the browser claimed.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core.errors import UploadRejectedError
from app.services import imaging


class TestSniff:
    def test_identifies_a_real_png(self, sample_png: bytes) -> None:
        info = imaging.sniff(sample_png)
        assert info.mime_type == "image/png"
        assert (info.width, info.height) == (512, 512)
        assert len(info.checksum_sha256) == 64

    def test_rejects_empty_upload(self) -> None:
        with pytest.raises(UploadRejectedError):
            imaging.sniff(b"")

    def test_rejects_non_image_bytes(self) -> None:
        with pytest.raises(UploadRejectedError):
            imaging.sniff(b"#!/bin/sh\nrm -rf /\n")

    def test_rejects_a_script_renamed_as_png(self) -> None:
        """The attack the filename/MIME rule exists for: a payload that claims
        to be an image. Only the bytes are consulted, so it is rejected."""
        with pytest.raises(UploadRejectedError):
            imaging.sniff(b"<?php system($_GET['c']); ?>" + b"\x00" * 512)

    def test_rejects_image_below_minimum_dimensions(self) -> None:
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), (10, 10, 10)).save(buf, format="PNG")
        with pytest.raises(UploadRejectedError, match="too small"):
            imaging.sniff(buf.getvalue())

    def test_checksum_is_stable(self, sample_png: bytes) -> None:
        assert imaging.sniff(sample_png).checksum_sha256 == (
            imaging.sniff(sample_png).checksum_sha256
        )


class TestRenditions:
    def test_produces_preview_and_thumbnail(self, sample_png: bytes) -> None:
        preview, thumbnail = imaging.make_renditions(sample_png)

        with Image.open(io.BytesIO(preview)) as p:
            preview_size = p.size
            assert max(preview_size) <= imaging.PREVIEW_MAX
            assert p.format == "WEBP"

        with Image.open(io.BytesIO(thumbnail)) as t:
            thumbnail_size = t.size
            assert max(thumbnail_size) <= imaging.THUMBNAIL_MAX
            assert t.format == "WEBP"

        # §98 — the gallery loads the smallest rendition. Asserted on pixel
        # dimensions rather than byte length: encoded size depends on image
        # content, and for a synthetic fixture the resampled thumbnail can
        # actually encode larger than the un-resampled preview. Dimensions are
        # the invariant the code guarantees; bytes follow for real photography.
        assert thumbnail_size[0] < preview_size[0]
        assert thumbnail_size[1] < preview_size[1]

    def test_fit_within_never_upscales(self) -> None:
        small = Image.new("RGB", (100, 100))
        assert imaging.fit_within(small, 1024).size == (100, 100)


class TestQualityChecks:
    def test_detects_a_blank_image(self, blank_png: bytes) -> None:
        assert imaging.looks_blank(imaging.load(blank_png)) is True

    def test_does_not_flag_a_real_image(self, sample_png: bytes) -> None:
        assert imaging.looks_blank(imaging.load(sample_png)) is False

    def test_detects_corruption(self, sample_png: bytes) -> None:
        assert imaging.is_corrupt(sample_png) is False
        assert imaging.is_corrupt(sample_png[:100]) is True


class TestWatermark:
    def test_watermark_changes_pixels_but_not_size(self, sample_png: bytes) -> None:
        original = imaging.load(sample_png)
        marked = imaging.apply_watermark(original)

        assert marked.size == original.size
        assert list(marked.getdata()) != list(original.getdata())
