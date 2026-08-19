"""Typed application errors.

§64: users never see a raw Python traceback. Every error carries a stable
machine-readable `code` plus a message written for a human.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return {"error": body}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "The requested resource does not exist."


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "You do not have access to this resource."


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "Authentication is required."


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "That resource already exists."


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "The submitted data is not valid."


class RateLimitError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests. Please slow down."


class InsufficientCreditsError(AppError):
    status_code = 402
    code = "INSUFFICIENT_CREDITS"
    message = "You do not have enough credits for this generation."


class FeatureDisabledError(AppError):
    status_code = 403
    code = "FEATURE_DISABLED"
    message = "This feature is not currently available on your plan."


class UploadRejectedError(AppError):
    status_code = 415
    code = "UPLOAD_REJECTED"
    message = "That file could not be accepted."


# --- AI failure codes (§64) ------------------------------------------------
# Raised inside workers; persisted on generation_jobs.error_code.

class AIError(AppError):
    status_code = 500
    code = "UNKNOWN_MODEL_ERROR"
    message = "Generation failed. Please try again."
    retryable: bool = True


class GPUOutOfMemoryError(AIError):
    code = "GPU_OUT_OF_MEMORY"
    message = "The server ran out of GPU memory. Try a smaller output size."
    retryable = True


class ModelLoadError(AIError):
    code = "MODEL_LOAD_ERROR"
    message = "The AI model could not be loaded. Our team has been notified."
    retryable = True


class InvalidImageError(AIError):
    status_code = 422
    code = "INVALID_IMAGE"
    message = "That image could not be processed. Try a different photo."
    retryable = False


class ModelTimeoutError(AIError):
    code = "MODEL_TIMEOUT"
    message = "Generation took too long and was stopped."
    retryable = True


class QueueTimeoutError(AIError):
    code = "QUEUE_TIMEOUT"
    message = "The job waited too long in the queue and was cancelled."
    retryable = False


class OutputQualityError(AIError):
    code = "OUTPUT_QUALITY_REJECTED"
    message = "The generated image did not pass quality checks."
    retryable = True


class LicenseError(AIError):
    status_code = 503
    code = "MODEL_LICENSE_BLOCKED"
    message = "This AI engine is not available."
    retryable = False
