from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .storage import ConnectionFactory, _managed_connection

SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT NOW()
)
"""


@dataclass(slots=True, frozen=True)
class MigrationFile:
    version: str
    path: Path
    sql: str


class MigrationRunner:
    def __init__(self, connection_factory: ConnectionFactory, migrations_dir: Path) -> None:
        self._connection_factory = connection_factory
        self._migrations_dir = migrations_dir

    def apply_pending(self) -> list[str]:
        migration_files = self._load_migration_files()
        if not migration_files:
            return []

        with _managed_connection(self._connection_factory()) as connection:
            applied_versions = self._fetch_applied_versions(connection)
            newly_applied: list[str] = []

            for migration in migration_files:
                if migration.version in applied_versions:
                    continue
                with connection.cursor() as cursor:
                    cursor.execute(migration.sql)
                    cursor.execute(
                        "INSERT INTO public.schema_migrations (version) VALUES (%s)",
                        (migration.version,),
                    )
                newly_applied.append(migration.version)

            connection.commit()
        return newly_applied

    def _fetch_applied_versions(self, connection: Any) -> set[str]:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA_MIGRATIONS_SQL)
            cursor.execute("SELECT version FROM public.schema_migrations ORDER BY version")
            rows = cursor.fetchall()
        return {str(row[0]) for row in rows}

    def _load_migration_files(self) -> list[MigrationFile]:
        if not self._migrations_dir.exists():
            return []

        migration_files: list[MigrationFile] = []
        for path in sorted(self._migrations_dir.glob("*.sql")):
            migration_files.append(
                MigrationFile(
                    version=path.stem,
                    path=path,
                    sql=path.read_text(encoding="utf-8"),
                )
            )
        return migration_files
