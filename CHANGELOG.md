# Changelog

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
