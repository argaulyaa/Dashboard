# AGENTS.md

Panduan untuk AI coding agent (Claude Code, dsb) yang bekerja di repo ini.
Baca file ini sebelum mengubah kode — banyak keputusan desain di sini
sengaja, bukan kebetulan.

## Ringkasan proyek

O-RAN Control Dashboard: panel kontrol full-stack untuk memantau dan
me-restart komponen jaringan Open RAN, dibagi jadi tiga domain —
**Core**, **RAN**, **RIC** — di mana tiap domain bisa punya beberapa
**provider** (mis. Core: OAI / Magma / open5gs) karena sifat Open RAN
yang vendor-agnostic. Backend FastAPI, frontend React (Vite + Tailwind).

Status implementasi saat ini (jangan asumsikan semua domain sudah nyata):

| Domain | Provider aktif | Status |
|---|---|---|
| Core | `oai` | **Nyata** kalau `OAI_CORE_CONTAINERS` diisi di `.env`. Dua mode: `OAI_SSH_HOST` (SSH paramiko ke node Core remote — recommended) atau `OAI_DOCKER_HOST` (Docker Engine API). Fallback mock kalau tidak. |
| Core | `open5gs` | Nyata kalau `OPEN5GS_CORE_CONTAINERS` diisi. Belum ada testbed-nya. |
| Core | `magma` | **Skeleton saja** (`MagmaCoreAdapter`), method-nya `raise NotImplementedError`. |
| RAN | `oai` | **Nyata** kalau `OAI_SSH_RAN_HOST` diisi di `.env` — deteksi OAI nr-softmodem / srsRAN `gnb` via SSH. Fallback mock kalau tidak. |
| RIC | `oai` | Mock (`RicAdapter`), belum disambungkan. |

Jangan tulis kode yang berasumsi RAN/RIC sudah live — cek dulu isi
`backend/adapters.py` sebelum klaim sesuatu "sudah connect ke testbed".

## Struktur repo

```
Dashboard/
├── backend/                FastAPI
│   ├── main.py              routes REST + 2 WebSocket endpoint
│   ├── adapters.py           <- provider registry + adapter pattern (lihat di bawah)
│   ├── auth.py               login/register/sesi, in-memory token (BUKAN JWT)
│   ├── reservations.py       lock komponen sebelum SSH (in-memory, TTL-based)
│   ├── ssh_proxy.py           jembatan WebSocket <-> paramiko SSH
│   ├── registered_users.json  akun self-registered (username, salt, hash pbkdf2)
│   ├── .env                  config provider (JANGAN commit; lihat .env.example)
│   └── requirements.txt
└── frontend/                React (Vite)
    └── src/
        ├── api.js             semua fetch() ke backend, satu tempat
        ├── auth.js, user.js    token & user di localStorage
        ├── App.jsx             routing, state komponen dari WS telemetry
        ├── pages/               satu file per halaman (CorePage, RanPage, RicPage, dst)
        └── components/          Sidebar, TopBar, ControlDrawer, ConsoleTerminal (xterm.js), dll
```

## Setup & command

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # lalu isi sesuai testbed kamu
uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev        # buka http://localhost:5173, proxy /api & /ws ke :8000 (lihat vite.config.js)
```

Tidak ada automated test suite di repo ini saat ini. Verifikasi manual:
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/core/providers
curl "http://localhost:8000/api/core/components?provider=oai"
```

## Pola adapter (WAJIB dipahami sebelum menambah provider baru)

Semua adapter — mock maupun nyata — harus memenuhi kontrak yang sama,
supaya `backend/main.py` dan seluruh frontend **tidak perlu diubah** saat
provider baru ditambahkan:

```python
class SomeAdapter:
    def list(self) -> List[dict]: ...
    def get(self, comp_id: str) -> Optional[dict]: ...
    async def restart(self, comp_id: str) -> Optional[dict]: ...
    def jitter_health(self) -> None: ...   # no-op untuk adapter nyata
```

Dict yang dikembalikan `list()`/`get()`/`restart()` harus punya field:
`id, name, kind, status, detail, host, cpu_pct, mem_gb, mem_pct,
throughput_mbps, port, latency_ms, active_ues, last_updated,
uptime_seconds`. `status` harus salah satu dari:
`"healthy" | "degraded" | "down" | "restarting"` — frontend
(`CorePage.jsx`, dll) hardcode empat nilai ini untuk warna/label.

Provider didaftarkan di `DOMAIN_PROVIDERS` (`backend/adapters.py`),
formatnya:
```python
"provider_key": {"label": str, "icon": str, "desc": str, "adapter": <instance>}
```
Frontend **fetch daftar provider secara dinamis** dari
`GET /api/{domain}/providers` — menambah entri baru di registry otomatis
memunculkan tab baru di UI, tidak perlu sentuh React sama sekali.

Kalau menambah adapter baru berbasis Docker (untuk provider lain, mis.
open5gs), gunakan ulang `DockerCoreAdapter` — jangan bikin dari nol,
cukup beda `container_map`-nya. Kalau providernya bukan berbasis Docker
(mis. Magma pakai REST API orc8r), bikin class terpisah tapi tetap
penuhi kontrak di atas.

## Environment variables

| Var | Dipakai di | Keterangan |
|---|---|---|
| `ORAN_USERS` | `auth.py` | Format `"user:pass,user2:pass2"`. Default `admin:admin` kalau kosong. |
| `OAI_CORE_CONTAINERS` | `adapters.py` | JSON `{comp_id: nama_container_docker}` untuk provider Core OAI. |
| `OAI_DOCKER_HOST` | `adapters.py` | Kosongkan kalau backend & Docker daemon satu mesin. Isi `tcp://host:port` kalau beda mesin. |
| `OPEN5GS_CORE_CONTAINERS`, `OPEN5GS_DOCKER_HOST` | `adapters.py` | Sama polanya seperti OAI, untuk provider open5gs. |
| `MAGMA_ORC8R_URL`, `MAGMA_API_KEY`, `MAGMA_NETWORK_ID` | `adapters.py` | Diteruskan ke `MagmaCoreAdapter`, tapi adapter-nya belum diimplementasi. |

`.env` dimuat lewat `python-dotenv` di baris paling atas `main.py`
(`load_dotenv()` **sebelum** `from adapters import ...`) — kalau
memindahkan import, urutan ini harus tetap dijaga, kalau tidak env var
belum kebaca saat `adapters.py` membangun `CORE_PROVIDERS`.

## Konvensi kode di repo ini

- Komentar & docstring backend campur Indonesia/Inggris — ikuti gaya
  file yang sedang diedit, jangan paksa konsisten semua jadi satu bahasa
  dalam satu PR/commit.
- Istilah yang konsisten dipakai di seluruh stack: `domain` (core/ran/ric),
  `provider` (key seperti `oai`, `magma`), `comp_id` (id komponen dalam
  satu provider, mis. `amf`, `gnb-1`).
- Frontend: satu file `api.js` menampung semua pemanggilan REST — jangan
  `fetch()` langsung dari komponen halaman.
- State komponen "live" (provider pertama tiap domain) datang dari
  WebSocket `/ws/telemetry`, bukan polling REST. Provider non-default
  di-fetch manual sekali via REST saat tab-nya diklik (lihat
  `CorePage.jsx`). Kalau menambah provider baru yang butuh live update,
  ini pola yang harus diikuti, jangan bikin polling terpisah.

## Keamanan — jangan "perbaiki" tanpa konteks ini

- `CORSMiddleware` di `main.py` pakai `allow_origins=["*"]` — sengaja
  untuk lab, **catatan sudah ada di kode** ("tighten this before any
  real deployment"). Jangan diam-diam ubah jadi ketat tanpa diminta,
  itu bisa merusak dev workflow saat ini.
- Token sesi di `auth.py` disimpan in-memory (`SESSIONS` dict), hilang
  kalau backend restart — bukan bug, ini demo/lab-grade auth, sudah
  didokumentasikan di docstring file itu sendiri.
- Password SSH untuk `/ws/ssh/{domain}/{comp_id}` dikirim dari frontend
  ke backend dalam payload JSON pertama (lihat `ssh_proxy.py` &
  `main.py::ssh_ws`) — tidak disimpan, tapi lewat di memori proses.
  Jangan log payload ini kalau menambah logging.
- `registered_users.json` berisi hash PBKDF2 (bukan plaintext), tapi
  tetap: jangan commit isi file ini kalau sudah ada user asli terdaftar.
- `.env` (bukan `.env.example`) tidak boleh dicommit — isinya bisa
  memuat detail infrastruktur testbed.

## Hal yang sengaja belum dikerjakan (jangan "selesaikan" tanpa diminta)

- `throughput_mbps`, `port`, `latency_ms`, `active_ues` di
  `DockerCoreAdapter._read_component()` masih hardcode `0` — datanya
  belum ada sumbernya (butuh metrics dari tiap NF, belum diekspos).
  Jangan isi dengan angka karangan supaya "kelihatan lengkap".
- `MagmaCoreAdapter` semua method-nya `raise NotImplementedError` — ini
  kerangka yang disiapkan untuk diisi nanti setelah orc8r tersedia,
  bukan bug yang perlu buru-buru ditutup dengan mock data.
- RAN dan RIC masih 100% mock (`RanAdapter`, `RicAdapter` di
  `adapters.py`). README menyarankan sambungkan RAN dulu (karena
  testbed OAI RAN sudah ada), tapi urutan aktual mengikuti instruksi
  pemilik repo di setiap sesi kerja — cek percakapan/issue terkait
  sebelum mulai kerja di domain ini.

## Deploy ke K8s (CI/CD) - fakta permanen, jangan diubah tanpa sadar

- Aplikasi dideploy ke cluster testbed via **Helm** dari workflow
  `.github/workflows/deploy.yml` (push ke `main` / `workflow_dispatch`).
- **Nama release WAJIB `oran`** (namespace `dashboard`). Resource yang melayani situs:
  deployment `oran-backend` & `oran-frontend`, service NodePort `oran-frontend` port **30090**
  di node `core`. Ganti nama release = bikin release duplikat yang konflik & situs tak pernah
  diupdate. `env.HELM_RELEASE` di deploy.yml harus tetap `oran`.
- ghcr.io **bersifat privat** - pod tak bisa menarik image tanpa auth. Chart me-render
  `imagePullSecrets: [{"name":"ghcr-secret"}]` lewat `image.pullSecrets` di `values.yaml`
  (template `backend-deployment.yaml` & `frontend-deployment.yaml`, sebagai sibling di bawah `spec:`).
  CI memastikan secret ini ada (bikin kalau belum, idempotent, biarkan yang sudah jalan).
  Untuk cluster baru set Actions secret `GHCR_TOKEN` (PAT `read:packages`) & opsional
  `GHCR_USERNAME`; fallback-nya `GITHUB_TOKEN`.
- Strategi image: CI men-tag image dengan `$github.sha` (unik per build) +
  `image.pullPolicy: Always`. JANGAN deploy lewat `kubectl rollout restart` saja - itu tidak
  meng-update tag image sehingga versi lama yang tercache tetap tersaji (mismatch).
  JANGAN pakai `--reuse-values` - gagal di install pertama dan menyembunyikan drift config.
- Kredensial SSH testbed (core `10.91.2.151`, ran `10.91.2.152`, user `core`/`ran`) sekarang
  diset **sebagai default di `values.yaml`** (bukan hanya lewat `--set`), supaya
  `helm upgrade` tanpa `--reuse-values` tetap me-render state known-good.
  Backend & frontend di-pin ke node `core` (`nodeSelector`) agar jalur SSH/image konsisten.
