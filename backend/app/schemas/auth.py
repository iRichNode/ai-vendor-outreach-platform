from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    email: EmailStr | None = None

    @field_validator("username")
    @classmethod
    def _username_safe(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", v):
            raise ValueError("Username may only contain letters, digits, dot, dash, underscore")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str | None = None
    is_superuser: bool


class AuthStatus(BaseModel):
    authenticated: bool
    user: UserOut | None = None