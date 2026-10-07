import pytest

from media_omega.cli import _refresh, _report


@pytest.mark.parametrize("command", [_refresh, _report])
def test_read_command_missing_state_fails_without_creating_directory(tmp_path, command):
    missing = tmp_path / "missing-state"
    with pytest.raises(FileNotFoundError):
        command(str(missing))
    assert not missing.exists()
