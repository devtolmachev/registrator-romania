from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB, INTEGER
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase): ...


class ListUsers(Base):
    __tablename__ = "list_users"

    id: Mapped[int] = mapped_column(
        INTEGER, primary_key=True, autoincrement=True
    )
    user_data: Mapped[dict] = mapped_column(JSONB, primary_key=False, nullable=False)
    registration_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
