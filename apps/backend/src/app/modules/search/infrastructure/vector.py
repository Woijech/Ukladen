import json

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "VECTOR"

    def bind_processor(self, dialect):
        return lambda value: json.dumps(list(value)) if value is not None else None

    def result_processor(self, dialect, coltype):
        return lambda value: tuple(json.loads(value)) if isinstance(value, str) else value


# Alembic must reflect the extension type to compare migration metadata.

ischema_names["vector"] = Vector
