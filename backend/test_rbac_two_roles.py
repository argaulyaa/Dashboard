"""Test RBAC dua role ('user' | 'admin') — simplifikasi dari 3 role lama.

Run from backend/ with the project venv:
    /tmp/oran_venv/bin/python /tmp/oran_check/backend/test_rbac_two_roles.py

Skenario (keputusan owner):
  (a) Self-register (OTP) -> akun selalu role 'user'.
  (b) Admin login -> GET /api/audit-logs 200.
  (c) User biasa -> GET /api/audit-logs 403 (lubang keamanan ditutup).
  (d) User biasa create reservation -> sukses (setara engineer lama).
  (e) User biasa activate + deactivate provider -> sukses.
  (f) User biasa PUT /api/auth/users/{x}/role -> 403.
  (g) Admin PUT role 'user' -> 'admin' OK; nilai legacy 'engineer' -> 400;
      efek live: user yang dipromote langsung boleh baca audit log.
  (h) Migrasi lazy: role legacy 'engineer'/'viewer'/tak dikenal dibaca
      'user'; hanya 'admin' yang diperlakukan istimewa.
"""
import os
import time

# Isolated SQLite DB untuk run test ini (tabel baru auto dibikin via create_all)
os.environ["DATABASE_URL"] = "sqlite:///./test_oran_rbac.db"
for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
    os.environ.pop(k, None)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402  (imports auth/database/models via main)
import auth  # noqa: E402

client = TestClient(main.app)


def _login(username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login {username} gagal: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _register_via_otp(username):
    """Self-register penuh tanpa SMTP nyata: OTP di-intercept dari argumen."""
    captured = {}
    orig = auth.send_verification_email
    auth.send_verification_email = lambda email, code, uname="": (
        captured.update({"code": code}) or "sent"
    )
    try:
        r = client.post("/api/auth/register", json={
            "full_name": f"User {username}",
            "username": username,
            "email": f"{username}@example.com",
            "password": "Startpass1",
        })
        assert r.status_code == 200, r.text
        v = client.post("/api/auth/verify-email", json={
            "username": username, "otp_code": captured["code"],
        })
        assert v.status_code == 200, v.text
        body = v.json()
        return body, {"Authorization": f"Bearer {body['token']}"}
    finally:
        auth.send_verification_email = orig


ADMIN = _login("admin", "admin")


def test_a_self_register_defaults_to_user():
    global BUDI, BUDI_HDR
    BUDI, BUDI_HDR = _register_via_otp("budi")
    assert BUDI["role"] == "user", BUDI
    with auth.get_db_session() as db:
        row = db.query(auth.UserModel).filter_by(username="budi").first()
        # Nilai legacy apa pun dibaca 'user' oleh get_user_role
        assert auth._normalize_role(row.role) == "user", row.role
    print("PASS (a): self-register -> role 'user' (bukan viewer/engineer)")


def test_b_admin_can_read_audit_logs():
    r = client.get("/api/audit-logs", headers=ADMIN)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
    print(f"PASS (b): admin GET audit-logs -> 200 ({len(r.json())} entri)")


def test_c_user_cannot_read_audit_logs():
    r = client.get("/api/audit-logs", headers=BUDI_HDR)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    print(f"PASS (c): user biasa GET audit-logs -> 403 ({r.json()['detail'].get('reason')})")


def test_d_user_can_create_reservation():
    comps = client.get("/api/core/components").json()
    comp_id = comps[0]["id"]
    now = time.time()
    r = client.post(
        f"/api/core/components/{comp_id}/reservation",
        json={"user": "budi", "start_at": now + 60, "end_at": now + 3660, "note": "rbac test"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"] == "budi", r.json()
    print(f"PASS (d): user biasa create reservation '{comp_id}' -> sukses")


def test_e_user_can_activate_and_deactivate_provider():
    r = client.post("/api/core/activate-provider", headers=BUDI_HDR, json={"provider": "open5gs"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["username"] == "budi", r.text
    g = client.get("/api/core/active-provider", headers=BUDI_HDR).json()
    assert g["provider"] == "open5gs", g
    d = client.post("/api/core/deactivate-provider", headers=BUDI_HDR)
    assert d.status_code == 200 and d.json()["ok"] is True, d.text
    g2 = client.get("/api/core/active-provider", headers=BUDI_HDR).json()
    assert g2["provider"] is None, g2
    print("PASS (e): user biasa activate+deactivate provider -> sukses")


def test_f_user_cannot_change_roles():
    auth.register_user("charlie", "Startpass1", full_name="Charlie", email="charlie@example.com")
    r = client.put("/api/auth/users/charlie/role", headers=BUDI_HDR, json={"role": "admin"})
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    assert "Only admin" in str(r.json()["detail"]), r.json()
    print("PASS (f): user biasa PUT role orang lain -> 403")


def test_g_admin_changes_roles():
    # Nilai legacy tidak lagi diterima
    r_bad = client.put("/api/auth/users/budi/role", headers=ADMIN, json={"role": "engineer"})
    assert r_bad.status_code == 400, r_bad.text
    assert "'user' or 'admin'" in r_bad.json()["detail"], r_bad.json()

    # Promote budi -> admin
    r_up = client.put("/api/auth/users/budi/role", headers=ADMIN, json={"role": "admin"})
    assert r_up.status_code == 200 and r_up.json()["role"] == "admin", r_up.text
    # Efek live: token lama budi (sebelum promote) langsung dapat akses audit
    r_audit = client.get("/api/audit-logs", headers=BUDI_HDR)
    assert r_audit.status_code == 200, r_audit.text

    # Demote balik -> akses audit hilang lagi
    r_down = client.put("/api/auth/users/budi/role", headers=ADMIN, json={"role": "user"})
    assert r_down.status_code == 200 and r_down.json()["role"] == "user", r_down.text
    r_denied = client.get("/api/audit-logs", headers=BUDI_HDR)
    assert r_denied.status_code == 403, r_denied.text
    print("PASS (g): admin toggle user<->admin OK; 'engineer' ditolak 400; efek live terverifikasi")


def test_h_lazy_migration_of_legacy_roles():
    def _set_role_raw(username, role):
        """Set kolom role mentah via session tersendiri (langsung commit)."""
        with auth.get_db_session() as db:
            u = db.query(auth.UserModel).filter_by(username=username).first()
            u.role = role

    # Simulasi baris legacy dari DB lama yang belum dimigrasi
    for legacy, expected in (("engineer", "user"), ("viewer", "user"),
                             ("ENGINEER", "user"), ("", "user"),
                             ("weird", "user"), ("admin", "admin")):
        _set_role_raw("charlie", legacy)
        got = auth.get_user_role("charlie")
        assert got == expected, (legacy, got)

    # Kolom role NOT NULL di DB — kasus NULL divalidasi di level fungsi
    assert auth._normalize_role(None) == "user"
    assert auth._normalize_role("") == "user"

    # Kembalikan ke nilai legacy lalu pastikan login menormalkan ke 'user'
    _set_role_raw("charlie", "engineer")
    lr = client.post("/api/auth/login", json={"username": "charlie", "password": "Startpass1"}).json()
    assert lr["role"] == "user", lr
    # Seed admin memakai role 'admin'
    with auth.get_db_session() as db:
        a = db.query(auth.UserModel).filter_by(username="admin").first()
        assert a.role == "admin", a.role
    print("PASS (h): migrasi lazy engineer/viewer/unknown -> 'user'; admin tetap admin")


if __name__ == "__main__":
    test_a_self_register_defaults_to_user()
    test_b_admin_can_read_audit_logs()
    test_c_user_cannot_read_audit_logs()
    test_d_user_can_create_reservation()
    test_e_user_can_activate_and_deactivate_provider()
    test_f_user_cannot_change_roles()
    test_g_admin_changes_roles()
    test_h_lazy_migration_of_legacy_roles()
    print("\nALL TESTS PASSED (RBAC 2-role)")
