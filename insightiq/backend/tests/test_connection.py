from core.data.connection import CONNECTION_SECRET_MASK, mask_connection, merge_connection


def test_mask_connection_hides_secrets_and_file_paths():
    masked = mask_connection(
        {
            "host": "db.local",
            "password": "secret",
            "access_key": "AKIA123",
            "files": {"sales": "/tmp/uploads/tenant/sales.csv"},
        }
    )
    assert masked["host"] == "db.local"
    assert masked["password"] == CONNECTION_SECRET_MASK
    assert masked["access_key"] == CONNECTION_SECRET_MASK
    assert masked["files"] == {"sales": "sales.csv"}


def test_merge_connection_preserves_secrets_when_omitted_or_masked():
    existing = {"host": "old.local", "password": "stored", "user": "reader"}
    merged = merge_connection(existing, {"host": "new.local", "password": CONNECTION_SECRET_MASK})
    assert merged == {"host": "new.local", "password": "stored", "user": "reader"}


def test_merge_connection_updates_secret_when_provided():
    existing = {"host": "db.local", "password": "old"}
    merged = merge_connection(existing, {"password": "new"})
    assert merged["password"] == "new"
