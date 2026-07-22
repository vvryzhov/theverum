import enum
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Role(str, enum.Enum):
    CLIENT = "CLIENT"
    EXPERT = "EXPERT"
    REVIEWER = "REVIEWER"
    ADMIN = "ADMIN"

class CaseStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    NEEDS_MEDIA = "NEEDS_MEDIA"
    IN_REVIEW = "IN_REVIEW"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class Verdict(str, enum.Enum):
    AUTHENTIC = "AUTHENTIC"
    NOT_AUTHENTIC = "NOT_AUTHENTIC"
    INCONCLUSIVE = "INCONCLUSIVE"
    PHYSICAL_REVIEW = "PHYSICAL_REVIEW"

class CertificateStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    UNDER_REVIEW = "UNDER_REVIEW"
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default=Role.CLIENT.value)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AuthenticationCase(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expert_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(80), default="Сумка")
    brand: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(160), default="Не указана")
    color: Mapped[str] = mapped_column(String(100), default="Не указан")
    material: Mapped[str] = mapped_column(String(160), default="Не указан")
    serial_display: Mapped[str] = mapped_column(String(120), default="Не предусмотрен / не указан")
    identifier_mode: Mapped[str] = mapped_column(String(40), default="NONE")
    identifier_notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default=CaseStatus.SUBMITTED.value)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    conclusion: Mapped[str] = mapped_column(Text, default="")
    notable_features: Mapped[str] = mapped_column(Text, default="")
    photo_path: Mapped[str] = mapped_column(String(500), default="")
    internal_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Certificate(Base):
    __tablename__ = "certificates"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), unique=True)
    certificate_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    public_token: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default=CertificateStatus.ACTIVE.value)
    version: Mapped[int] = mapped_column(Integer, default=1)
    pdf_path: Mapped[str] = mapped_column(String(500), default="")
    report_path: Mapped[str] = mapped_column(String(500), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revocation_reason: Mapped[str] = mapped_column(Text, default="")
    case: Mapped[AuthenticationCase] = relationship()

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="system")
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PriceBlock(Base):
    __tablename__ = "price_blocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    price_label: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    features: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
