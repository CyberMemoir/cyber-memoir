import pytest

from cyber_memoir.adapters import backup, storage


def test_backup_hash_verification_and_non_destructive_restore(env, tmp_path):
    key, _ = storage.put(b"synthetic evidence")
    destination = tmp_path / "backup"
    assert backup.export(destination) == 1
    assert backup.verify(destination)[0]["key"] == key
    with pytest.raises(ValueError, match="empty evidence"):
        backup.restore(destination)
    (destination / "objects" / key).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity"):
        backup.verify(destination)


def test_backup_rejects_traversal(env):
    with pytest.raises(ValueError):
        backup.valid_key("../../.env")
