from app.db import check_db_connection


def test_database_connection_succeeds():
    ok, error = check_db_connection()
    assert ok is True
    assert error is None
