"""Render's managed PostgreSQL URL must work with our psycopg 3 dependency."""
from app.core.config import Settings


def test_render_postgres_url_uses_installed_psycopg_driver():
    url = "postgresql://kadoku:secret@example.internal:5432/kadoku?sslmode=require"
    assert Settings(database_url=url).database_url == (
        "postgresql+psycopg://kadoku:secret@example.internal:5432/kadoku?sslmode=require"
    )


def test_other_database_url_schemes_are_not_changed():
    for url in (
        "postgres://kadoku:secret@localhost:5432/kadoku",
        "postgresql+psycopg://kadoku:secret@localhost:5432/kadoku",
        "sqlite:///./local.db",
    ):
        got = Settings(database_url=url).database_url
        if url.startswith("postgres://"):
            assert got.startswith("postgresql+psycopg://")
        else:
            assert got == url
