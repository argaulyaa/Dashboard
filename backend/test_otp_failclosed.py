"""Lightweight test: fail-closed email OTP + SMTP success path.

Run from backend/ with the project venv:
    /tmp/oran_venv/bin/python /tmp/oran_check/backend/test_otp_failclosed.py

Covers:
  (a) No SMTP_HOST -> POST /api/auth/register returns 503 AND captured
      stdout/stderr contains NO OTP code.
  (b) smtplib.SMTP monkeypatched to a fake that succeeds -> register 200 ok,
      fake SMTP received the message containing the OTP.
  (c) resend-otp: 503 without SMTP, 200 ok with mocked SMTP.
  (d) verify-email flow untouched: mocked-SMTP register then verify -> token.
"""
import io
import os
import sys
import contextlib

# Isolated SQLite DB for this test run
os.environ["DATABASE_URL"] = "sqlite:///./test_oran_otp.db"
for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
    os.environ.pop(k, None)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402  (imports auth/email_service/database via main)

client = TestClient(main.app)
REG = {"username": "budi", "email": "budi@example.com",
       "password": "Password123", "full_name": "Budi Test"}


def _register():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        r = client.post("/api/auth/register", json=REG)
    return r, buf.getvalue()


def test_a_no_smtp_host_register_503_no_otp_leak():
    r, out = _register()
    assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
    d = r.json()["detail"]
    assert d["ok"] is False and d["reason"] == "email_service_unavailable", d
    assert d["message"] == "Gagal mengirim email verifikasi. Coba lagi nanti."
    # Pending row must exist (retryable) but account NOT active yet
    import auth
    with auth.get_db_session() as db:
        pend = db.query(auth.PendingRegistrationModel).filter_by(username="budi").first()
        assert pend is not None, "pending registration should be created"
        otp = pend.otp_code
        users = db.query(auth.UserModel).filter_by(username="budi").first()
    assert users is None, "account must NOT be active before OTP verify"
    # THE critical assertion: no OTP code anywhere in stdout/stderr
    assert otp not in out, f"OTP LEAKED to log: {otp!r}"
    assert "Email Fallback" not in out and "OTP" not in out.replace("OTP sent", "")
    print("PASS (a): register tanpa SMTP_HOST -> 503 email_service_unavailable, "
          f"pending dibuat (otp={otp!r} TIDAK muncul di log)")


def test_b_mocked_smtp_register_200():
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port=None, timeout=None):
            sent["host"], sent["port"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            sent["starttls"] = True

        def login(self, u, p):
            sent["login"] = (u, p)

        def sendmail(self, frm, to, msg):
            sent["from"], sent["to"], sent["msg"] = frm, to, msg

    import smtplib
    orig = smtplib.SMTP
    os.environ["SMTP_HOST"] = "smtp.test.local"
    os.environ["SMTP_PORT"] = "587"
    os.environ["SMTP_USER"] = "tester@test.local"
    os.environ["SMTP_PASSWORD"] = "secret"
    os.environ["SMTP_FROM"] = "noreply@test.local"
    # unique username biar nggak bentrok dgn pending dari test (a)
    reg2 = dict(REG, username="siti", email="siti@example.com")
    try:
        smtplib.SMTP = FakeSMTP
        r, out = None, ""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r = client.post("/api/auth/register", json=reg2)
        out = buf.getvalue()
    finally:
        smtplib.SMTP = orig
        for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
            os.environ.pop(k, None)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    assert r.json()["ok"] is True and "verify" in r.json()["message"].lower()
    assert sent.get("starttls") and sent.get("msg"), f"SMTP not exercised properly: {sent}"
    assert sent["to"] == ["siti@example.com"]
    # OTP yang terkirim via SMTP harus sama dgn yg tersimpan di pending
    import auth, re
    m = re.search(r"\b(\d{6})\b", sent["msg"])
    assert m, "no 6-digit code in SMTP payload"
    with auth.get_db_session() as db:
        pend = db.query(auth.PendingRegistrationModel).filter_by(username="siti").one()
        stored_otp = pend.otp_code
    assert m.group(1) == stored_otp, "OTP in email != OTP stored"
    assert m.group(1) not in out, "OTP leaked to log even on success path?!"
    print("PASS (b): register dgn mock SMTP sukses -> 200 ok, email berisi OTP "
          "yang sama dgn pending, tidak ada OTP di log")


def test_c_resend_otp_paths():
    import smtplib

    class FakeSMTPBase:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def sendmail(self, *a):
            pass

    # (c1) resend tanpa SMTP_HOST -> 503
    r = client.post("/api/auth/resend-otp", json={"username": "budi"})
    assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
    assert r.json()["detail"]["reason"] == "email_service_unavailable"

    # (c2) resend dengan mock SMTP -> 200
    orig = smtplib.SMTP
    os.environ["SMTP_HOST"] = "smtp.test.local"
    try:
        smtplib.SMTP = FakeSMTPBase
        r = client.post("/api/auth/resend-otp", json={"username": "budi"})
    finally:
        smtplib.SMTP = orig
        os.environ.pop("SMTP_HOST", None)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    print("PASS (c): resend-otp tanpa SMTP -> 503; dengan mock SMTP -> 200")


def test_d_verify_flow_untouched():
    """Setelah resend sukses (mock SMTP), verify OTP beneran bikin akun."""
    import auth
    with auth.get_db_session() as db:
        otp = db.query(auth.PendingRegistrationModel).filter_by(username="budi").one().otp_code
    r = client.post("/api/auth/verify-email", json={"username": "budi", "otp_code": otp})
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert body["ok"] is True and body["user"] == "budi" and body["role"] == "viewer"
    assert body.get("token"), "login token harus dikembalikan"
    with auth.get_db_session() as db:
        u = db.query(auth.UserModel).filter_by(username="budi").one()
        assert u.role == "viewer"
    print("PASS (d): verify-email alur lama utuh -> akun aktif + token viewer")


if __name__ == "__main__":
    test_a_no_smtp_host_register_503_no_otp_leak()
    test_b_mocked_smtp_register_200()
    test_c_resend_otp_paths()
    test_d_verify_flow_untouched()
    print("\nALL TESTS PASSED")
