# Changelog

## 2026-08-25 - Revisi: TopBar sticky title-only, Current Operator pindah ke body sejajar provider tabs

### Keputusan Owner (revisi atas entri di bawah)
TopBar sticky kembali HANYA menampilkan judul per-page (Core/RAN juga dapat
subtitle). Badge Current Operator TIDAK lagi ada di TopBar — kotak operator
pindah ke body halaman Core & RAN, sejajar dengan provider tabs. RIC sengaja
tanpa kotak operator. Implementasi oleh worker paralel (hermes-bill, commit
60b7334), diverifikasi independen oleh Dev.

### Perubahan (`frontend/`, commit 60b7334)
- `components/PageHeaderContext.jsx` (BARU): context `PageHeaderProvider` +
  hook `usePageHeader({title, subtitle, right})` — page aktif mengisi isi
  header sticky; mode tanpa argumen = GET (dipakai TopBar).
- `App.jsx`: `<Routes>` dibungkus `PageHeaderProvider`.
- `components/TopBar.jsx` (rewrite): sticky title-only — judul + subtitle dari
  `usePageHeader()`, fallback map PAGE_TITLES untuk page yang tidak set
  header. Slot kanan/operator badge DIHAPUS.
- `pages/CorePage.jsx`: judul h2 lokal + strip lama dihapus;
  `usePageHeader({title, subtitle, right:null})`; baris atas body =
  wrapper flex (kiri provider tabs, kanan kotak Current Operator dengan
  HEALTH_BADGE fallback "NO ACTIVE PROVIDER"); logika `currentOperator`
  (useMemo) tidak berubah.
- `pages/RanPage.jsx`: block judul lokal dihapus; TAMBAHAN state
  `currentOperator` RAN baru (useMemo domainHealth dari WebSocket
  components); kotak operator disisipkan sejajar tabs pola sama dgn Core.
- `pages/RicPage.jsx`: judul lokal duplikat dihapus via usePageHeader
  ("RIC Management" + subtitle), tanpa kotak operator.

### Verifikasi Dev (independen)
- Diff 60b7334 sesuai brief owner poin 1–5 (title-only sticky, operator di
  body sejajar tabs Core+RAN, RAN state baru, RIC bersih).
- `npm run build` (vite) di clone bersih @60b7334: exit 0, built 2.54s.

## 2026-08-25 - TopBar sticky: judul per-page + Current Operator, CorePage strip di-revert

### Keputusan Owner
Strip full-width di CorePage (t_4c729fd9) dibatalkan. Judul halaman + badge
Current Operator kini dirender di TopBar global yang jadi STICKY — tetap
terlihat saat scroll, berlaku untuk semua halaman.

### Perubahan
- `frontend/src/components/TopBar.jsx` (rewrite):
  - `fixed` → `sticky top-0` in-flow; lebar tetap `md:w-[calc(100%-280px)]
    md:ml-sidebar-width`, `z-40`, bg-surface-bright, border-b (identik visual).
  - Kiri: judul halaman aktif via `useLocation()` (map path → title:
    Overview / Core Network Management / Radio Access Network / RIC
    Management / Node Reservations / Profile / Audit Logs).
  - Kanan: badge Current Operator HANYA di route `/core`, `/ran`, `/ric`.
    Data-driven dari backend: `fetchProviders(domain)` sekali per mount +
    health provider non-default (`fetchComponents`) sekali; health default
    provider di-poll tiap 15 detik selama user di halaman domain itu.
    Pemilihan operator sama dgn logika halaman: provider healthy pertama,
    fallback degraded, kalau nggak ada → "None" + "NO ACTIVE PROVIDER".
  - Search/telemetry/notifikasi/bantuan TETAP terhapus (keputusan t_2d1fb375).
- `frontend/src/pages/CorePage.jsx`: REVERT persis ke state sebelum commit
  strip (checkout dari 4c8cfa6) — header "Core Network Management" + kotak
  Current Operator balik ke dalam container `max-w-[1400px] mx-auto`,
  fragment strip full-width dihapus.
- `frontend/src/App.jsx`: `<main>` `pt-20` → `pt-4` karena TopBar bukan fixed
  lagi (tidak ada konten tertutup); sisanya tak disentuh.
- Catatan: badge Current Operator di CorePage/RanPage/RicPage tetap ada
  (redundansi sengaja, konten halaman tidak diubah).

### Verifikasi
- `npm run build` (vite): sukses, exit 0, built in 2.31s.

## 2026-08-25 - Header Core page jadi full-width top strip

### Keputusan Owner
Header halaman Core (judul + kotak Current Operator) dipindah jadi strip
full-width di PALING ATAS konten Core page, menggantikan posisi visual
TopBar global yang sudah dikosongkan sebelumnya.

### Perubahan
- `frontend/src/pages/CorePage.jsx`:
  - Block header (`Core Network Management` + subtitle + kotak Current
    Operator) dikeluarkan dari container `max-w-[1400px] mx-auto`.
  - Return kini fragment `<>` dengan 2 anak: (1) header-strip full-width
    `relative z-10 bg-surface-bright border-b border-outline-variant px-gutter py-4 flex items-center justify-between gap-4`
    (pola visual diambil dari TopBar lama), (2) container
    `max-w-[1400px] mx-auto` berisi sisa konten (Provider Selector Tabs,
    Bento Grid, tabel connections).
  - Isi/badge Current Operator, state, dan logika TIDAK diubah.
- `TopBar.jsx`, `App.jsx`, dan page lain tidak tersentuh.

### Verifikasi
- `npm run build` (vite v5.4.21): sukses, 66 modules transformed, exit 0.
- Commit `aaa2b78` pushed ke `main`.

## 2026-08-25 - TopBar dibersihkan: search, telemetry, notifikasi, bantuan dihapus

### Keputusan Owner
Empat elemen di baris paling atas halaman (top bar) dihapus dari SEMUA page.

### Perubahan
- `frontend/src/components/TopBar.jsx`:
  - Hapus input search (`placeholder="Search infrastructure..."`) beserta wrapper div-nya.
  - Hapus indikator `Telemetry live / Connecting... / Disconnected` beserta
    konstanta `WS_LABEL` dan `WS_DOT` (kini unused).
  - Hapus tombol ikon `notifications` (bel) dan `help_outline` (tanda tanya).
  - Prop `wsStatus` dihapus dari signature; header kanan kini kosong total
    (tidak ada elemen lain di file ini yang layak dipertahankan).
- `App.jsx` TIDAK diubah: tetap mengirim `wsStatus={wsStatus}` ke `<TopBar/>`;
  React mengabaikan prop tak terpakai sehingga aman tanpa edit pemanggil.
- Sidebar, page lain, dan logika lain tidak tersentuh.

### Verifikasi
- `npm run build` (vite v5.4.21): sukses, 66 modules transformed, exit 0.
- Commit `ff46822` pushed ke `main`.

## 2026-08-24 - RBAC disederhanakan: 2 role (admin + user), audit log admin-only

### Keputusan Owner
Model 3-role (admin/engineer/viewer) diganti **2 role: `admin` + `user`**.
Role `user` = setara engineer lama (operasi penuh: reservasi, Console SSH,
Activate/Deactivate provider, restart). Role `admin` = user + kelola role akun
lain + **satu-satunya yang boleh membaca audit log** (lubang keamanan ditutup).
Self-register default `user` (sebelumnya `viewer`).

### Perubahan Backend
- `backend/auth.py`:
  - Seed admin (`_DEFAULT_USERS` / `init_auth_data`) kini dibuat dengan role
    **`admin`** (dulu `engineer`).
  - Fungsi baru `_normalize_role()`: nilai legacy apa pun (`engineer`,
    `viewer`, unknown/null) dibaca sebagai `user`; hanya `admin` istimewa
    (lazy migration, tanpa skrip DB).
  - `require_engineer` diganti `require_operator` (menerima `user`+`admin`)
    dan dependensi baru `require_admin` (admin-only, dipakai audit log).
  - Self-register (`create_pending_registration`, `register_user`) hardcode
    role `user`.
- `backend/main.py`: activate/deactivate provider pakai `require_operator`;
  `PUT /api/auth/users/{username}/role` validasi target hanya `user|admin`
  (nilai legacy -> 400); `GET /api/audit-logs` kini `Depends(require_admin)`
  (403 untuk non-admin); reservasi/restart cek `user|admin`.
- `backend/models.py`: default kolom role `user`.

### Perubahan Frontend
- `frontend/src/user.js` / `auth.js`: fallback role `user`.
- Semua halaman: kondisi `viewer`/`engineer` dihapus — `user` & `admin`
  sama-sama operator penuh; Console SSH, reservasi, Activate, restart tidak
  lagi ada gate read-only.
- `Profile.jsx`: tombol promote/demote jadi toggle **Jadikan Admin /
  Jadikan User**.
- AuditLogs.jsx + route `/audit-logs`: tetap admin-only (pola lama konsisten).

### Migrasi Data
DB SQLite in-pod `/data/oran_dashboard.db` efemeral. Normalisasi role bersifat
lazy: hanya string `admin` yang dipetakan ke admin; `engineer`, `viewer`, dan
nilai tak dikenal dibaca sebagai `user`. Akun admin baru hasil seed saat pod
start otomatis ber-role `admin`; user lama engineer/viewer otomatis setara
`user` tanpa skrip migrasi DB.

### Verifikasi
- `py_compile` semua file Python yang berubah PASS.
- Test baru `backend/test_rbac_two_roles.py` **8/8 PASS**: register->user,
  admin baca audit 200, user baca audit 403, user create reservation OK,
  user activate provider OK, user PUT role orang lain 403, admin toggle
  user<->admin OK (+legacy 'engineer' 400), lazy migration legacy roles.
- Regresi: test_forgot_password 5/5, test_otp_failclosed 4/4,
  test_provider_activation 7/7 (disesuaikan kontrak baru),
  test_ran_activation 7/7.
- `npm run build` sukses (`index-D0s7Q87v.js`, 66 modules).

## 2026-08-24 - RIC page: kartu Active xApps dihapus, kotak FlexRIC full-width

### Perubahan
- `frontend/src/pages/RicPage.jsx` (satu-satunya file yang berubah, 1 insersi /
  49-51 baris dihapus):
  - Kartu samping **Active xApps** (daftar xApp + tombol MANAGE xAPPS) dihapus
    dari RIC page.
  - Kartu status utama FlexRIC lebarnya jadi **full-width** (`col-span-12`,
    sebelumnya `lg:col-span-8`).
  - Dead code ikut dibersihkan: konstanta `XAPP_KIND`, `XAPP_ICON`, dan filter
    `xapps` (tidak ada lagi referensi xApp di RicPage).

### Verifikasi
- `npx vite build` PASS (66 modules → `index-BS5jEo0N.js`).
- Live check NodePort core (`10.91.2.151:30090`) serve bundle
  `assets/index-BS5jEo0N.js` — hash identik dengan build lokal, deploy CI
  terkonfirmasi hidup.
- Tidak ada perubahan backend; endpoint & adapter RIC tidak disentuh.

### Catatan
- Implementasi landed via commit `3ff8fa9` (feat(ric): remove Active xApps
  card, widen FlexRIC card to full width); run dev paralel menghasilkan diff
  yang fungsional identik dan sudah direkonsiliasi ke origin/main.

## 2026-08-24 - RAN page: tombol Console kiri, Activate kanan, eksklusif antar provider RAN

### Perubahan
- `frontend/src/pages/RanPage.jsx` (satu-satunya file yang diubah; backend sudah
  generik sejak a9cc8c0 — endpoint `/api/{domain}/activate-provider` dll. otomatis
  melayani domain `ran` dengan provider oai + srsran):
  - Reorder tombol action bar hero card: **Console** (kiri) → **View Logs** →
    **Activate/Deactivate** (kanan), konsisten dengan CorePage.
  - Tombol Activate toggle ke `/api/ran/activate-provider` / `deactivate-provider`
    (engineer/admin only; viewer lihat status tapi disabled).
  - Eksklusif antar provider RAN: kalau satu provider aktif, tombol Activate di
    tab provider lain disabled + tooltip "Provider X sedang aktif — nonaktifkan
    dulu". Tab yang aktif dapat badge `● ACTIVE` + border secondary.
  - Saat activate: tab lain otomatis keganti (backend upsert single-row per
    domain), state UI langsung disinkronkan tanpa reload.

### Verifikasi
- `npm run build` (vite) PASS.
- Regresi `test_provider_activation.py` 7/7 PASS (domain core).
- Test baru `test_ran_activation.py` 7/7 PASS: eksklusivitas oai↔srsran,
  single-row per domain, independensi core vs ran, deactivate, idempotensi.

## 2026-08-23 - Fix permanen CI deploy (release mismatch + pullsecret)

### Masalah
- CI deploy (`deploy.yml`) menamai release helm `oran-dashboard`, padahal release yang
  benar-benar melayani situs bernama `oran` (deployment `oran-backend`/`oran-frontend`, ns
  `dashboard`, NodePort 30090). Akibatnya tiap push bikin release duplikat yang konflik, dan
  release asli tidak pernah ter-update (release mismatch).
- `rollout restart` + `--reuse-values` tidak menjamin image baru ter-deploy; image lama yang
  tercache tetap tersaji.
- ghcr.io privat tapi chart tidak me-render `imagePullSecrets`, jadi pod tak bisa menarik
  image (ImagePullBackOff) tanpa patch manual secret (pullsecret).

### Perbaikan
- `deploy.yml`: `HELM_RELEASE` kembali ke `oran`; hapus `--reuse-values`; tambah step
  "Ensure ghcr.io pull secret" (idempotent); helm upgrade --install pakai tag `github.sha`
  + `--timeout 180s --wait`.
- `deploy/helm/oran-dashboard/templates/backend-/frontend-deployment.yaml`: render
  `imagePullSecrets` (dari `image.pullSecrets`) sebagai sibling di bawah `spec:`.
- `deploy/helm/oran-dashboard/values.yaml`: default `pullSecrets: [ghcr-secret]`, pin
  backend+frontend ke node `core`, set kredensial SSH testbed, `pullPolicy: Always`, nodePort 30090.
- `AGENTS.md`: tambah section "Deploy ke K8s (CI/CD)" dengan fakta permanen.

### Verifikasi
- `helm lint` PASS; `helm template` (release `oran`) render imagePullSecrets + tag + 30090 + core.
- `helm upgrade --install oran` live di nas-master => REVISION 7 deployed, 2 pod Running di node
  `core`, imagePullSecrets hadir di manifest, `/api/health` = ok, data core/ran real via SSH.
- YAML deploy.yml & values.yaml tervalidasi.
