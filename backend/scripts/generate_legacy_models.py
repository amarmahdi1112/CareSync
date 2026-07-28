"""Generate read-only SQLAlchemy mappings from the live legacy schema.

The connection is forced read-only by ``Database``. Credentials are loaded from the
ignored ``.env`` file and are never written to the generated source.
"""

from pathlib import Path

from sqlacodegen.generators import DeclarativeGenerator
from sqlalchemy import MetaData

from app.core.config import get_settings
from app.db.session import Database

OUTPUT = Path(__file__).resolve().parents[1] / "app" / "models" / "generated_legacy.py"


def main() -> None:
    settings = get_settings()
    if not settings.database_read_only:
        raise RuntimeError("Model generation requires DATABASE_READ_ONLY=true")

    database = Database(settings)
    try:
        metadata = MetaData()
        metadata.reflect(database.engine, schema=None, views=False)
        generator = DeclarativeGenerator(metadata, database.engine, set())
        code = generator.generate()
        OUTPUT.write_text(
            '"""Generated compatibility mappings. Do not edit by hand."""\n\n' + code,
            encoding="utf-8",
        )
        print(f"Generated {len(metadata.tables)} table mappings")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
