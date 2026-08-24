"""Test: forgot credentials self-service (email OTP -> form ganti password -> redirect login).

Run from backend/ with the project venv:
    backend/.venv/bin/python backend/test_forgot_password.py

Covers:
  (a) request reset tanpa SMTP -> 503 fail-closed, TIDAK ada OTP di log;
      username tidak dikenal -> tetap 200 generik (anti user-enumeration);
      akun tanpa email -> juga generik.
  (b) mock SMTP sukses -> OTP terkirim ke email terdaftar & cocok dgn row
      pending; tidak ada OTP bocor ke stdout/stderr.
  (c) verify-otp: OTP salah -> 400 otp_invalid; OTP benar -> 200 + reset_token,
      OTP di-nol-kan (replay -> 400); resend setelah verify membatalkan token
      lama (confirm dgn token lama -> invalid_reset_token).
  (d) confirm: konfirmasi tidak cocok -> 400; password lemah -> 400 policy;
      sukses -> password baru aktif, password lama mati, SEMUA sesi lama
      dicabut; token sekali pakai (pakai ulang -> invalid_reset_token);
      audit PASSWORD_RESET_COMPLETED tercatat.
"""
import io
import os
import sys
import contextlib

# Isolated SQLite DB for this test run
os.environ["DATABASE_URL"] = "sqlite:///./test_oran_forgot.db"
for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
    os.environ.pop(k, None)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402  (imports auth/email_service/database via main)

client = TestClient(main.app)


class FakeSMTP:
    """Mock smtplib.SMTP yang mencatat pesan terkirim."""

    last = {}

    def __init__(self, host, port=None, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, u, p):
        pass

    def sendmail(self, frm, to, msg):
        FakeSMTP.last = {"from": frm, "to": to, "msg": msg}


def _enable_fake_smtp():
    import smtplib
    os.environ.update({
        "SMTP_HOST": "smtp.test.local",
        "SMTP_PORT": "587",
        "SMTP_USER": "tester@test.local",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM": "noreply@test.local",
    })
    orig = smtplib.SMTP
    smtplib.SMTP = FakeSMTP
    return orig


def _disable_fake_smtp(orig):
    import smtplib
    smtplib.SMTP = orig
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        os.environ.pop(k, None)


def _silent_post(path, json_body):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        r = client.post(path, json=json_body)
    return r, buf.getvalue()


def _make_user_with_session(username, email, password):
    """Buat user aktif (jalur admin, tanpa verifikasi) + satu sesi aktif."""
    import auth
    auth.register_user(username, password, full_name=username.title(), email=email)
    tok = auth.authenticate(username, password, ip="127.0.0.1")
    assert tok, f"seed login failed for {username}"
    return tok


def test_a_request_no_smtp_failclosed_and_generic():
    # Seed dua user: satu dengan email, satu tanpa email
    import auth
    auth.register_user("agung", "Startpass1", full_name="Agung", email="agung@example.com")
    auth.register_user("tanpaemail", "Startpass1", full_name="No Email", email="")

    # (1) akun valid tapi SMTP mati -> 503 fail-closed
    r, out = _silent_post("/api/auth/forgot-password", {"username": "agung"})
    assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
    d = r.json()["detail"]
    assert d["reason"] == "email_service_unavailable" and d["ok"] is False, d
    # Row pending harus sudah dibuat sebelum kirim (retryable via resend)
    with auth.get_db_session() as db:
        row = db.query(auth.PendingPasswordResetModel).filter_by(username="agung").first()
        assert row is not None, "pending reset harus dibuat walau SMTP gagal"
        otp = row.otp_code
    assert otp not in out, f"OTP LEAKED to log: {otp!r}"

    # (2) username tidak dikenal -> TETAP 200 generik (anti-enumeration)
    r_unknown, _ = _silent_post("/api/auth/forgot-password", {"username": "hantu999"})
    assert r_unknown.status_code == 200, r_unknown.text
    msg_unknown = r_unknown.json()["message"]

    # (3) akun tanpa email -> juga generik, sama pesannya
    r_noemail, _ = _silent_post("/api/auth/forgot-password", {"username": "tanpaemail"})
    assert r_noemail.status_code == 200, r_noemail.text
    assert r_noemail.json()["message"] == msg_unknown, (
        "pesan utk akun tanpa email beda dgn akun tak dikenal -> bocor enumerasi"
    )

    print("PASS (a): tanpa SMTP -> 503 fail-closed (OTP tak bocor), "
          "username tak dikenal & akun tanpa email -> respons generik identik")


def test_b_request_with_mocked_smtp_sends_matching_otp():
    orig = _enable_fake_smtp()
    try:
        r, out = _silent_post("/api/auth/forgot-password", {"username": "agung"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        sent = FakeSMTP.last
        assert sent.get("to") == ["agung@example.com"], sent
        assert "reset code" in sent["msg"].lower(), "bukan email reset password"

        import auth, re
        m = re.search(r"\b(\d{6})\b", sent["msg"])
        assert m, "tidak ada kode 6 digit di payload SMTP"
        with auth.get_db_session() as db:
            row = db.query(auth.PendingPasswordResetModel).filter_by(username="agung").one()
            stored_otp = row.otp_code
            assert row.email == "agung@example.com"
        assert m.group(1) == stored_otp, "OTP di email != OTP tersimpan"
        assert m.group(1) not in out, "OTP bocor ke log pada jalur sukses?!"
    finally:
        _disable_fake_smtp(orig)
    print("PASS (b): mock SMTP -> email reset terkirim ke alamat terdaftar, "
          "OTP cocok dgn pending, tak ada OTP di log")


def test_c_verify_otp_and_single_use_token():
    import auth

    # OTP salah
    r_bad, _ = _silent_post(
        "/api/auth/forgot-password/verify-otp",
        {"username": "agung", "otp_code": "000000"},
    )
    assert r_bad.status_code == 400 and r_bad.json()["detail"] == "otp_invalid", r_bad.text

    # Ambil OTP beneran dari DB, verifikasi
    with auth.get_db_session() as db:
        otp = db.query(auth.PendingPasswordResetModel).filter_by(username="agung").one().otp_code
    r_ok, _ = _silent_post(
        "/api/auth/forgot-password/verify-otp",
        {"username": "agung", "otp_code": otp},
    )
    assert r_ok.status_code == 200, r_ok.text
    token = r_ok.json()["reset_token"]
    assert token and r_ok.json()["username"] == "agung"

    # Replay OTP yang sama harus gagal (OTP dinolkan saat verifikasi)
    r_replay, _ = _silent_post(
        "/api/auth/forgot-password/verify-otp",
        {"username": "agung", "otp_code": otp},
    )
    assert r_replay.status_code == 400, "OTP masih bisa dipakai ulang!"

    # Resend setelah verify -> token lama hangus
    orig = _enable_fake_smtp()
    try:
        r_resend, _ = _silent_post(
            "/api/auth/forgot-password/resend-otp", {"username": "agung"}
        )
    finally:
        _disable_fake_smtp(orig)
    assert r_resend.status_code == 200, r_resend.text

    r_oldtok, _ = _silent_post(
        "/api/auth/forgot-password/confirm",
        {"reset_token": token, "new_password": "Newpass123", "confirm_password": "Newpass123"},
    )
    assert r_oldtok.status_code == 400 and r_oldtok.json()["detail"] == "invalid_reset_token", (
        f"token lama masih hidup setelah resend: {r_oldtok.text}"
    )
    print("PASS (c): OTP salah ditolak, OTP benar -> token, replay OTP gagal, "
          "resend membatalkan token lama")


def test_d_confirm_full_flow_and_revocation():
    import auth

    # User kedua + sesi aktif sebelum reset
    sess_tok = _make_user_with_session("dewi", "dewi@example.com", "Oldpassword1")

    orig = _enable_fake_smtp()
    try:
        r1, _ = _silent_post("/api/auth/forgot-password", {"username": "dewi"})
        assert r1.status_code == 200, r1.text
        with auth.get_db_session() as db:
            otp = db.query(auth.PendingPasswordResetModel).filter_by(username="dewi").one().otp_code
        r2, _ = _silent_post(
            "/api/auth/forgot-password/verify-otp",
            {"username": "dewi", "otp_code": otp},
        )
        assert r2.status_code == 200, r2.text
        token = r2.json()["reset_token"]

        # Konfirmasi tidak cocok
        r_mm, _ = _silent_post(
            "/api/auth/forgot-password/confirm",
            {"reset_token": token, "new_password": "Newpass123", "confirm_password": "Other999"},
        )
        assert r_mm.status_code == 400 and r_mm.json()["detail"] == "passwords_do_not_match", r_mm.text

        # Password lemah (policy)
        r_weak, _ = _silent_post(
            "/api/auth/forgot-password/confirm",
            {"reset_token": token, "new_password": "lewat123", "confirm_password": "lewat123"},
        )
        assert r_weak.status_code == 400 and "password_" in r_weak.json()["detail"], r_weak.text

        # Sukses
        r_ok, _ = _silent_post(
            "/api/auth/forgot-password/confirm",
            {"reset_token": token, "new_password": "Newpassword2", "confirm_password": "Newpassword2"},
        )
        assert r_ok.status_code == 200, r_ok.text
        body = r_ok.json()
        assert body["ok"] is True and body["redirect"] == "/login", body
    finally:
        _disable_fake_smtp(orig)

    # Sesi lama harus sudah dicabut
    assert auth._session_for(sess_tok) is None, "sesi lama tidak dicabut setelah reset!"

    # Password lama mati, baru hidup; pending row terhapus (token hangus)
    assert client.post("/api/auth/login", json={"username": "dewi", "password": "Oldpassword1"}).status_code == 401
    r_new = client.post("/api/auth/login", json={"username": "dewi", "password": "Newpassword2"})
    assert r_new.status_code == 200, r_new.text

    with auth.get_db_session() as db:
        left = db.query(auth.PendingPasswordResetModel).filter_by(username="dewi").first()
        assert left is None, "row pending harus dihapus setelah confirm"
        from models import AuditLogModel
        audits = db.query(AuditLogModel).filter(
            AuditLogModel.username == "dewi",
            AuditLogModel.action == "PASSWORD_RESET_COMPLETED",
        ).all()
    assert audits, "audit PASSWORD_RESET_COMPLETED tidak tercatat"

    # Token sekali pakai: pakai ulang token yang sudah dikonsumsi
    r_reuse, _ = _silent_post(
        "/api/auth/forgot-password/confirm",
        {"reset_token": token, "new_password": "Another123", "confirm_password": "Another123"},
    )
    assert r_reuse.status_code == 400, "token bisa dipakai dua kali!"
    print("PASS (d): confirm lengkap — mismatch/policy ditolak, sukses ganti password, "
          "sesi lama dicabut, login lama mati/baru hidup, audit tercatat, token sekali pakai")


def test_e_admin_without_email_stays_generic():
    # admin seed tidak punya email -> harus generik 200, bukan error
    r, _ = _silent_post("/api/auth/forgot-password", {"username": "admin"})
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    print("PASS (e): permintaan reset utk akun admin (tanpa email) tetap generik")


if __name__ == "__main__":
    failures = []
    for fn in [
        test_a_request_no_smtp_failclosed_and_generic,
        test_b_request_with_mocked_smtp_sends_matching_otp,
        test_c_verify_otp_and_single_use_token,
        test_d_confirm_full_flow_and_revocation,
        test_e_admin_without_email_stays_generic,
    ]:
        try:
            fn()
        except AssertionError as e:
            failures.append((fn.__name__, str(e)))
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures.append((fn.__name__, repr(e)))
            print(f"ERROR {fn.__name__}: {e!r}")
    if failures:
        print(f"\n{len(failures)} test GAGAL")
        sys.exit(1)
    print("\nSEMUA TEST PASS (5/5)")
