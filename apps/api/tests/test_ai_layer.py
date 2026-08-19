"""The AI abstraction (§15, §70, §72) and the credit rules (§40).

These are the parts where a bug is expensive: a mis-priced generation costs
money, and a licence guard that does not hold costs more than that.
"""

from __future__ import annotations

import pytest
from PIL import Image

from app.ai.base import GenerationResult, VirtualTryOnEngine
from app.ai.providers.mock import MockImageGeneration, MockSegmentation, MockVirtualTryOn
from app.ai.registry import PROVIDERS, _enforce_license, resolve_class
from app.core.errors import InvalidImageError, LicenseError, ModelLoadError
from app.models.enums import AIModelType, CommercialUse, GarmentCategory, JobType
from app.services import credits


class TestRegistry:
    def test_resolves_every_registered_mock_provider(self) -> None:
        for engine_type, providers in PROVIDERS.items():
            if "mock" not in providers:
                continue
            cls = resolve_class(engine_type, "mock")
            assert cls is not None

    def test_unknown_provider_names_the_known_ones(self) -> None:
        with pytest.raises(ModelLoadError, match="mock"):
            resolve_class(AIModelType.VTON, "does-not-exist")

    def test_blocks_a_non_commercial_engine(self, monkeypatch) -> None:
        """§72 — the guard that stops CC BY-NC-SA weights loading by accident."""

        class NonCommercialEngine(MockVirtualTryOn):
            pass

        engine = NonCommercialEngine()
        engine.info = type(engine.info)(
            key="restricted",
            name="Restricted Model",
            license="CC BY-NC-SA 4.0",
            commercial_use=CommercialUse.NOT_ALLOWED,
        )

        monkeypatch.setattr(
            "app.ai.registry.settings.allow_non_commercial_models", False, raising=False
        )
        with pytest.raises(LicenseError, match="MODEL_LICENSE.md"):
            _enforce_license(engine)

    def test_allows_a_permissive_engine(self) -> None:
        _enforce_license(MockVirtualTryOn())  # must not raise


class TestMockVirtualTryOn:
    @pytest.fixture
    def engine(self) -> MockVirtualTryOn:
        engine = MockVirtualTryOn()
        engine.load()
        return engine

    def test_implements_the_interface(self, engine: MockVirtualTryOn) -> None:
        assert isinstance(engine, VirtualTryOnEngine)
        assert engine.is_loaded

    def test_produces_an_image_of_the_requested_size(self, engine: MockVirtualTryOn) -> None:
        result = engine.generate(
            Image.new("RGB", (768, 1024), (180, 160, 150)),
            Image.new("RGB", (512, 512), (30, 60, 200)),
            width=768,
            height=1024,
        )
        assert isinstance(result, GenerationResult)
        assert len(result.images) == 1
        assert result.images[0].size == (768, 1024)

    def test_is_deterministic_for_a_fixed_seed(self, engine: MockVirtualTryOn) -> None:
        """§67 — a seed has to actually reproduce a result, or it is decoration."""
        args = dict(
            person=Image.new("RGB", (768, 1024), (180, 160, 150)),
            garment=Image.new("RGB", (512, 512), (30, 60, 200)),
            width=512,
            height=512,
            seed=1234,
        )
        first = engine.generate(**args).images[0]
        second = engine.generate(**args).images[0]
        assert list(first.getdata()) == list(second.getdata())

    def test_different_seeds_diverge(self, engine: MockVirtualTryOn) -> None:
        common = dict(
            person=Image.new("RGB", (768, 1024), (180, 160, 150)),
            garment=Image.new("RGB", (512, 512), (30, 60, 200)),
            width=512,
            height=512,
        )
        a = engine.generate(**common, seed=1).images[0]
        b = engine.generate(**common, seed=99).images[0]
        assert list(a.getdata()) != list(b.getdata())

    def test_reports_progress_monotonically(self, engine: MockVirtualTryOn) -> None:
        seen: list[int] = []
        engine.generate(
            Image.new("RGB", (768, 1024)),
            Image.new("RGB", (512, 512)),
            width=512,
            height=512,
            on_progress=lambda pct, _label: seen.append(pct),
        )
        assert seen == sorted(seen)
        assert seen[-1] <= 100

    def test_rejects_an_unusably_small_input(self, engine: MockVirtualTryOn) -> None:
        with pytest.raises(InvalidImageError):
            engine.validate_input(Image.new("RGB", (32, 32)), Image.new("RGB", (512, 512)))

    def test_honours_num_images(self, engine: MockVirtualTryOn) -> None:
        result = engine.generate(
            Image.new("RGB", (768, 1024)),
            Image.new("RGB", (512, 512)),
            width=512,
            height=512,
            num_images=3,
        )
        assert len(result.images) == 3


class TestMockImageGeneration:
    def test_same_prompt_gives_the_same_backdrop(self) -> None:
        engine = MockImageGeneration()
        engine.load()
        a = engine.generate("luxury marble studio", width=512, height=512).images[0]
        b = engine.generate("luxury marble studio", width=512, height=512).images[0]
        assert list(a.getdata()) == list(b.getdata())


class TestMockSegmentation:
    def test_returns_a_single_channel_mask(self) -> None:
        engine = MockSegmentation()
        engine.load()

        image = Image.new("RGB", (256, 256), (255, 255, 255))
        image.paste((20, 20, 20), (64, 64, 192, 192))

        mask = engine.segment(image)
        assert mask.mode == "L"
        assert mask.size == image.size
        # The dark square should register as subject.
        assert mask.getpixel((128, 128)) > 200

    def test_box_prompt_is_respected(self) -> None:
        engine = MockSegmentation()
        engine.load()
        mask = engine.segment(Image.new("RGB", (256, 256)), prompt_box=(10, 10, 100, 100))
        assert mask.getpixel((50, 50)) == 255
        assert mask.getpixel((200, 200)) == 0


class TestCreditPricing:
    def test_try_on_costs_one_credit(self) -> None:
        assert credits.cost_for(JobType.VTON) == 1

    def test_hd_adds_a_surcharge(self) -> None:
        assert credits.cost_for(JobType.VTON, hd=True) == 1 + credits.HD_SURCHARGE

    def test_variations_multiply(self) -> None:
        assert credits.cost_for(JobType.VTON, num_images=3) == 3

    def test_hd_and_variations_compose(self) -> None:
        assert credits.cost_for(JobType.VTON, hd=True, num_images=2) == (
            1 + credits.HD_SURCHARGE
        ) * 2

    def test_free_operations_stay_free_regardless(self) -> None:
        """A zero-cost job must not become chargeable via HD or batching."""
        assert credits.cost_for(JobType.BACKGROUND_REMOVE) == 0
        assert credits.cost_for(JobType.BACKGROUND_REMOVE, hd=True, num_images=5) == 0
        assert credits.cost_for(JobType.ENHANCE, hd=True) == 0

    def test_video_is_the_most_expensive(self) -> None:
        assert credits.cost_for(JobType.VIDEO) == 5

    def test_every_job_type_has_a_price(self) -> None:
        for job_type in JobType:
            assert credits.cost_for(job_type) >= 0

    def test_every_plan_has_limits(self) -> None:
        for plan, limits in credits.PLAN_LIMITS.items():
            assert limits["max_projects"] > 0
            assert limits["storage_quota_mb"] > 0
            assert plan in credits.MONTHLY_GRANT


class TestJobRouting:
    def test_each_job_type_routes_to_a_queue(self) -> None:
        from app.queue.celery_app import queue_for

        for job_type in JobType:
            assert queue_for(job_type) in {"vton", "image", "cpu", "video"}

    def test_gpu_heavy_work_avoids_the_cpu_queue(self) -> None:
        from app.queue.celery_app import queue_for

        assert queue_for(JobType.VTON) == "vton"
        assert queue_for(JobType.UPSCALE) == "image"
        assert queue_for(JobType.VIDEO) == "video"
        # Cheap CPU work must not sit behind a diffusion job.
        assert queue_for(JobType.BACKGROUND_REMOVE) == "cpu"
        assert queue_for(JobType.ENHANCE) == "cpu"


class TestJobStatus:
    def test_terminal_states(self) -> None:
        from app.models.enums import JobStatus

        assert JobStatus.COMPLETED.is_terminal
        assert JobStatus.FAILED.is_terminal
        assert JobStatus.CANCELLED.is_terminal
        assert not JobStatus.PROCESSING.is_terminal
        assert not JobStatus.QUEUED.is_terminal

    def test_every_status_has_progress_and_a_label(self) -> None:
        from app.models.enums import JOB_STATUS_LABEL, JOB_STATUS_PROGRESS, JobStatus

        for status in JobStatus:
            assert status in JOB_STATUS_PROGRESS
            assert status in JOB_STATUS_LABEL
