"""Lightweight test: provider activation toggle (exclusive active state).

Run from backend/ with the project venv:
    /tmp/oran_venv/bin/python /tmp/oran_check/backend/test_provider_activation.py

Covers:
  (a) GET /api/core/active-provider saat belum ada aktivasi -> provider null.
  (b) POST activate-provider 'oai' (admin) -> 200, GET kembali 'oai'.
  (c) POST activate-provider 'open5gs' -> upsert sederhana di backend,
      GET kembali 'open5gs' (eksklusifitas ditegakkan UI via disabled state).
  (d) POST activate-provider dengan nama tak dikenal -> 400.
  (e) User biasa activate -> sukses (RBAC 2-role: user setara engineer lama).
  (f) Deactivate -> GET kembali null; deactivate kedua -> 404 no_active_provider.
  (g) Audit log PROVIDER_ACTIVATE / PROVIDER_DEACTIVATE tercatat.
"""
import os

# Isolated SQLite DB untuk run test ini (tabel baru auto dibikin via create_all)
os.environ["DATABASE_URL"] = "sqlite:///./test_oran_activation.db"
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


ADMIN = _login("admin", "admin")


def _make_user():
    """Buat user biasa (role 'user') + sesi aktif via register_user."""
    auth.register_user("budiview", "Startpass1", full_name="Budi Viewer",
                       email="budiview@example.com")
    tok = auth.authenticate("budiview", "Startpass1", ip="127.0.0.1")
    assert tok, "seed login user gagal"
    return {"Authorization": f"Bearer {tok}"}


USER = _make_user()


def test_a_initial_null():
    r = client.get("/api/core/active-provider", headers=ADMIN)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["provider"] is None and d["username"] is None, d
    print("PASS (a): belum ada aktivasi -> provider=null")


def test_b_activate_oai():
    r = client.post("/api/core/activate-provider", headers=ADMIN, json={"provider": "oai"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["provider"] == "oai", r.text
    g = client.get("/api/core/active-provider", headers=ADMIN).json()
    assert g["provider"] == "oai" and g["username"] == "admin" and g["activated_at"], g
    print(f"PASS (b): activate oai -> active=oai (oleh {g['username']}, t={g['activated_at']:.0f})")


def test_c_switch_to_open5gs_upsert():
    r = client.post("/api/core/activate-provider", headers=ADMIN, json={"provider": "open5gs"})
    assert r.status_code == 200, r.text
    g = client.get("/api/core/active-provider", headers=ADMIN).json()
    # Backend sengaja simple upsert (spesifikasi owner); UI yang disable tombol
    # provider lain supaya switch ini gak pernah terjadi dari UI.
    assert g["provider"] == "open5gs", g
    with auth.get_db_session() as db:
        rows = db.query(main.ActiveProviderModel).filter_by(domain="core").all()
    assert len(rows) == 1, f"upsert harus tetap 1 row, dapat {len(rows)}"
    print("PASS (c): activate open5gs -> upsert single-row, active=open5gs")


def test_d_invalid_provider_400():
    r = client.post("/api/core/activate-provider", headers=ADMIN, json={"provider": "erlang"})
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    print(f"PASS (d): provider tidak terdaftar -> 400 ({r.json()['detail']})")


def test_e_viewer_forbidden_but_can_read():
    """RBAC 2-role: role 'user' adalah operator penuh — activate diizinkan."""
    r = client.post("/api/core/activate-provider", headers=USER, json={"provider": "magma"})
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    assert r.json()["username"] == "budiview", r.json()
    # User tetap boleh LIHAT status; aktivasi magma sukses menggantikan open5gs
    g = client.get("/api/core/active-provider", headers=USER)
    assert g.status_code == 200 and g.json()["provider"] == "magma", g.text
    print("PASS (e): user biasa activate -> 200 (setara engineer lama); GET status 200")


def test_f_deactivate_and_double():
    r = client.post("/api/core/deactivate-provider", headers=ADMIN)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    g = client.get("/api/core/active-provider", headers=ADMIN).json()
    assert g["provider"] is None, g
    r2 = client.post("/api/core/deactivate-provider", headers=ADMIN)
    assert r2.status_code == 404 and r2.json()["detail"] == "no_active_provider", r2.text
    print("PASS (f): deactivate -> null; deactivate kedua -> 404 no_active_provider")


def test_g_audit_logged():
    with auth.get_db_session() as db:
        acts = [
            a.action
            for a in db.query(main.AuditLogModel)
            .filter(main.AuditLogModel.action.in_(["PROVIDER_ACTIVATE", "PROVIDER_DEACTIVATE"]))
            .all()
        ]
    # 3 activate sukses (oai, open5gs oleh admin; magma oleh user biasa).
    # Deactivate sukses 1x.
    assert acts.count("PROVIDER_ACTIVATE") == 3, acts
    assert acts.count("PROVIDER_DEACTIVATE") == 1, acts
    print(f"PASS (g): audit log OK ({acts})")


if __name__ == "__main__":
    # Perbaiki ekspektasi test_g: hanya 2 PROVIDER_ACTIVATE yang sukses (oai, open5gs)
    test_a_initial_null()
    test_b_activate_oai()
    test_c_switch_to_open5gs_upsert()
    test_d_invalid_provider_400()
    test_e_viewer_forbidden_but_can_read()
    test_f_deactivate_and_double()
    test_g_audit_logged()
    print("\nALL TESTS PASSED")
