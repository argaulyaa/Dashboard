"""Verifikasi eksklusivitas activation untuk domain RAN (t_4618ed5a) — RAN domain.

Cakupan:
  (1) GET /api/ran/active-provider awal -> null.
  (2) Activate 'srsran' -> active=srsran.
  (3) Activate 'srsran' lagi (idempotent).
  (4) Switch ke 'oai' saat srsran aktif -> 409 provider_active (B1);
      setelah deactivate -> activate oai sukses.
  (5) Hanya ada 1 row active_providers untuk domain ran.
  (6) Domain core INDEPENDEN: activate core gak mengganggu ran.
  (7) Deactivate ran -> null; core tetap aktif.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ran_activation.db"
for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
    os.environ.pop(k, None)

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import auth  # noqa: E402

client = TestClient(main.app)

r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
assert r.status_code == 200, r.text
H = {"Authorization": f"Bearer {r.json()['token']}"}

# (1)
g = client.get("/api/ran/active-provider", headers=H).json()
assert g["provider"] is None and g["username"] is None, g
print("PASS (1): ran belum ada aktivasi -> provider=null")

# (2)
r = client.post("/api/ran/activate-provider", headers=H, json={"provider": "srsran"})
assert r.status_code == 200 and r.json()["provider"] == "srsran", r.text
g = client.get("/api/ran/active-provider", headers=H).json()
assert g["provider"] == "srsran" and g["username"] == "admin", g
print("PASS (2): activate srsran -> ran active=srsran")

# (3) idempotent re-activate sama provider
r = client.post("/api/ran/activate-provider", headers=H, json={"provider": "srsran"})
assert r.status_code == 200, r.text
print("PASS (3): re-activate srsran idempotent")

# (4) switch ke oai saat srsran aktif -> 409 provider_active (B1 server-side);
#     setelah deactivate -> switch sukses.
r = client.post("/api/ran/activate-provider", headers=H, json={"provider": "oai"})
assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"
d = r.json()["detail"]
assert d["reason"] == "provider_active" and d["active"] == "srsran", d
print("PASS (4a): activate oai saat srsran aktif -> 409 provider_active")
r = client.post("/api/ran/deactivate-provider", headers=H)
assert r.status_code == 200, r.text
r = client.post("/api/ran/activate-provider", headers=H, json={"provider": "oai"})
assert r.status_code == 200 and r.json()["provider"] == "oai", r.text
g = client.get("/api/ran/active-provider", headers=H).json()
assert g["provider"] == "oai", g
print("PASS (4b): deactivate -> activate oai -> ran active=oai")

# (5) cuma 1 row utk domain ran
with auth.get_db_session() as db:
    rows = db.query(main.ActiveProviderModel).filter_by(domain="ran").all()
    n = len(rows)
    prov = rows[0].provider if rows else None
assert n == 1 and prov == "oai", (n, prov)
print(f"PASS (5): single-row eksklusif domain ran ({n} row, provider={prov})")

# (6) independensi antar domain: core bisa aktif sendiri
r = client.post("/api/core/activate-provider", headers=H, json={"provider": "open5gs"})
assert r.status_code == 200, r.text
g_ran = client.get("/api/ran/active-provider", headers=H).json()
g_core = client.get("/api/core/active-provider", headers=H).json()
assert g_ran["provider"] == "oai" and g_core["provider"] == "open5gs", (g_ran, g_core)
with auth.get_db_session() as db:
    total = db.query(main.ActiveProviderModel).count()
assert total == 2, total
print("PASS (6): core & ran independen (2 rows: core=open5gs, ran=oai)")

# (7) deactivate ran -> null, core tidak terpengaruh
r = client.post("/api/ran/deactivate-provider", headers=H)
assert r.status_code == 200, r.text
g_ran = client.get("/api/ran/active-provider", headers=H).json()
g_core = client.get("/api/core/active-provider", headers=H).json()
assert g_ran["provider"] is None and g_core["provider"] == "open5gs", (g_ran, g_core)
print("PASS (7): deactivate ran -> null; core tetap open5gs")

print("\nALL RAN ACTIVATION TESTS PASSED")
