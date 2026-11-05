# KONTEKS LENGKAP PROYEK — O-RAN Control Dashboard (Testbed 5G Bare-Metal 3-PC)

**Dibuat:** 4 November 2026
**Untuk:** agent AI baru (atau tim lain) yang melanjutkan pekerjaan di dashboard maupun testbed ini
**Status:** dashboard sudah live & terhubung nyata ke 2 dari 3 node testbed; RAN sudah bisa switch antara 2 software (srsRAN & OAI); Core masih 1 provider (Open5GS)

> Baca dokumen ini sampai habis sebelum menyentuh kode, deployment, atau testbed fisik.
> Banyak keputusan di sini **sengaja**, bukan kelalaian — terutama soal apa yang belum
> diimplementasi dan kenapa.

---

## 1. Apa proyek ini

**O-RAN Control Dashboard** — panel kontrol full-stack untuk testbed 5G Open RAN
bare-metal 3-PC (Core, RAN, RIC) di lab kampus. Tujuan: satu layar web untuk memilih
dan memantau kombinasi software Core + RAN + RIC yang berbeda (prinsip Open RAN:
vendor-agnostic, bisa campur Core dari vendor A dengan RAN dari vendor B).

Kebutuhan pemilik proyek:
> "Dashboard yang bisa milih core, RAN, dan RIC-nya."

Konsekuensi desain:
1. Tiap domain (Core/RAN/RIC) bisa punya **beberapa provider** (software/vendor berbeda).
2. Provider **tidak di-hardcode** di frontend — backend mendaftarkan provider di registry
   (`backend/adapters.py`), frontend fetch daftar itu dan render tab secara dinamis.
3. Ada mekanisme **memilih kombinasi Core+RAN lalu menyambungkannya** ("hybrid connect").
4. Data yang tampil harus **data nyata dari testbed**, bukan angka karangan. Kalau sumber
   datanya belum ada, dibiarkan 0/kosong — JANGAN DIISI MOCK supaya "kelihatan lengkap".

**Stack**: FastAPI (backend) + React 18 (Vite + Tailwind, frontend) + SQLite (DB kecil:
user, audit log, reservasi, status aktivasi provider) + paramiko (SSH ke testbed) +
xterm.js (web console/terminal langsung ke node testbed).

---

## 2. Testbed fisik — 3 PC, peran, dan akses

| Host | IP | User SSH | Auth | Peran |
|---|---|---|---|---|
| `core` | `10.91.2.151` | `core` | **SSH key-only** (password dimatikan di server) | 5G Core Network |
| `ran` | `10.91.2.152` | `ran` | SSH password | gNB (RAN) + USRP B210 (radio fisik) |
| `ric` | `10.91.2.153` | `telmat` | SSH password | FlexRIC (nearRT-RIC) + **host deployment dashboard ini** |

Akses jaringan: dari luar lab, lewat **WireGuard** ke subnet `10.91.2.0/21`.

### 2.1 `core` (10.91.2.151) — 5G Core Network

Software yang jalan: **Open5GS v2.8.0**, sebagai 11 unit **systemd** (bukan Docker/K8s):

```
open5gs-amfd, open5gs-smfd, open5gs-upfd, open5gs-nrfd, open5gs-ausfd,
open5gs-udmd, open5gs-udrd, open5gs-pcfd, open5gs-nssfd, open5gs-scpd, open5gs-bsfd
```

Port penting:
- AMF — **SCTP 38412** (N2, signaling ke gNB)
- SMF — **PFCP UDP 8805**
- UPF — **GTP-U UDP 2152** (N3, user plane data)

Interface tunnel UE: `ogstun` (nama interface TUN Linux yang dibuat Open5GS untuk
meneruskan trafik UE ke internet). **PENTING — arah byte counter TERBALIK** dari
interface fisik biasa: `tx_bytes` di `/proc/net/dev` untuk `ogstun` = **DOWNLINK**
(internet→UE), `rx_bytes` = **UPLINK** (UE→internet). Ini diverifikasi via `tcpdump`
langsung saat UE streaming video — kalau bikin monitoring baru atas interface tun
manapun, uji ulang arahnya, jangan asumsikan rx=downlink seperti interface biasa.

Subscriber (SIM) tersimpan di MongoDB Open5GS (`db.subscribers`), ada 6 IMSI dengan
PLMN `001/01`. Detail IMSI/K/OPC ada di `/home/ubuntu/benchmark-5g/configs/sim_data/`.

Core juga punya sisa instalasi lama yang **TIDAK AKTIF**: Docker OAI Core
(`oai-cn5g-fed`, container status `Exited`) dan Magma (backup). SSH ke host ini
**hanya menerima publickey**, private key disimpan di `~/.ssh/telmat_core_key`
(di VM agent) dan di-copy ke server dashboard sebagai
`/home/telmat/.ssh/dashboard_core_key`.

### 2.2 `ran` (10.91.2.152) — Radio Access Network

Hardware: **1x USRP B210** (software-defined radio) — **hanya satu gNB boleh
aktif dalam satu waktu** karena cuma ada satu unit radio fisik.

Dua software gNB terpasang, dipilih via systemd unit terpisah:

| Software | Unit systemd | Config aktif | Catatan |
|---|---|---|---|
| **srsRAN Project** | `srsran-gnb.service` | `/home/ran/srsran-configs/n40_RICbare.yaml` (dipilih lewat env var `GNB_CONFIG` di `/etc/default/srsran-gnb`) | Band n40, 40MHz (106 PRB), PCI 1 |
| **OpenAirInterface (OAI)** | `oai-gnb-n40.service` (unit baru, dibuat 3-4 Nov 2026) | `/home/ran/gnb-proven-441s-lowgain.conf` | Band n40, **20MHz (51 PRB)** — beda bandwidth dari srsRAN, lihat §5 |

> Unit `oai-gnb.service` (lama) menunjuk ke config **band 78** — SUDAH TIDAK DIPAKAI,
> proyek ini fokus **band n40 saja** (keputusan eksplisit pemilik proyek).

Karena cuma 1 radio fisik, backend **wajib** mematikan gNB yang sedang aktif
sebelum menyalakan yang lain (lihat §4, `ran_hybrid.py`).

### 2.3 `ric` (10.91.2.153) — RIC + host deployment dashboard

- **FlexRIC** (nearRT-RIC), SCTP port 36421 (E2 interface ke gNB).
- **Dashboard ini sendiri di-deploy di host yang sama** (lihat §6).

---

## 3. Arsitektur kode dashboard

### 3.1 Dua repo GitHub — JANGAN TERTUKAR

| Repo | Peran | Lokasi kerja |
|---|---|---|
| `argaulyaa/Dashboard` | Repo kerja utama (dev, semua perubahan kode dimulai di sini) | clone lokal di mesin developer, branch `main` |
| `argaulyaa/OpenRAN-Dashboard` | Repo yang **benar-benar live di-deploy** di server (RIC) | `/home/telmat/Dashboard/OpenRAN-Dashboard` di host RIC, branch `deploy/baremetal-nginx` |

Alur kerja: develop & commit di `Dashboard` (branch `main`) → push → di server RIC,
`git fetch dashboard-src main` (remote `dashboard-src` sudah ditambahkan, mengarah ke
`Dashboard`) → `git cherry-pick <sha>` ke `deploy/baremetal-nginx` → build/restart →
push branch deploy ke `OpenRAN-Dashboard`.

**Kenapa dua repo**: histori proyek — ada deployment live yang sudah berjalan di server
sebelum konsolidasi repo kerja dilakukan. Belum diputuskan untuk digabung jadi satu;
kalau mau konsolidasi, itu perlu keputusan eksplisit pemilik proyek, bukan inisiatif
sepihak agent manapun.

### 3.2 Struktur folder

```
Dashboard/ (= OpenRAN-Dashboard di server)
├── AGENTS.md                 panduan asli untuk AI coding agent — WAJIB dibaca juga
├── backend/                  FastAPI
│   ├── main.py                routes REST + 2 WebSocket endpoint (/ws/telemetry, /ws/ssh/*)
│   ├── adapters.py            provider registry (lihat §3.3) — JANTUNG arsitektur
│   ├── ran_hybrid.py          logika exclusive switching RAN (bare-metal, lihat §4)
│   ├── auth.py                login/register, token in-memory (BUKAN JWT, bukan persisten)
│   ├── reservations.py        sistem booking slot waktu sebelum SSH console dipakai
│   ├── ssh_proxy.py           jembatan WebSocket <-> paramiko SSH (console browser)
│   ├── models.py               SQLAlchemy models (termasuk ActiveProviderModel)
│   ├── .env                   config provider & kredensial SSH (JANGAN commit)
│   └── requirements.txt
└── frontend/                 React (Vite)
    └── src/
        ├── api.js              semua fetch() ke backend, satu tempat terpusat
        ├── App.jsx             routing, WebSocket telemetry, state global
        ├── pages/
        │   ├── CorePage.jsx     tab provider Core, status NF, tombol activate
        │   ├── RanPage.jsx      tab provider RAN (srsRAN/OAI), status gNB
        │   └── RicPage.jsx      status FlexRIC
        └── components/
            ├── CoreRanConnectBar.jsx   UI pilih kombinasi Core+RAN lalu connect
            ├── ConsoleTerminal.jsx     web terminal (xterm.js) ke node testbed
            └── ...
```

### 3.3 Pola adapter provider (WAJIB dipahami sebelum menambah provider baru)

Semua adapter (mock maupun nyata) harus punya kontrak yang sama supaya `main.py` dan
frontend **tidak perlu diubah** saat menambah provider baru:

```python
class SomeAdapter:
    def list(self) -> List[dict]: ...
    def get(self, comp_id: str) -> Optional[dict]: ...
    async def restart(self, comp_id: str) -> Optional[dict]: ...
```

Dict yang dikembalikan harus punya field: `id, name, kind, status, detail, host,
cpu_pct, mem_gb, mem_pct, throughput_mbps, port, latency_ms, active_ues,
last_updated, uptime_seconds`. `status` wajib salah satu dari:
`"healthy" | "degraded" | "down" | "restarting"`.

**Status implementasi per domain (per 4 Nov 2026):**

| Domain | Provider | Status |
|---|---|---|
| Core | `open5gs` | **Nyata**, via `SshSystemdCoreAdapter` (SSH ke 11 unit systemd) |
| Core | ~~`oai`~~, ~~`open5gs` versi lama~~ | **Dihapus dari registry** (dulu mock, sudah dibersihkan — lihat §7) |
| RAN | `srsran` | **Nyata**, via `SrsRanSshAdapter` |
| RAN | `oai` | **Nyata**, via `SshRanAdapter` — baru berhasil connect UE fisik 3-4 Nov 2026 |
| RIC | `oai` (FlexRIC) | Nyata, read-only status |

---

## 4. Hybrid Core↔RAN Connect — exclusive switching (bare-metal)

Karena RAN cuma punya 1 radio fisik, dan (untuk Core, kalau nanti ditambah provider
kedua) port jaringan yang sama dipakai semua provider Core — backend **tidak bisa**
menyalakan 2 provider sekaligus di domain yang sama. Logikanya ada di
`backend/ran_hybrid.py`:

```
connect_ran_to_core(provider):
  1. stop KEDUA unit gNB dulu (srsran-gnb.service DAN oai-gnb-n40.service)
     — supaya USRP B210 benar-benar bebas sebelum salah satu dinyalakan lagi
  2. retarget AMF address di config (kalau perlu) via SSH + Python re.sub
     — BUKAN pakai `sed -i` (pernah merusak file YAML testbed ini, jadi dilarang)
  3. start unit yang dipilih
  4. verifikasi SCTP N2 (38412) berstatus ESTAB
```

**Core belum punya mekanisme serupa** karena baru ada 1 provider (`open5gs`). Kalau
nanti OAI Core ditambahkan sebagai provider kedua, exclusive switching Core HARUS
dibangun dengan pola yang sama (stop Core lama penuh → verifikasi port 38412/2152/8805
kosong → start Core baru) — **BELUM dikerjakan**, statusnya PENDING (lihat §8).

**Bug kelas umum yang pernah terjadi dan harus diwaspadai** (frontend):
`RanPage.jsx`/`CorePage.jsx` sempat salah asumsi provider pertama di daftar = provider
yang sedang di-stream data live-nya lewat WebSocket. Yang benar: backend men-stream
data provider yang **AKTIF DI DATABASE** (`telemetryMeta.active.{domain}`), bukan
selalu urutan pertama registry. Sudah diperbaiki — kalau menambah domain/provider
baru, cek ulang pola ini supaya tidak terulang.

**Bug kedua yang pernah terjadi**: badge "ACTIVE"/tombol Activate-Deactivate di
`RanPage.jsx` sempat 100% bergantung pada tabel `active_providers` di database — yang
HANYA berubah lewat tombol dashboard. Kalau radio di-switch manual via SSH langsung
(di luar dashboard), badge jadi salah menampilkan provider yang sudah mati sebagai
aktif. Sudah diperbaiki: sekarang UI poll **health nyata** semua provider tiap 5 detik
dan itu jadi sumber kebenaran utama, status DB cuma fallback.

---

## 5. Perbedaan penting antara srsRAN dan OAI di testbed ini

| Parameter | srsRAN | OAI |
|---|---|---|
| Bandwidth | 40MHz (106 PRB) | **20MHz (51 PRB)** |
| PCI | 1 | 0 |
| Config file | `n40_RICbare.yaml` | `gnb-proven-441s-lowgain.conf` |

**OAI bandwidth lebih kecil dari srsRAN** — ini bukan kesalahan konfigurasi, tapi
hasil troubleshooting: config OAI 40MHz/106PRB yang awalnya dicoba **gagal total**
(UE tidak pernah bisa menyelesaikan Random Access Msg3). Config yang **terbukti
berhasil** (ditemukan dari log historis testbed bulan September 2026,
`gnb-proven-441s.conf`) pakai 20MHz/51PRB, ditambah CLI flags krusial:

```
--MACRLCs.[0].pusch_FailureThres 100
--MACRLCs.[0].pucch_FailureThres 100
--L1s.[0].prach_dtx_threshold 300
-A -55   (frequency offset, hasil tuning manual — nilai ini SPESIFIK untuk
          oscillator USRP B210 yang ada di testbed ini, mungkin perlu di-tune
          ulang kalau USRP diganti/direkalibrasi)
```

Tuning gain radio (`max_rxgain` di config RU) juga krusial: nilai 80 (default)
menyebabkan BLER tinggi & PUCCH DTX parah (overdrive) meski SNR bagus; **50** memberi
hasil terbaik sejauh ini (goodput 4-5 Mbps). Nilai 30 terlalu rendah (sinyal UE hilang
total). Rentang optimal ada di antara 30-80, belum di-fine-tune lebih presisi.

**UE compatibility**: Oppo Reno 8 (IMSI `001013310000159`) **berhasil** connect ke
gNB OAI. **Motorola G35 tidak pernah berhasil** mendapat sinyal dari gNB OAI sama
sekali — ini konsisten dengan pengalaman percobaan bulan Agustus 2026 (masalah lama,
belum terselesaikan, root cause belum diselidiki — kemungkinan soal kapabilitas
band/modem HP tersebut terhadap konfigurasi radio OAI yang dipakai).

---

## 6. Deployment live (server RIC)

| Komponen | Detail |
|---|---|
| Backend | systemd `oran-dashboard-api.service`, uvicorn `127.0.0.1:8100`, WorkingDirectory `/home/telmat/Dashboard/OpenRAN-Dashboard/backend` |
| Frontend | nginx vhost `127.0.0.1:8200` (`/etc/nginx/sites-available/oran-dashboard-standalone.conf`), serve `/var/www/oran-dashboard-standalone`, root path |
| Akses publik | Cloudflare Quick Tunnel (**gratis**, `oran-dashboard-tunnel.service`) — **URL berubah tiap restart service/reboot**. Cek URL terkini: `journalctl -u oran-dashboard-tunnel.service -n 30 | grep trycloudflare` |
| URL per 4 Nov 2026 | `https://copyrighted-surgeons-quantum-structure.trycloudflare.com` (akan berubah lagi kalau tunnel di-restart — JANGAN hardcode URL ini sebagai permanen) |
| Login admin | `admin` / `Admin123` |

**Build & deploy ulang (frontend):**
```bash
cd /home/telmat/Dashboard/OpenRAN-Dashboard/frontend
VITE_API_BASE=/api VITE_WS_BASE=/ws npm run build
sudo rm -rf /var/www/oran-dashboard-standalone/*
sudo cp -r dist/* /var/www/oran-dashboard-standalone/
sudo chown -R www-data:www-data /var/www/oran-dashboard-standalone
```

**Restart backend (setelah ubah kode backend):**
```bash
sudo systemctl restart oran-dashboard-api.service
```

**SELALU backup dulu sebelum deploy perubahan apapun:**
```bash
cp backend/oran_dashboard.db ~/oran_dashboard.db.bak-$(date +%Y%m%d-%H%M%S)
git branch backup-before-X-$(date +%Y%m%d-%H%M%S)
```

Catatan domain: **jangan pernah numpang** ke domain `dashboard-5g.testbed-itb.my.id`
— itu domain milik tim lain di lab yang sama (pernah ketumpangan subpath `/oran/`
oleh kesalahan deploy sebelumnya, sudah 100% dibersihkan). Dashboard proyek ini
berdiri sendiri dengan Cloudflare Tunnel terpisah.

Register & forgot-password **sengaja tidak berfungsi** — butuh SMTP yang belum
dikonfigurasi di `.env` (`SMTP_HOST` kosong). Ini fail-closed by design, bukan bug.

---

## 7. Keputusan desain & pembersihan yang sudah dilakukan

- **Mock provider Core dihapus total** (`oai` lama, `open5gs` versi K8s/Docker) —
  bukan sekadar disembunyikan, kode registry-nya dihapus. Kode adapter lama tetap
  ada di `adapters.py` (dormant) untuk referensi kalau dibutuhkan lagi nanti.
- **Label "(bare-metal)" dihapus** dari nama provider Open5GS — karena sekarang semua
  provider memang berjalan native bare-metal, tidak ada campuran clustering/K8s lagi,
  jadi label itu jadi redundant.
- **Kubernetes/Helm SEPENUHNYA DIBATALKAN** untuk alur kerja operasional sehari-hari.
  `AGENTS.md` di repo masih menyebut deployment via Helm/K8s (bagian "Deploy ke K8s")
  — itu **dokumentasi usang** dari fase proyek sebelumnya, SUDAH TIDAK DIPAKAI untuk
  testbed bare-metal 3-PC ini. Jangan bingung kalau membaca referensi K8s di file itu.
- Badge status "down" di RAN diubah labelnya dari "Critical" → **"Inactive"** (atas
  permintaan pemilik proyek, supaya tidak terkesan alarm darurat).
- Ditambahkan label kecil **"N2/N3"** di bawah panah konektivitas Core↔RAN
  (`CoreRanConnectBar.jsx`) dengan tooltip penjelasan interface N2 (signaling,
  SCTP 38412) dan N3 (user plane, GTP-U UDP 2152).

---

## 8. PENDING — pekerjaan yang belum selesai

1. **OAI sebagai provider Core kedua** — docker-compose OAI Core (`oai-cn5g-fed`)
   sudah ada di host Core tapi **belum bisa dinyalakan** karena konflik port: AMF
   SCTP 38412, SMF PFCP 8805/udp, UPF GTP-U 2152/udp semuanya **sudah dipakai**
   Open5GS yang live. Solusinya sama seperti RAN: bangun exclusive Core switching
   (stop Core lama penuh → verifikasi port kosong → start Core baru) — **BELUM
   ditulis kodenya**, baru rencana desain.

2. **Fine-tuning radio OAI RAN** — gain 50 sudah lumayan (4-5 Mbps) tapi belum
   dioptimalkan lebih jauh (MCS masih terkunci rendah meski SNR bagus — kemungkinan
   ada parameter lain yang perlu disesuaikan, misal outer-loop link adaptation).

3. **Motorola G35 tidak pernah connect ke OAI RAN** — baik di percobaan Agustus
   2026 maupun November 2026. Root cause belum diselidiki sama sekali. Perlu riset
   kapabilitas band HP ini vs konfigurasi radio OAI yang dipakai testbed, atau coba
   parameter radio berbeda khusus untuk HP ini.

4. **Benchmark data lengkap untuk semua kombinasi Core×RAN** — baru kombinasi
   Open5GS+srsRAN yang selesai 3x run lengkap (10 menit tiap run, metrik: throughput
   DL/UL, RTT, packet loss, CPU/Mem Core & RAN). Open5GS+OAI baru berhasil connect
   tapi belum dijalankan sesi benchmark resmi 3x run-nya. Toolkit pengambilan data
   (sampler Python + skrip analisis) sudah siap di `/home/ubuntu/benchmark-5g/`.

5. **Proyek handover** (next phase, belum dimulai): memakai 1 Core + 2 RAN sekaligus
   untuk skenario UE berpindah sel — di luar scope dashboard versi sekarang, proyek
   terpisah untuk masa depan.

---

## 9. Hal yang JANGAN dilakukan tanpa konfirmasi eksplisit pemilik proyek

- Jangan merancang/mengerjakan apa pun yang bergantung pada Kubernetes, kubectl,
  Helm, NodePort, atau namespace — fase itu sudah dibatalkan total.
- Jangan ubah konfigurasi testbed yang sedang dipakai tim lain tanpa konfirmasi
  testbed benar-benar kosong (cek traffic `ogstun` idle, cek log AMF untuk sesi UE
  aktif) — testbed ini dipakai bergantian oleh beberapa orang.
- Jangan pakai `sed -i` untuk edit config YAML di testbed (pernah merusak file) —
  pakai Python `re.sub` via SSH.
- Jangan commit file `.env` (backend) ke git — isinya kredensial SSH testbed.
- Jangan asumsikan domain/provider yang belum nyata (`MagmaCoreAdapter`,
  placeholder RIC) sudah live — cek `adapters.py` dulu sebelum klaim sesuatu
  "sudah terhubung ke testbed".
- Jangan mengubah `allow_origins=["*"]` di CORS backend diam-diam — itu sengaja
  untuk kemudahan dev lab, sudah didokumentasikan di kode.

---

## 10. Referensi tambahan

- `AGENTS.md` di root repo — panduan asli untuk coding agent, pola adapter lebih
  detail, environment variables lengkap. **Catatan**: bagian "Deploy ke K8s" di
  file itu sudah usang (lihat §7 di atas).
- Referensi eksternal yang pernah dipakai untuk riset/troubleshooting:
  `github.com/giticarusWalks/5g-testbed` (proyek serupa tim lain, pakai OCUDU —
  penerus/rebrand srsRAN Project, BUKAN OAI — jadi config di repo itu tidak
  langsung applicable untuk tuning OAI).
