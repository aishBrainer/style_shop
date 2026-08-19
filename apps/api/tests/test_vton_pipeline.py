"""The §17 stage pipeline and §65 quality gate."""

from __future__ import annotations

import pytest
from PIL import Image

from app.ai.pipelines import vton
from app.core.errors import InvalidImageError, OutputQualityError
from app.models.enums import GarmentCategory


def person_image(size: tuple[int, int] = (768, 1024)) -> Image.Image:
    """A synthetic 'person' with enough structure to pass the blank check."""
    img = Image.new("RGB", size, (210, 190, 175))
    img.paste((60, 50, 45), (size[0] // 3, 0, 2 * size[0] // 3, size[1] // 5))  # head
    img.paste((80, 90, 140), (size[0] // 4, size[1] // 5, 3 * size[0] // 4, size[1]))  # body
    return img


def garment_image(size: tuple[int, int] = (600, 600)) -> Image.Image:
    img = Image.new("RGB", size, (255, 255, 255))
    img.paste((190, 40, 60), (100, 100, 500, 500))
    return img


class TestRunVton:
    def test_completes_and_returns_an_image(self) -> None:
        result = vton.run_vton(
            vton.VTONRequest(person=person_image(), garment=garment_image(), seed=7)
        )
        assert len(result.images) == 1
        assert result.images[0].size == vton.STANDARD_SIZE

    def test_hd_uses_the_larger_size(self) -> None:
        request = vton.VTONRequest(person=person_image(), garment=garment_image(), hd=True)
        assert request.size == vton.HD_SIZE

    def test_records_parameters_for_reproducibility(self) -> None:
        """§66 — every parameter is stored, so a result can be regenerated."""
        result = vton.run_vton(
            vton.VTONRequest(
                person=person_image(),
                garment=garment_image(),
                seed=42,
                steps=25,
                category=GarmentCategory.DRESS,
            )
        )
        assert result.params["seed"] == 42
        assert result.params["steps"] == 25
        assert result.params["category"] == "dress"

    def test_reports_progress_across_all_stages(self) -> None:
        stages: list[tuple[int, str]] = []
        vton.run_vton(
            vton.VTONRequest(person=person_image(), garment=garment_image()),
            on_progress=lambda pct, label: stages.append((pct, label)),
        )
        percentages = [p for p, _ in stages]
        assert percentages == sorted(percentages)
        assert percentages[0] < 10       # starts near zero
        assert percentages[-1] >= 90     # reaches the end
        assert len({label for _, label in stages}) > 2

    def test_rejects_a_blank_person_image(self) -> None:
        with pytest.raises(InvalidImageError, match="blank"):
            vton.run_vton(
                vton.VTONRequest(
                    person=Image.new("RGB", (768, 1024), (255, 255, 255)),
                    garment=garment_image(),
                )
            )

    def test_rejects_a_blank_garment_image(self) -> None:
        with pytest.raises(InvalidImageError, match="blank"):
            vton.run_vton(
                vton.VTONRequest(
                    person=person_image(),
                    garment=Image.new("RGB", (600, 600), (255, 255, 255)),
                )
            )

    def test_a_supplied_mask_is_used(self) -> None:
        mask = Image.new("L", (600, 600), 0)
        mask.paste(255, (150, 150, 450, 450))

        result = vton.run_vton(
            vton.VTONRequest(
                person=person_image(), garment=garment_image(), mask=mask, auto_mask=False
            )
        )
        assert len(result.images) == 1

    def test_quality_checks_are_attached(self) -> None:
        """§65 — the result carries evidence that it was checked."""
        result = vton.run_vton(
            vton.VTONRequest(person=person_image(), garment=garment_image())
        )
        checks = result.metadata["quality_checks"]
        assert checks["passed"] is True
        assert checks["blank_images"] == 0


class TestNormalisation:
    def test_person_is_cropped_to_fill(self) -> None:
        wide = Image.new("RGB", (2000, 800), (100, 100, 100))
        assert vton._normalise(wide, (768, 1024)).size == (768, 1024)

    def test_garment_is_padded_not_cropped(self) -> None:
        """A padded garment keeps its aspect ratio — the product must never be
        cut off, which is what cropping would do to a tall dress."""
        tall = Image.new("RGB", (400, 1600), (20, 20, 20))
        out = vton._normalise(tall, (768, 1024), pad=True)
        assert out.size == (768, 1024)
        # The corners should be the white padding, not garment pixels.
        assert out.getpixel((5, 5)) == (255, 255, 255)


class TestQualityGate:
    def test_flags_a_blank_output(self) -> None:
        blank = Image.new("RGB", (768, 1024), (128, 128, 128))
        checks = vton._quality_checks([blank], (768, 1024))
        assert checks["passed"] is False
        assert checks["blank_images"] == 1

    def test_passes_a_real_output(self) -> None:
        checks = vton._quality_checks([person_image()], (768, 1024))
        assert checks["passed"] is True
