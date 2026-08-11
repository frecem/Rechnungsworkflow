import pytest

from app.services import login_guard


@pytest.fixture(autouse=True)
def reset_guard():
    login_guard.register_success()
    yield
    login_guard.register_success()


def test_not_locked_initially():
    assert login_guard.is_locked() is False


def test_locks_after_max_attempts():
    for _ in range(login_guard.MAX_ATTEMPTS - 1):
        login_guard.register_failure()
        assert login_guard.is_locked() is False

    login_guard.register_failure()
    assert login_guard.is_locked() is True


def test_success_resets_failure_count():
    for _ in range(login_guard.MAX_ATTEMPTS - 1):
        login_guard.register_failure()
    login_guard.register_success()

    login_guard.register_failure()
    assert login_guard.is_locked() is False


def test_success_clears_existing_lock():
    for _ in range(login_guard.MAX_ATTEMPTS):
        login_guard.register_failure()
    assert login_guard.is_locked() is True

    login_guard.register_success()
    assert login_guard.is_locked() is False


def test_seconds_until_unlock_decreases_to_zero_when_not_locked():
    assert login_guard.seconds_until_unlock() == 0
