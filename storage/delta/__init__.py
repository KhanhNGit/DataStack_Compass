"""DataStack Compass — Delta Lake storage package."""

from storage.delta.schemas import SCHEMAS, create_delta_tables

__all__ = ["SCHEMAS", "create_delta_tables"]
