from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Text, func, literal_column
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MaterialSearchDocumentModel(Base):
    __tablename__ = "search_material_documents"

    material_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    body: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        ForeignKeyConstraint(
            ["material_id", "user_id"],
            ["materials.id", "materials.user_id"],
            ondelete="CASCADE",
            name="fk_search_material_owner",
        ),
        CheckConstraint("octet_length(body) <= 2097152", name="ck_search_material_size"),
        Index("ix_search_material_owner", "user_id", "material_id"),
        Index(
            "ix_search_material_body",
            func.ukladen_search_vector(literal_column("''"), body),
            postgresql_using="gin",
        ),
    )
