from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class AppSetting(UUIDPkMixin, TimestampMixin, Base):
    """Key/value application settings editable from the dashboard."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(16), default="str", nullable=False)  # str|int|float|bool|json
    section: Mapped[str] = mapped_column(String(32), default="general", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)