# O-RAN Control Dashboard

Panel kontrol full-stack untuk Open RAN: Core, RAN, dan RIC ditampilkan
sebagai tiga domain, tiap domain bisa punya beberapa **provider**
(mis. Core: OAI / Magma / open5gs) karena sifat Open RAN yang terbuka —
tidak terikat satu vendor. Tiap komponen (AMF, gNB, xApp, dst) bisa
dilihat statusnya secara live dan direstart lewat dashboard.

> Status saat ini: **Core → provider OAI sudah bisa terhubung ke data
> nyata** (lewat Docker Engine API). Provider lain & domain lain (RAN,
> RIC) masih mock — lihat tabel di [`AGENTS.md`](./AGENTS.md) untuk
> status lengkap per domain/provider.

## Struktur

```
Dashboard/
├── backend/            FastAPI — API status & kontrol + WebSocket telemetry
│   ├── main.py
│   ├── adapters.py     <- integrasi ke tiap provider ada di sini
│   ├── auth.py          login/register + sesi
│   ├── reservations.py  lock komponen sebelum SSH
│   ├── ssh_proxy.py     jembatan SSH lewat WebSocket
│   ├── .env.example     contoh konfigurasi provider
│   └── requirements.txt
└── frontend/           React (Vite + Tailwind) — tampilan dashboard
    └── src/
        ├── App.jsx
        ├── api.js
        ├── pages/
        └── components/
```

Dokumen lain di repo ini:
- [`AGENTS.md`](./AGENTS.md) — konteks untuk AI coding agent, termasuk
  kontrak adapter yang wajib dipenuhi tiap provider.
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — alur data lebih
  detail: pola adapter, reservasi/lock, telemetry WebSocket, SSH proxy.

## Menjalankan

**Backend**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env      # isi sesuai testbed kamu, lihat bagian Konfigurasi di bawah
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

Login default (kalau `ORAN_USERS` belum di-set): `admin` / `admin`.
Ganti ini via env var sebelum dipakai di luar mesin lokal.

## Konfigurasi provider (`backend/.env`)

Provider Core diaktifkan lewat environment variable. Kalau env-nya
kosong, provider tetap muncul di UI tapi otomatis jalan mode mock —
dashboard tidak pernah error walau provider belum disetel.

```bash
# Core — OAI (cloud-native 5GC via Docker)
OAI_CORE_CONTAINERS={"amf":"oai-amf","smf":"oai-smf","upf":"oai-upf","ausf":"oai-ausf","udm":"oai-udm","udr":"oai-udr","nrf":"oai-nrf"}
OAI_DOCKER_HOST=          # kosong = backend & docker daemon satu mesin

# Core — open5gs (pola sama seperti OAI)
OPEN5GS_CORE_CONTAINERS={}
OPEN5GS_DOCKER_HOST=

# Core — Magma (belum diimplementasi penuh, lihat AGENTS.md)
MAGMA_ORC8R_URL=
MAGMA_API_KEY=
MAGMA_NETWORK_ID=
```

Cara cek nama container asli di testbed:
```bash
docker ps --format "{{.Names}}"
```

Backend butuh akses ke Docker daemon tempat container providernya
jalan: kalau satu mesin, cukup pastikan user yang menjalankan `uvicorn`
ada di grup `docker`; kalau beda mesin, expose Docker API lewat TCP dan
isi `OAI_DOCKER_HOST=tcp://<ip>:<port>`.

## Cara kerja (ringkas)

- `backend/adapters.py` mendaftarkan provider per domain lewat
  `DOMAIN_PROVIDERS = {"core": {...}, "ran": {...}, "ric": {...}}`.
  Frontend fetch daftar ini dari `GET /api/{domain}/providers` —
  menambah provider baru di backend otomatis memunculkan tab baru di
  UI, tanpa ubah kode React.
- Provider pertama tiap domain dapat update live lewat WebSocket
  `/ws/telemetry` (snapshot tiap 3 detik). Provider lain diambil sekali
  lewat REST saat tab-nya diklik.
- Aksi "Restart komponen" memanggil
  `POST /api/{domain}/components/{id}/restart`.
- Sebelum akses SSH ke sebuah komponen, dashboard mewajibkan
  "reservasi" (lock berbasis waktu) supaya dua orang tidak SSH
  bertabrakan ke komponen yang sama — lihat `reservations.py`.

## Menambah provider baru

Titik integrasi ada di `backend/adapters.py` — ganti/tambah isi adapter,
bukan struktur API-nya, supaya frontend tidak perlu diubah:

| Domain | Provider contoh | Cara integrasi |
|---|---|---|
| Core | OAI, open5gs | `DockerCoreAdapter` — query status via Docker Engine API (sudah tersedia, tinggal isi `container_map`) |
| Core | Magma | REST API orc8r — lihat kerangka `MagmaCoreAdapter` |
| RAN | OAI gNB | SSH/CLI ke softmodem, atau config-management API kalau tersedia |
| RIC | FlexRIC | E2 interface via SDK FlexRIC (near-RT RIC/xApps), A1 policy call ke non-RT RIC |

Detail kontrak method yang wajib dipenuhi tiap adapter ada di
[`AGENTS.md`](./AGENTS.md#pola-adapter-wajib-dipahami-sebelum-menambah-provider-baru).

## Langkah lanjutan yang disarankan

1. Selesaikan provider Core lain (open5gs, Magma) atau lanjut ke RAN —
   README lama menyarankan RAN duluan karena testbed-nya sudah ada;
   prioritas aktual disesuaikan kebutuhan penelitian.
2. Isi `throughput_mbps`, `latency_ms`, `active_ues` di
   `DockerCoreAdapter` dari sumber metrics NF asli (saat ini masih 0).
3. Tambahkan RBAC (role admin vs operator) sebelum dashboard dipakai
   untuk mengontrol jaringan eksperimen/produksi sungguhan — saat ini
   semua akun punya akses restart & hapus user yang sama.
4. Pertimbangkan automated test (belum ada test suite sama sekali saat ini).
