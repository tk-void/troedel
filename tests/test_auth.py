from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from troedel import auth
from troedel.auth import Auth, PasswordRejected, Throttle
from troedel.db import DB

PASSWORD = "correct horse battery"


@pytest.fixture
def a(db: DB) -> Auth:
    a = Auth(db, setup_code="ABCD-EFGH-JKLM")
    a.setup("abcd efgh jklm", PASSWORD)
    return a


class TestSetup:
    def test_needs_the_code_from_the_log(self, db: DB) -> None:
        a = Auth(db)
        assert not a.configured and len(a.setup_code) == 14
        with pytest.raises(PermissionError):
            a.setup("AAAA-AAAA-AAAA", PASSWORD)
        assert not a.configured

    def test_code_is_forgiving_about_case_and_dashes(self, db: DB) -> None:
        a = Auth(db, setup_code="ABCD-EFGH-JKLM")
        a.setup(" abcdefghjklm ", PASSWORD)
        assert a.configured and a.setup_code == ""

    def test_only_once(self, a: Auth) -> None:
        with pytest.raises(PermissionError):
            a.setup("ABCD-EFGH-JKLM", "another password")

    def test_no_code_once_a_password_exists(self, a: Auth, db: DB) -> None:
        assert Auth(db).setup_code == ""

    @pytest.mark.parametrize("password", ["short", "x" * 300])
    def test_password_rules(self, db: DB, password: str) -> None:
        a = Auth(db, setup_code="ABCD-EFGH-JKLM")
        with pytest.raises(PasswordRejected):
            a.setup("ABCD-EFGH-JKLM", password)
        assert not a.configured

    def test_stored_as_argon2id_not_in_the_clear(self, a: Auth, db: DB) -> None:
        stored = db.private("password")
        assert stored.startswith("$argon2id$") and PASSWORD not in stored
        assert "password" not in db.settings() and "_password" not in db.settings()


class TestSessions:
    def test_login_and_check(self, a: Auth) -> None:
        token = a.login(PASSWORD, "client")
        assert token and a.check(token)
        assert a.login("wrong password!", "client") is None
        assert not a.check("made-up") and not a.check("")

    def test_database_holds_only_a_hash_of_the_token(self, a: Auth, db: DB) -> None:
        token = a.login(PASSWORD, "client")
        raw = sqlite3.connect(db.path).execute("SELECT token_hash FROM session").fetchall()
        assert raw == [(auth.hash_token(token),)] and token not in raw[0][0]

    def test_logout(self, a: Auth) -> None:
        token = a.login(PASSWORD, "client")
        a.logout(token)
        assert not a.check(token)

    def test_idle_sessions_expire(self, a: Auth, db: DB) -> None:
        token = a.login(PASSWORD, "client")
        old = (datetime.now().astimezone() - auth.SESSION_IDLE - timedelta(days=1)).isoformat()
        db.con.execute("UPDATE session SET last_seen=?", (old,))
        assert not a.check(token)
        assert db.session(auth.hash_token(token)) is None

    def test_changing_the_password_ends_the_other_sessions(self, a: Auth) -> None:
        mine, other = a.login(PASSWORD, "a"), a.login(PASSWORD, "b")
        assert not a.change_password("wrong password!", "new password 123", keep=mine)
        assert a.change_password(PASSWORD, "new password 123", keep=mine)
        assert a.check(mine) and not a.check(other)
        assert a.verify("new password 123") and not a.verify(PASSWORD)

    def test_reset_forgets_everything(self, a: Auth) -> None:
        token = a.login(PASSWORD, "client")
        code = a.reset()
        assert code and not a.configured and not a.check(token)
        a.setup(code, "a brand new password")
        assert a.verify("a brand new password")

    def test_helper_token_is_its_own_kind(self, a: Auth) -> None:
        session, helper = a.login(PASSWORD, "client"), a.new_helper_token()
        assert a.check_helper(helper) and not a.check(helper)
        assert not a.check_helper(session)
        second = a.new_helper_token()
        assert a.check_helper(second) and a.check_helper(helper), "one per device, both stay valid"
        assert a.helper_count() == 2
        a.revoke_helper()
        assert not a.check_helper(second) and not a.check_helper(helper) and a.check(session)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class TestThrottle:
    def test_five_free_then_growing_waits(self) -> None:
        clock = Clock()
        t = Throttle(clock)
        for _ in range(4):
            t.failed("x")
        assert t.retry_after("x") == 0
        t.failed("x")
        first = t.retry_after("x")
        assert first > 0
        clock.t += first
        assert t.retry_after("x") == 0
        t.failed("x")
        assert t.retry_after("x") > first

    def test_wait_is_capped(self) -> None:
        t = Throttle(Clock())
        for _ in range(40):
            t.failed("x")
        assert t.retry_after("x") <= Throttle.CAP + 1

    def test_other_clients_are_not_punished(self) -> None:
        t = Throttle(Clock())
        for _ in range(8):
            t.failed("x")
        assert t.retry_after("x") > 0 and t.retry_after("y") == 0

    def test_many_addresses_trigger_the_overall_pause(self) -> None:
        t = Throttle(Clock())
        for i in range(Throttle.GLOBAL_LIMIT + 1):
            t.failed(f"client-{i}")
        assert t.retry_after("someone-new") > 0

    def test_success_clears_the_count(self) -> None:
        t = Throttle(Clock())
        for _ in range(4):
            t.failed("x")
        t.succeeded("x")
        t.failed("x")
        assert t.retry_after("x") == 0

    def test_login_counts_failures(self, a: Auth) -> None:
        for _ in range(Throttle.FREE):
            assert a.login("wrong password!", "x") is None
        assert a.throttle.retry_after("x") > 0
