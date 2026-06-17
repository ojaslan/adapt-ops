# ADAPT-OPS Deployment Guide

## Quick Start

### 1. Local Development

```bash
# Setup virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run API server
uvicorn api.main:app --reload

# In another terminal, run simulation
python simulate.py
```

### 2. Docker Deployment

```bash
# Build image
docker build -t adapt-ops:latest .

# Run container
docker run -p 8000:8000 \
  -e MAB_ALPHA=1.0 \
  -e HEALING_COOLDOWN_SECS=60 \
  -v $(pwd)/.data:/app/.data \
  adapt-ops:latest
```

### 3. Docker Compose (Full Stack)

```bash
docker-compose up -d

# Check logs
docker-compose logs -f api

# Stop
docker-compose down
```

## Integration with CI/CD

### GitHub Actions

1. **Webhook Setup:**
   - Go to repo Settings → Webhooks
   - URL: `https://your-adapt-ops.com/webhook/github`
   - Events: Workflow runs
   - Secret: Set `GITHUB_WEBHOOK_SECRET` env var

2. **Environment Variables:**
   ```yaml
   GITHUB_WEBHOOK_SECRET: <random-secret>
   GITHUB_API_TOKEN: <your-pat-token>
   ```

3. **Integration in Workflow:**
   ```yaml
   - name: Send metrics to ADAPT-OPS
     run: |
       curl -X POST http://adapt-ops:8000/ingest \
         -H "Content-Type: application/json" \
         -d '{...metrics...}'
   ```

### Jenkins Integration

```groovy
pipeline {
    post {
        always {
            script {
                def metrics = [
                    build_duration_secs: currentBuild.durationString.toFloat(),
                    test_pass_rate: 0.95,
                    failure_rate: 0.05,
                    queue_depth: 1,
                    cpu_utilization: 0.5,
                    memory_utilization: 0.5,
                    deploy_success_rate: 0.95,
                    flaky_test_count: 0,
                    retry_count: 0,
                    pipeline_id: "${JOB_NAME}-${BUILD_NUMBER}"
                ]
                
                httpRequest(
                    url: 'http://adapt-ops:8000/ingest',
                    httpMode: 'POST',
                    contentType: 'APPLICATION_JSON',
                    requestBody: groovy.json.JsonOutput.toJson(metrics)
                )
            }
        }
    }
}
```

### GitLab CI

```yaml
after_script:
  - |
    curl -X POST http://adapt-ops:8000/ingest \
      -H "Content-Type: application/json" \
      -d '{
        "build_duration_secs": '${CI_PIPELINE_DURATION}',
        "test_pass_rate": 0.95,
        "failure_rate": 0.05,
        "queue_depth": 1,
        "cpu_utilization": 0.5,
        "memory_utilization": 0.5,
        "deploy_success_rate": 0.95,
        "flaky_test_count": 0,
        "retry_count": 0,
        "pipeline_id": "'${CI_PIPELINE_ID}'"
      }'
```

## Production Deployment

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: adapt-ops
spec:
  replicas: 2
  selector:
    matchLabels:
      app: adapt-ops
  template:
    metadata:
      labels:
        app: adapt-ops
    spec:
      containers:
      - name: api
        image: adapt-ops:latest
        ports:
        - containerPort: 8000
        env:
        - name: MAB_ALPHA
          value: "1.0"
        - name: HEALING_COOLDOWN_SECS
          value: "60"
        - name: LOG_LEVEL
          value: "INFO"
        volumeMounts:
        - name: data
          mountPath: /app/.data
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
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: adapt-ops-data

---
apiVersion: v1
kind: Service
metadata:
  name: adapt-ops
spec:
  selector:
    app: adapt-ops
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
  type: LoadBalancer

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: adapt-ops-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

### Azure Container Instances

```bash
az container create \
  --resource-group myResourceGroup \
  --name adapt-ops \
  --image adapt-ops:latest \
  --environment-variables \
    MAB_ALPHA=1.0 \
    HEALING_COOLDOWN_SECS=60 \
  --ports 8000 \
  --cpu 1 \
  --memory 2 \
  --registry-login-server <registry>.azurecr.io \
  --registry-username <username> \
  --registry-password <password>
```

## Configuration

### Environment Variables

```bash
# MAB Configuration
MAB_ALPHA=1.0                      # Exploration weight
MAB_CONTEXT_DIM=16                 # Context vector dimension

# Anomaly Detection
ANOMALY_WINDOW_SIZE=30             # Metrics window for detection
ANOMALY_MIN_SCORE=0.45             # Min score to trigger healing

# Healing
HEALING_COOLDOWN_SECS=60           # Min time between heals
HEALING_MIN_SEVERITY=2             # Min severity (1-5)

# API
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=false

# Logging
LOG_LEVEL=INFO
LOG_FILE=.data/adapt-ops.log

# GitHub Integration
GITHUB_WEBHOOK_SECRET=<secret>
GITHUB_API_TOKEN=<token>

# Storage
ENABLE_MAB_PERSISTENCE=true
ENABLE_METRICS_HISTORY=true
MAX_HISTORY_SIZE=10000
```

## Monitoring & Observability

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# System stats
curl http://localhost:8000/stats

# MAB state
curl http://localhost:8000/mab/state
```

### Metrics Endpoints

- `/stats` — Overall system statistics
- `/metrics/recent` — Recent metrics (50 default)
- `/anomalies` — Recent anomalies
- `/healings` — Recent healing attempts
- `/mab/state` — Current MAB state

### Log Analysis

```bash
# Watch logs
tail -f .data/adapt-ops.log

# Count anomalies by type
grep "ANOMALY:" .data/adapt-ops.log | awk '{print $4}' | sort | uniq -c

# Success rate
grep "reward=" .data/adapt-ops.log | awk -F'=' '{print $NF}' | awk '{s+=$1; n++} END {print "Avg reward:", s/n}'
```

## Scaling Considerations

### Performance Tuning

| Parameter | Low Load | High Load |
|-----------|----------|-----------|
| MAB_ALPHA | 0.5 | 2.0 |
| HEALING_COOLDOWN_SECS | 30 | 120 |
| ANOMALY_WINDOW_SIZE | 20 | 60 |
| MAX_HISTORY_SIZE | 5000 | 50000 |

### Data Retention

- Metrics stored in `.data/metrics.jsonl`
- Anomalies stored in `.data/anomalies.jsonl`
- Healings stored in `.data/healings.jsonl`
- Automatic trimming when file > 10MB

### High Availability

1. **Multi-region deployment** with load balancer
2. **Persistent volume** for MAB state
3. **Read replicas** for metrics queries
4. **Redis cache** for frequent queries (optional)

## Troubleshooting

### No anomalies detected?
- Check `ANOMALY_MIN_SCORE` (lower = more sensitive)
- Verify metrics are being ingested
- Check `/metrics/recent` endpoint

### Healing not triggering?
- Check `HEALING_COOLDOWN_SECS` (cooling period)
- Check `HEALING_MIN_SEVERITY` (min level required)
- Verify anomaly detection working

### API not responding?
- Check port 8000 is open
- Check logs: `tail -f .data/adapt-ops.log`
- Restart container

## Cost Optimization

- **Metrics storage**: ~1-2 GB/month typical
- **CPU**: 0.5 CPU for low load, 2 CPU for high load
- **Memory**: 512 MB min, 2 GB recommended
- **Disk**: Automatic cleanup after 10GB

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
