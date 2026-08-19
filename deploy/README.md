# Deploy O-RAN Dashboard ke Kubernetes (Helm)

Dashboard (`argaulyaa/OpenRAN-Dashboard`) bisa di-deploy sebagai **Helm chart** ke cluster K8s testbed.

## Struktur
```
deploy/helm/oran-dashboard/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── backend-deployment.yaml   # FastAPI, SSH ke Core/RAN
    ├── frontend-deployment.yaml  # nginx serve build + proxy /api & /ws
    ├── backend-service.yaml      # ClusterIP :8000
    ├── frontend-service.yaml     # NodePort (default 30080) / LoadBalancer / Ingress
    ├── configmap.yaml            # host IP, container map, DATABASE_URL
    ├── secret.yaml               # ORAN_USERS, password SSH
    ├── pvc.yaml                  # opsional (persistence.enabled)
    └── ingress.yaml              # opsional
```

## 1. Build image
Dari root repo, build 2 image:

```bash
# Backend
docker build -t ghcr.io/argaulyaa/openran-dashboard-backend:latest -f backend/Dockerfile backend/

# Frontend (multi-stage: node build → nginx)
docker build -t ghcr.io/argaulyaa/openran-dashboard-frontend:latest -f frontend/Dockerfile frontend/
```

> Repository di `values.yaml` tinggal ganti ke registry lu (GHCR / Docker Hub / registry internal).  
> Login dulu: `docker login ghcr.io -u <user>`.

## 2. Push image
```bash
docker push ghcr.io/argaulyaa/openran-dashboard-backend:latest
docker push ghcr.io/argaulyaa/openran-dashboard-frontend:latest
```

## 3. Install Helm chart
Sesuaikan `values.yaml` (terutama `backend.oai.sshPassword`, `backend.ran.sshPassword`, `auth.oranUsers`), lalu:

```bash
cd deploy/helm/oran-dashboard
helm install oran . --namespace dashboard --create-namespace
```

Opsi: kasih values lewat CLI
```bash
helm install oran . -n dashboard --create-namespace \
  --set backend.oai.sshPassword='XXX' \
  --set backend.ran.sshPassword='XXX' \
  --set auth.oranUsers='admin:secret'
```

## 4. Akses
```bash
kubectl get svc -n dashboard
# oran-frontend NodePort 30080 →
# http://<INTERNAL-IP-node-mana-pun>:30080/
```

## 5. Verifikasi
```bash
curl http://<node-ip>:30080/api/health                      # backend
curl "http://<node-ip>:30080/api/core/components?provider=oai"  # real OAI (via SSH ke Core)
curl "http://<node-ip>:30080/api/ran/components?provider=oai"   # real RAN (kalau ran.sshHost diset)
```

## Syarat / catatan
- **SSH dari pod → node testbed**: Pod backend perlu reach `10.91.2.151:22` (Core) & `10.91.2.152:22` (RAN). Default egress pod ke IP LAN node berfungsi (SNAT), tapi pastikan firewall node mengizinkan SSH dari IP pod/Calico (192.168.0.0/16).
- **Persistensi**: default `persistence.enabled=false` (emptyDir — data audit hilang saat pod dibuat ulang). Aktifkan PVC kalau storage class udah ada, atau tambah hostPath PV.
- **Ingress/LoadBalancer**: kalau mau akses via `:80` bersih, pasang ingress-controller + `frontend.serviceType: LoadBalancer` (butuh MetalLB) atau aktifkan `frontend.ingress`.
- **Frontend proxying**: nginx di image frontend otomatis proxy `/api` & `/ws` ke service backend `oran-backend:8000` (env `BACKEND_HOST`, di-render via envsubst di image nginx).
- **Upgrade**: `helm upgrade oran . -n dashboard` setelah ubah values.
