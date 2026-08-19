# O-RAN Control Dashboard — Skeleton

Skeleton full-stack panel kontrol Open RAN: Core, RAN, RIC ditampilkan sebagai
tiga domain, tiap komponen bisa dilihat statusnya dan direstart. Semua data
saat ini **mock** (simulasi) — tujuan skeleton ini adalah menyediakan
arsitektur yang siap disambungkan ke testbed OAI/FlexRIC yang sesungguhnya.

## Struktur

```
oran-dashboard/
├── backend/            FastAPI — API status & kontrol + WebSocket telemetry
│   ├── main.py
│   ├── adapters.py     <- di sinilah integrasi ke testbed nyata masuk
│   └── requirements.txt
└── frontend/           React (Vite) — tampilan dashboard
    └── src/
        ├── App.jsx
        ├── api.js
        └── components/
```

## Menjalankan

**Backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend** (di terminal terpisah)
```bash
cd frontend
npm install
npm run dev
```

Buka `http://localhost:5173`. Vite sudah dikonfigurasi untuk proxy
`/api` dan `/ws` ke backend di port 8000 (lihat `vite.config.js`).

## Cara kerja saat ini (mock)

- `backend/adapters.py` punya tiga adapter: `CoreAdapter`, `RanAdapter`,
  `RicAdapter`. Masing-masing menyimpan komponen contoh (AMF/SMF/UPF,
  gNB/CU/DU, xApps RIC) dengan status yang berubah acak untuk simulasi
  telemetry live lewat WebSocket `/ws/telemetry`.
- Aksi "Restart komponen" di drawer memanggil
  `POST /api/{domain}/components/{id}/restart`, yang di mock ini cuma
  `sleep` lalu set status kembali `healthy`.

## Menyambungkan ke testbed nyata

Titik integrasi ada di `backend/adapters.py` — ganti isi tiap adapter,
bukan struktur API-nya, supaya frontend tidak perlu diubah:

| Domain | Ganti dengan |
|---|---|
| Core | SSH ke node Core (paramiko) menjalankan `docker ps/inspect/stats/logs/restart`, atau Docker Engine API (`OAI_DOCKER_HOST`) untuk restart container NF |
| RAN | SSH/CLI ke OAI softmodem / srsRAN (sudah ada: `SshRanAdapter` — status proses, uptime, CPU/RAM, konfig, N2/E2) |
| RIC | E2 interface via SDK FlexRIC (near-RT RIC / xApps), A1 policy call ke non-RT RIC |

Untuk telemetry live yang sesungguhnya, ganti loop `jitter_health()` di
`/ws/telemetry` dengan subscription nyata — misalnya stream dari T-Tracer,
atau E2 indication message.

## Langkah lanjutan yang disarankan

1. Sambungkan satu adapter dulu (misalnya RAN, karena testbed OAI sudah ada)
   ke data/aksi nyata — jangan tiga domain sekaligus.
2. Tambahkan autentikasi + RBAC sebelum ada aksi kontrol yang benar-benar
   mengubah state jaringan produksi/eksperimen.
3. Setelah pemetaan komponen nyata jelas, baru masuk ke fitur-fitur
   tambahan (log historis, alerting, dashboard auto-healing, dsb).
