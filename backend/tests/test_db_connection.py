from app.db import check_db_connection


def test_database_connection_succeeds():
    assert check_db_connection() is True
