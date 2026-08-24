# Changelog

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
