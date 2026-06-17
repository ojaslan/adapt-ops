# Production Deployment Guide

## Overview

ADAPT-OPS can be deployed in multiple environments. This guide covers common deployment scenarios.

---

## Option 1: Docker (Recommended for Development/Testing)

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/ojaslan/adapt-ops.git
cd adapt-ops

# 2. Create .env file (copy from .env.example)
cp .env.example .env

# 3. Build and run with Docker Compose
docker-compose up -d

# 4. Verify
curl http://localhost:8000/health
```

### Check Logs

```bash
docker-compose logs -f adapt-ops
```

### Stop

```bash
docker-compose down
```

---

## Option 2: Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (1.20+)
- kubectl configured
- Storage provisioner (for persistent MAB state)

### Deploy

```bash
# Create namespace
kubectl create namespace adapt-ops

# Create ConfigMap for configuration
kubectl create configmap adapt-ops-config \
  --from-env-file=.env \
  -n adapt-ops

# Apply deployment
kubectl apply -f k8s/deployment.yaml -n adapt-ops
kubectl apply -f k8s/service.yaml -n adapt-ops

# Verify
kubectl get pods -n adapt-ops
kubectl logs -f deployment/adapt-ops -n adapt-ops
```

### Example deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: adapt-ops
  namespace: adapt-ops
spec:
  replicas: 1
  strategy:
    type: RollingUpdate
  selector:
    matchLabels:
      app: adapt-ops
  template:
    metadata:
      labels:
        app: adapt-ops
    spec:
      containers:
      - name: adapt-ops
        image: adapt-ops:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
          name: http
        envFrom:
        - configMapRef:
            name: adapt-ops-config
        volumeMounts:
        - name: data
          mountPath: /app/.data
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
      volumes:
      - name: data
        emptyDir: {}
```

### Example service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: adapt-ops
  namespace: adapt-ops
spec:
  selector:
    app: adapt-ops
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
    name: http
  type: ClusterIP
```

### Access via Port Forward

```bash
kubectl port-forward svc/adapt-ops 8000:80 -n adapt-ops
# Now accessible at http://localhost:8000
```

---

## Option 3: VM/Bare Metal

### Prerequisites

- Python 3.9+
- pip
- systemd (for service management)

### Installation

```bash
# 1. Clone
git clone https://github.com/ojaslan/adapt-ops.git
cd adapt-ops

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env
cp .env.example .env
# Edit .env with your settings

# 5. Test run
python simulate.py
```

### Setup as systemd Service

Create `/etc/systemd/system/adapt-ops.service`:

```ini
[Unit]
Description=ADAPT-OPS Self-Healing Pipeline Optimizer
After=network.target
StartLimitInterval=60s
StartLimitBurst=3

[Service]
Type=simple
User=adapt-ops
WorkingDirectory=/opt/adapt-ops
Environment="PATH=/opt/adapt-ops/venv/bin"
ExecStart=/opt/adapt-ops/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

### Enable and Start

```bash
# Create user
sudo useradd -r -s /bin/bash adapt-ops

# Copy files
sudo mkdir -p /opt/adapt-ops
sudo cp -r . /opt/adapt-ops/
sudo chown -R adapt-ops:adapt-ops /opt/adapt-ops

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable adapt-ops
sudo systemctl start adapt-ops

# Verify
sudo systemctl status adapt-ops
sudo journalctl -u adapt-ops -f
```

---

## Option 4: AWS Lambda + API Gateway

### Limitations

- Lambda has cold-start overhead
- Best for low-volume integrations
- Consider ECS Fargate for production workloads

### Deployment

```bash
# 1. Install AWS CLI and SAM
pip install aws-cdk

# 2. Deploy with CDK
cdk deploy
```

### Alternative: Manual Lambda Packaging

```bash
# Create deployment package
mkdir package
pip install -r requirements.txt -t package/
cp -r api core config.py package/
cd package
zip -r ../adapt-ops.zip .

# Upload to AWS Lambda
aws lambda create-function \
  --function-name adapt-ops \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT:role/lambda-role \
  --handler api.main:app \
  --zip-file fileb://../adapt-ops.zip
```

---

## Option 5: GitHub Actions Self-Hosted Runner

Deploy ADAPT-OPS on a self-hosted GitHub Actions runner:

```yaml
name: Deploy ADAPT-OPS

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v3
      
      - name: Stop current instance
        run: systemctl stop adapt-ops || true
      
      - name: Update code
        run: cd /opt/adapt-ops && git pull
      
      - name: Install dependencies
        run: /opt/adapt-ops/venv/bin/pip install -r /opt/adapt-ops/requirements.txt
      
      - name: Start service
        run: systemctl start adapt-ops
      
      - name: Verify
        run: curl http://localhost:8000/health
```

---

## Production Checklist

### Security

- [ ] Use HTTPS/TLS (proxy through Nginx/HAProxy)
- [ ] Set up authentication (API key, OAuth)
- [ ] Configure CORS properly (don't use `*`)
- [ ] Run in isolated network namespace
- [ ] Regularly update dependencies (`pip list --outdated`)

### Monitoring

- [ ] Set up health checks (Prometheus, DataDog)
- [ ] Configure alerting on high anomaly rates
- [ ] Monitor MAB state staleness
- [ ] Track API response times
- [ ] Set up log aggregation (ELK, CloudWatch)

### High Availability

- [ ] Run multiple instances behind load balancer
- [ ] Use shared persistent storage for MAB state (NFS, S3)
- [ ] Configure graceful shutdown
- [ ] Set up database for metrics history

### Performance

- [ ] Monitor CPU/memory usage
- [ ] Configure resource limits
- [ ] Enable caching for `/mab/rankings`, `/config`
- [ ] Consider CDN for static content

### Backups

- [ ] Backup `.data/mab_state.json` regularly
- [ ] Version control MAB state changes
- [ ] Test recovery procedures

---

## Monitoring & Observability

### Prometheus Integration

Add to your Prometheus config:

```yaml
scrape_configs:
  - job_name: 'adapt-ops'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

### Key Metrics to Monitor

```
adapt_ops_metrics_processed_total
adapt_ops_anomalies_detected_total
adapt_ops_healings_triggered_total
adapt_ops_heal_success_rate
adapt_ops_mab_decision_latency_seconds
adapt_ops_mab_state_age_seconds
```

### CloudWatch (AWS)

```python
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')

def send_metric(metric_name, value):
    cloudwatch.put_metric_data(
        Namespace='ADAPT-OPS',
        MetricData=[{
            'MetricName': metric_name,
            'Value': value,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow()
        }]
    )
```

---

## Troubleshooting

### MAB State File Corruption

```bash
# Reset to clean state
rm .data/mab_state.json
curl -X POST http://localhost:8000/reset
```

### High Memory Usage

```bash
# Reduce history size in .env
MAX_HISTORY_SIZE=1000

# Or clear history manually
curl -X POST http://localhost:8000/reset
```

### Slow Anomaly Detection

Check window size and Z-score calculation:

```bash
# Reduce window size for faster response
ANOMALY_WINDOW_SIZE=15
```

### API Timeouts

```bash
# Increase healing cooldown to reduce load
HEALING_COOLDOWN_SECS=120
```

---

## Scaling Considerations

### Horizontal Scaling

Multiple ADAPT-OPS instances with shared state:

```yaml
# Use NFS for shared .data directory
volumes:
  - nfs-server:/opt/adapt-ops/.data
```

### Vertical Scaling

Adjust resource limits based on metrics volume:

- **Low volume** (< 100 req/min): 128MB RAM, 100m CPU
- **Medium volume** (100-1000 req/min): 256MB RAM, 250m CPU
- **High volume** (> 1000 req/min): 512MB+ RAM, 500m+ CPU

---

## Support

For deployment issues:

1. Check logs: `docker-compose logs adapt-ops`
2. Review configuration: `cat .env`
3. Test connectivity: `curl http://localhost:8000/health`
4. Open GitHub issue with full context
