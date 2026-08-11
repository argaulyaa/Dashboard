# Arsitektur — O-RAN Control Dashboard

Dokumen ini menjelaskan *alur data* di balik dashboard, bukan cuma
daftar file. Ditulis untuk orang (atau AI agent) yang perlu mengubah
sesuatu dan harus tahu bagian mana yang saling bergantung.

## 1. Model domain/provider/component

Tiga lapis hierarki dipakai konsisten di backend maupun frontend:

```
domain      ("core" | "ran" | "ric")
  └─ provider   (mis. "oai", "magma", "open5gs" -- beda-beda per vendor)
       └─ component   (mis. "amf", "gnb-1", "xapp-kpimon" -- comp_id)
```

- **domain** hardcode di tiga tempat: `DOMAIN_PROVIDERS` (backend),
  routing di `App.jsx`, dan menu `Sidebar.jsx` (frontend). Menambah
  domain baru (mis. "transport") butuh ubah ketiganya.
- **provider** *tidak* hardcode di frontend — sepenuhnya data-driven
  dari `GET /api/{domain}/providers`. Menambah provider baru cukup di
  backend (lihat §3).
- **component** bentuknya beda-beda tergantung domain, tapi field
  wajibnya sama (lihat §2) supaya kartu komponen di frontend
  (`ComponentCard.jsx`) bisa render apa saja tanpa tahu domainnya.

## 2. Kontrak data komponen

Semua adapter — mock atau nyata — mengembalikan dict dengan field ini
(didefinisikan lewat dataclass `Component` untuk mock, dan dict manual
untuk `DockerCoreAdapter`):

| Field | Tipe | Dipakai di UI untuk |
|---|---|---|
| `id` | str | key React, target restart/reservasi |
| `name` | str | judul kartu |
| `kind` | str | subjudul/deskripsi jenis NF |
| `status` | `"healthy"\|"degraded"\|"down"\|"restarting"` | warna dot + label (`CorePage.jsx: STATUS_DOT/STATUS_LABEL`) |
| `detail` | str | teks kecil di kartu |
| `host` | str | dipakai `ControlDrawer`/`ConsoleTerminal` untuk target SSH |
| `cpu_pct`, `mem_gb`, `mem_pct` | float | gauge di kartu/hero panel |
| `throughput_mbps`, `latency_ms`, `active_ues`, `port` | float/int | metrik tambahan (belum semua provider mengisi ini — lihat `AGENTS.md`) |
| `last_updated` | epoch float | "diperbarui X detik lalu" |
| `uptime_seconds` | float | dihitung dari `started_at` (mock) atau `StartedAt` container Docker (nyata) |

`status` bukan enum bebas — nilai lain akan bikin frontend jatuh ke
default/tidak ke-style. Kalau adapter baru punya status lain dari
vendor (mis. Docker `"paused"`), **map dulu** ke empat nilai di atas
(lihat `DockerCoreAdapter._map_status`).

## 3. Pola adapter & provider registry

```
                     ┌─────────────────────────────┐
GET /api/core/       │  DOMAIN_PROVIDERS["core"]    │
providers    ──────► │  { "oai": {...}, "magma": {...} } │──► [{key,label,icon,desc}, ...]
                     └─────────────────────────────┘

GET /api/core/       ┌─────────────────────────────┐
components?          │  entry["adapter"].list()     │
provider=oai ──────► │  (DockerCoreAdapter.list())  │──► [{id, status, ...}, ...]
                     └─────────────────────────────┘
```

`_build_core_providers()` di `adapters.py` jalan **sekali** saat modul
di-import (saat backend start), bukan per-request. Artinya:

- Kalau kamu ubah `.env` saat backend jalan (`--reload` aktif),
  Uvicorn reload module Python-nya, `_build_core_providers()` jalan
  ulang, provider ke-refresh. Tapi kalau kamu edit `.env` tanpa restart
  backend (mis. env var di-set lewat shell lalu backend sudah jalan
  duluan), perubahan **tidak** kepakai sampai proses di-restart.
- `DockerCoreAdapter.__init__` langsung bikin `docker.DockerClient(...)`
  saat modul di-import. Kalau Docker daemon tidak reachable saat startup,
  ini bisa raise exception dan backend gagal start — bukan gagal
  senyap. Kalau ingin lebih toleran, bungkus pembuatan client dengan
  try/except di `_build_core_providers()` (belum dilakukan saat ini).

## 4. Dua jalur pengambilan data komponen (live vs on-demand)

Frontend punya dua cara dapat data komponen, **jangan disamakan**:

1. **Provider default (pertama terdaftar) tiap domain** → dapat data
   dari WebSocket `/ws/telemetry`. Backend push snapshot semua domain
   tiap 3 detik (`main.py::telemetry_ws`). `App.jsx` nyimpen ini di
   state dan meneruskan sebagai prop `components` ke tiap halaman.
2. **Provider selain yang pertama** → di-fetch sekali lewat
   `GET /api/{domain}/components?provider=X` saat tab-nya diklik
   (`CorePage.jsx::useEffect` yang cek `isDefaultProvider`). Tidak ada
   polling otomatis untuk provider non-default.

Implikasi: kalau kamu ubah urutan provider di `_build_core_providers()`
(mis. `open5gs` didaftarkan sebelum `oai`), provider yang jadi "live by
default" ikut berubah — dari sisi backend ini `next(iter(providers))`
di `main.py::_get_adapter`. Kalau ingin provider tertentu selalu jadi
default, urutan insert dict di `_build_core_providers()` yang menentukan.

## 5. Reservasi/lock sebelum SSH

```
User klik "Connect SSH" di ControlDrawer
    │
    ▼
POST /api/core/components/amf/reservation  {user, ttl_seconds, note}
    │
    ├─ 409 kalau user lain sudah reserve → UI tampilkan siapa yang pegang
    └─ 200 → reservasi tersimpan di ReservationManager (in-memory, key "core:amf")
                │
                ▼
        WS /ws/ssh/core/amf  {user, ssh_username, ssh_password, port}
                │
                ├─ backend cek reservations.status("core","amf").user == user
                │  kalau tidak cocok → tolak koneksi, tidak lanjut SSH sama sekali
                └─ cocok → run_ssh_bridge() buka koneksi paramiko ke component["host"]
```

Poin penting: reservasi **tidak otomatis dilepas** saat SSH ditutup.
User (atau TTL 15 menit default) yang melepasnya. Kalau butuh
auto-release saat WebSocket disconnect, itu belum diimplementasikan —
`ssh_ws` di `main.py` tidak memanggil `reservations.release()` di blok
`finally`.

## 6. SSH proxy (`ssh_proxy.py`)

- Satu thread terpisah (`_reader_thread`) baca output SSH channel
  secara blocking-polling (`recv_ready()` + sleep 0.05s), taruh ke
  `queue.Queue`, supaya event loop asyncio utama tidak diblok oleh I/O
  paramiko yang sinkron.
- Resize terminal dikirim sebagai JSON (`{"type":"resize","cols":...,
  "rows":...}`) lewat WebSocket yang sama dengan input keystroke —
  dibedakan dari input biasa dengan cek `msg.startswith("{")`. Kalau
  nanti nambah jenis pesan kontrol lain, ikuti pola ini tapi hati-hati:
  keystroke biasa yang kebetulan diawali `{` (jarang, tapi mungkin di
  beberapa TUI) akan salah diparse sebagai JSON control message.

## 7. Autentikasi

Dua sumber user, digabung transparan di `authenticate()`:

- **Akun bawaan** dari `ORAN_USERS` env var (plaintext, dibandingkan
  `secrets.compare_digest`) — untuk akun admin/demo tetap.
- **Akun self-registered** lewat `POST /api/auth/register`, password
  di-hash PBKDF2-HMAC-SHA256 (100.000 iterasi), disimpan di
  `registered_users.json`.

Token sesi: `secrets.token_urlsafe(32)`, disimpan di dict in-memory
`SESSIONS`, TTL 8 jam. **Hilang total saat backend restart** — semua
user ke-logout paksa. Ini bukan bug, didokumentasikan di docstring
`auth.py`, tapi penting diketahui kalau debugging "kenapa tiba-tiba
logout" setelah `--reload` trigger restart.

## 8. Hal yang perlu diperhatikan sebelum deploy nyata

Ringkasan dari catatan yang sudah ada di kode + `AGENTS.md`, dikumpulkan
di sini biar satu tempat:

- `CORSMiddleware(allow_origins=["*"])` — perlu dipersempit.
- Tidak ada RBAC — endpoint `DELETE /api/auth/users/{username}` bisa
  dipanggil user mana saja yang sudah login (lihat komentar di
  `main.py::remove_user`).
- Sesi & reservasi in-memory, tidak persistent, tidak shared antar
  instance backend (kalau nanti di-scale horizontal, butuh Redis atau
  sejenisnya — sudah dicatat di docstring `reservations.py`).
- Password SSH dikirim lewat payload WebSocket pertama, bukan disimpan,
  tapi tetap sensitif — pastikan koneksi WebSocket dari frontend ke
  backend lewat TLS (wss://) di luar localhost.
