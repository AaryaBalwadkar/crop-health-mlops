# AgriCNXEdge Web — MLOps Crop-Health Inference

FastAPI + ONNX Runtime API serving a 126MB crop-health model, React + Vite UI, full MLOps loop: CI/CD, Ansible, Docker, Kubernetes, Prometheus + Grafana, and a test-and-drop GCP deploy that stays inside Always Free.

> Interview note: the live GCP VM was deleted after recording to avoid billing. This README + the demo video + screenshots below are the permanent proof. Every claim maps to a file and a screenshot number (S1–S9).

## 30-second pitch

Leaf/pest/fruit inference from one ONNX model at 512x512, served by one container or one VM. Single-origin frontend + `/api`, `/api/metrics` for monitoring, GitHub Actions for CI, Ansible for VM config, Compose for local monitoring, kind manifests for Kubernetes, GCE `e2-micro` for the live demo.

## Architecture

```text
Browser → Nginx (:80) → Vite dist (/) + FastAPI 127.0.0.1:8000 (/api/)
FastAPI → InferenceService → adc_student_full.onnx (CPU) → leaf/pest/fruit + boxes
FastAPI → /api/metrics → Prometheus :9090 → Grafana :3000
CI: GitHub Actions build-test → (gated) SSH deploy
VM: Ansible apt/nginx/systemd/swap → scp code+dist+model → systemctl restart
```

## Stack & repo map

* Frontend: `frontend/src/App.jsx:1`, API client `frontend/src/lib/api.js:1` (same-origin), dev proxy `frontend/vite.config.js:6`
* Backend: app `backend/app/main.py:8` (serves `/` + `/api`), routes `backend/app/api/routes.py:7` (`/health`, `/model/status`, `/predict`, `/metrics`), inference `backend/app/services/inference.py:15`, config `backend/app/core/config.py:6`
* CI: `.github/workflows/ci-cd.yml:13` (S1)
* Ansible: `ansible/playbook.yml:9` (swap + nginx + systemd), `ansible/inventory.gcp.ini`, `ansible/group_vars/webservers.yml:7`, templates `ansible/templates/nginx-agricnxedge.conf.j2:1`, `ansible/templates/agricnxedge-api.service.j2:1` (S3)
* Docker: `Dockerfile` (node build → python:3.11-slim, non-root, `${PORT}`, model not baked), `docker-compose.yml` (api + prometheus + grafana)
* K8s: `k8s/namespace.yaml`, `k8s/api-deployment.yaml`, `k8s/api-service.yaml`
* Monitoring: `monitoring/prometheus.yml`, `monitoring/grafana/provisioning/datasources/prometheus.yml`, tests `backend/tests/test_metrics.py:1`
* GCP Track B: `scripts/gcp-trackb.ps1`, `scripts/deploy-trackb.sh`
* Model (gitignored, 126MB): `backend/models/adc_student_full.onnx` — never committed; injected via volume/scp/GCS.

## Run it (pick one)

Local API + UI:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\..\AgriCNXEdge\app\src\main\assets\adc_student_full.onnx models\adc_student_full.onnx
python -m pytest -q
python -m uvicorn app.main:app --reload --port 8000
cd ..\frontend
npm install
npm run dev
```

Docker monitoring stack (needs Docker Desktop running):

```bash
docker compose up --build
# UI: http://localhost:8000/  API: http://localhost:8000/api/health
# Metrics: http://localhost:8000/api/metrics
# Prometheus: http://localhost:9090  Grafana: http://localhost:3000 (admin/admin)
```

Kubernetes (kind):

```bash
docker build -t agricnxedge-web:latest .
kind create cluster --name agricnxedge
kind load docker-image agricnxedge-web:latest --name agricnxedge
kubectl apply -f k8s/namespace.yaml -f k8s/api-deployment.yaml -f k8s/api-service.yaml
kubectl -n agricnxedge port-forward svc/agricnxedge-api 8000:80
```

GCP Track B test-and-drop (us-central1, e2-micro, 30GB pd-standard — the only free combo):

```powershell
.\scripts\gcp-trackb.ps1 -Project YOUR_PROJECT -Zone us-central1-a -Action create
# copy IP -> ansible/inventory.gcp.ini
```

```bash
# WSL2 Ubuntu controller:
pip install ansible
ansible -i ansible/inventory.gcp.ini webservers -m ping
ansible-playbook -i ansible/inventory.gcp.ini ansible/playbook.yml
bash scripts/deploy-trackb.sh <VM_IP> <GCE_USER>
# verify: http://<VM_IP>/ http://<VM_IP>/api/health http://<VM_IP>/api/model/status
```

```powershell
.\scripts\gcp-trackb.ps1 -Project YOUR_PROJECT -Zone us-central1-a -Action delete
```

## Demo proof (video chapters + screenshots)

Record once, then delete the VM. Keep these 9 artifacts in `docs/` or release assets:

* S1 CI: Actions `build-test` green tick + `pytest 2 passed` + `npm run build` output
* S2 GCP: console `e2-micro us-central1-a`, 30GB pd-standard, ephemeral IP, `allow-http`
* S3 Ansible: `ansible-playbook` PLAY RECAP `ok` + `ping pong`
* S4 VM: `systemctl status agricnxedge-api`, `nginx -t`, `free -h` showing swap, `curl 127.0.0.1:8000/api/health`
* S5 App: UI with uploaded leaf + prediction JSON (filename, latency_ms, leaf/pest/fruit, apple_count)
* S6 API: `/docs`, `/api/health model_loaded:true`, `/api/model/status` inputs/outputs
* S7 Docker: `docker compose ps`, Prometheus targets UP, Grafana Prometheus datasource + latency graph
* S8 K8s: `kubectl -n agricnxedge get all`, `describe deployment`, port-forward curl
* S9 Billing: $0 / $1 budget, `instances/disks/addresses list` empty after delete

Suggested 8-min video: 0:00 problem+architecture, 0:45 S1, 1:30 S2–S3, 3:30 S4–S6 live inference, 5:30 S7–S8, 7:00 S9 teardown + free-tier math, 7:30 tradeoffs + future work.

## What to say in interviews (use these lines)

* 2-min: "Single-origin FastAPI serves both UI and API so CORS and Cloud Run both stay simple. Model is gitignored and volume-mounted to keep the image under free-tier registry limits. Ansible owns inside-the-OS, Terraform/gcloud owns the cloud objects — that's why Ansible can't deploy Cloud Run."
* Tradeoff: "e2-micro 1GB needs swap and local frontend build; Oracle 12GB ARM would fit easily but adds ARM wheel risk and capacity fights. GCP US-only free adds India latency — fine for a demo, not for prod."
* Monitoring: "Counters `predict_requests_total{outcome}` + latency histogram feed Prometheus; Grafana alerts on error rate. Health/readiness probes reuse `/api/health` in Compose and K8s."
* If asked why VM not serverless: "Assignment required 100% Ansible, which needs SSH+systemd. Same image runs on Cloud Run with `${PORT}` when cost, not marks, is the goal."

## Free-tier math (test-and-drop)

1 VM x 4h ≈ 0.5% of 720h monthly hours; disk 30GB x 4h ≈ 0.16 GB-month; egress demo ≈ 50MB of 1GB. Delete VM + disk + static IP same day and billing stops. Budget alert at $1 before create.

## Future work

Bake model via GCS + `--build-arg` for Cloud Run, WIF GitHub→GCP deploy, Helm `kube-prometheus-stack` ServiceMonitor, auth + rate limits on `/predict`, ARM test for Oracle A1.
