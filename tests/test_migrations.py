def test_migration_upgrade_downgrade_and_metadata_match(alembic_runner):
    try:
        alembic_runner("downgrade", "5857005dfb78")
        # Upgrade an existing Day 3 DB without rewriting its applied revision.
        alembic_runner("upgrade", "a18010177bdd")
        assert "a18010177bdd" in alembic_runner("current")
    finally:
        alembic_runner("upgrade", "head")
    assert "b1a8de19275e" in alembic_runner("current")
    alembic_runner("check")
