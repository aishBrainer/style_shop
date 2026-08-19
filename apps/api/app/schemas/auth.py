"""Auth request/response schemas (§7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import MembershipRole, PlanTier, UserRole
from app.schemas.common import ORMModel

MIN_PASSWORD_LENGTH = 10


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    full_name: str | None = Field(default=None, max_length=160)

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        # Deliberately minimal: length is the property that actually matters,
        # and character-class rules mostly push users toward "Password1!".
        if v.strip() != v:
            raise ValueError("Password cannot start or end with whitespace.")
        if v.lower() in {"password12", "1234567890", "qwertyuiop"}:
            raise ValueError("Please choose a less common password.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class EmailVerifyRequest(BaseModel):
    token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: PlanTier
    credit_balance: int
    storage_quota_mb: int
    storage_used_bytes: int
    max_projects: int
    max_concurrent_jobs: int
    is_personal: bool


class MembershipOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    role: MembershipRole
    organization: OrganizationOut | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    avatar_url: str | None
    role: UserRole
    is_active: bool
    email_verified_at: datetime | None
    default_organization_id: uuid.UUID | None
    created_at: datetime


class SessionOut(BaseModel):
    user: UserOut
    organization: OrganizationOut
    memberships: list[MembershipOut] = []


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=160)


class DeleteAccountRequest(BaseModel):
    password: str | None = None
    confirm: str

    @field_validator("confirm")
    @classmethod
    def _must_confirm(cls, v: str) -> str:
        if v.strip().upper() != "DELETE":
            raise ValueError('Type "DELETE" to confirm account deletion.')
        return v
