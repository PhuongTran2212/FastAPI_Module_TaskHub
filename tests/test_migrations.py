def test_migration_upgrade_downgrade_and_metadata_match(alembic_runner):
    try:
        alembic_runner("downgrade", "5857005dfb78")
        assert "5857005dfb78" in alembic_runner("current")
    finally:
        alembic_runner("upgrade", "head")
    assert "0d97a0968e0b" in alembic_runner("current")
    alembic_runner("check")
