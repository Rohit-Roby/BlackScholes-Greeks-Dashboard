# Google Cloud Platform (GCP) Deployment Guide

## Overview
Deploying the Options Greeks Calculator to Google Cloud using:
- **Cloud Run**: Serverless container platform (Recommended - simplest)
- **Compute Engine**: VM-based deployment
- **App Engine**: Managed platform as a service
- **Cloud SQL**: Managed database for future features

---

## Prerequisites
- GCP Account with billing enabled
- Google Cloud SDK installed (`gcloud` CLI)
- Docker installed locally
- Project created in GCP Console

---

## Option 1: Cloud Run (Recommended - Easiest)

### Step 1: Setup GCP Project

```bash
# Set project
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable compute.googleapis.com
```

### Step 2: Configure Docker Authentication

```bash
# Configure Docker to use gcloud
gcloud auth configure-docker gcr.io

# Create service account
gcloud iam service-accounts create options-greeks-sa \
  --display-name "Options Greeks Service Account"
```

### Step 3: Build and Push Docker Image

```bash
# Clone repository
git clone https://github.com/your-repo/options_greeks_calculator.git
cd options_greeks_calculator

# Build for Cloud Run (add PORT env support)
docker build -f backend/Dockerfile -t gcr.io/$PROJECT_ID/options-greeks-api:latest ./backend

# Push to Container Registry
docker push gcr.io/$PROJECT_ID/options-greeks-api:latest

# Build frontend
docker build -t gcr.io/$PROJECT_ID/options-greeks-frontend:latest ./frontend
docker push gcr.io/$PROJECT_ID/options-greeks-frontend:latest
```

### Step 4: Deploy Backend to Cloud Run

```bash
# Deploy backend service
gcloud run deploy options-greeks-api \
  --image gcr.io/$PROJECT_ID/options-greeks-api:latest \
  --platform managed \
  --region us-central1 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 3600 \
  --set-env-vars ENVIRONMENT=production,DEBUG=false,LOG_LEVEL=WARNING \
  --allow-unauthenticated

# Get service URL
gcloud run services describe options-greeks-api --region us-central1
```

### Step 5: Deploy Frontend to Cloud Run

```bash
# Deploy frontend (Nginx container)
gcloud run deploy options-greeks-frontend \
  --image gcr.io/$PROJECT_ID/options-greeks-frontend:latest \
  --platform managed \
  --region us-central1 \
  --memory 256Mi \
  --port 80 \
  --allow-unauthenticated
```

### Step 6: Setup Cloud Load Balancer

```bash
# Create backend service for API
gcloud compute backend-services create options-greeks-api-backend \
  --protocol HTTP \
  --global \
  --health-checks http-basic-check

# Create URL map
gcloud compute url-maps create options-greeks-lb \
  --default-service options-greeks-api-backend

# Create HTTP proxy
gcloud compute target-http-proxies create options-greeks-proxy \
  --url-map options-greeks-lb

# Create forwarding rule
gcloud compute forwarding-rules create options-greeks-lb-rule \
  --global \
  --target-http-proxy options-greeks-proxy \
  --address-region us-central1
```

---

## Option 2: Compute Engine VM Deployment

### Step 1: Create Compute Engine Instance

```bash
# Create instance
gcloud compute instances create options-greeks-vm \
  --image-family ubuntu-2204-lts \
  --image-project ubuntu-os-cloud \
  --machine-type e2-small \
  --zone us-central1-a \
  --tags greeks-app \
  --metadata startup-script='#!/bin/bash
    apt-get update
    apt-get install -y docker.io docker-compose git
    usermod -aG docker ubuntu
    cd /home/ubuntu
    git clone https://github.com/your-repo/options_greeks_calculator.git
    cd options_greeks_calculator
    docker-compose -f docker-compose.prod.yml up -d
  '
```

### Step 2: Configure Firewall Rules

```bash
# Allow HTTP
gcloud compute firewall-rules create allow-http \
  --allow tcp:80 \
  --target-tags greeks-app

# Allow HTTPS
gcloud compute firewall-rules create allow-https \
  --allow tcp:443 \
  --target-tags greeks-app

# Allow SSH
gcloud compute firewall-rules create allow-ssh \
  --allow tcp:22 \
  --target-tags greeks-app
```

### Step 3: Connect and Configure

```bash
# SSH into instance
gcloud compute ssh options-greeks-vm --zone us-central1-a

# Clone and deploy
git clone https://github.com/your-repo/options_greeks_calculator.git
cd options_greeks_calculator

# Setup .env
cp .env.example .env
nano .env  # Edit with production settings

# Start services
docker-compose -f docker-compose.prod.yml up -d
```

---

## Option 3: App Engine Deployment

### Step 1: Create app.yaml Configuration

```yaml
# app.yaml
runtime: custom
env: flex

service: default

env_variables:
  ENVIRONMENT: "production"
  DEBUG: "false"
  LOG_LEVEL: "WARNING"

resources:
  cpu: 1
  memory_gb: 1
  disk_size_gb: 20

automatic_scaling:
  min_instances: 1
  max_instances: 3
  min_cpu_utilization: 0.5
  min_pending_latency: 400ms

handlers:
  - url: /.*
    script: auto
    secure: always
    redirect_http_response_code: 301

health_check:
  enable_health_checking: true
  check_interval_sec: 30
```

### Step 2: Deploy to App Engine

```bash
# Deploy
gcloud app deploy

# View logs
gcloud app logs read

# View service
gcloud app describe
```

---

## Post-Deployment Configuration

### 1. Setup Cloud DNS

```bash
# Create DNS zone
gcloud dns managed-zones create options-greeks \
  --dns-name yourdomain.com \
  --description "Options Greeks DNS"

# Create A record
gcloud dns record-sets update yourdomain.com \
  --rrdatas=LOAD_BALANCER_IP \
  --ttl=300 \
  --type=A \
  --zone=options-greeks
```

### 2. Setup SSL/TLS with Cloud Armor

```bash
# Create SSL certificate
gcloud compute ssl-certificates create options-greeks-cert \
  --certificate mycert.crt \
  --private-key mykey.key

# Apply to load balancer
gcloud compute target-https-proxies create options-greeks-https-proxy \
  --ssl-certificates=options-greeks-cert \
  --url-map=options-greeks-lb
```

### 3. Setup Cloud Monitoring

```bash
# View metrics in Cloud Console
gcloud monitoring metrics-descriptors list | grep compute

# Create alert policy
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="High CPU Alert"
```

### 4. Setup Cloud Logging

```bash
# View logs
gcloud logging read "resource.type=cloud_run_revision"

# Filter logs
gcloud logging read "severity=ERROR" --limit 50
```

---

## Environment Variables Configuration

### Create Secret for Sensitive Data

```bash
# Create secret
echo -n "your-secret-key-here" | gcloud secrets create greeks-secret-key \
  --data-file=-

# Grant service account access
gcloud secrets add-iam-policy-binding greeks-secret-key \
  --member=serviceAccount:options-greeks-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

### Update Cloud Run with Secret

```bash
gcloud run services update options-greeks-api \
  --update-secrets SECRET_KEY=greeks-secret-key:latest \
  --region us-central1
```

---

## Scaling Configuration

### Auto-scaling for Cloud Run

```bash
# Update auto-scaling settings
gcloud run services update options-greeks-api \
  --min-instances=1 \
  --max-instances=10 \
  --region us-central1
```

### Auto-scaling for Compute Engine

```bash
# Create instance group
gcloud compute instance-groups managed create options-greeks-ig \
  --size 2 \
  --template options-greeks-instance-template

# Create auto-scaler
gcloud compute autoscalers create options-greeks-scaler \
  --target=options-greeks-ig \
  --min-num-replicas=2 \
  --max-num-replicas=10 \
  --target-cpu-utilization=0.7 \
  --zone=us-central1-a
```

---

## Database Setup (Cloud SQL)

```bash
# Create Cloud SQL instance
gcloud sql instances create options-greeks-db \
  --database-version=POSTGRES_14 \
  --tier=db-g1-small \
  --region=us-central1 \
  --backup-start-time=03:00

# Create database
gcloud sql databases create greeks_app --instance=options-greeks-db

# Create user
gcloud sql users create app_user \
  --instance=options-greeks-db \
  --password=secure-password

# Get connection string
gcloud sql instances describe options-greeks-db \
  --format='value(connectionName)'
```

---

## Monitoring & Logging

### View Real-time Metrics

```bash
# CPU utilization
gcloud monitoring time-series list \
  --filter='metric.type=run.googleapis.com/request_count'

# Error rate
gcloud logging read "severity=ERROR" \
  --limit 20 \
  --format=json
```

### Setup Error Reporting

```bash
# Enable Error Reporting API
gcloud services enable errorreporting.googleapis.com

# View errors
gcloud error-reporting list
```

---

## Maintenance & Updates

### Update Application

```bash
# Rebuild and push new image
docker build -f backend/Dockerfile -t gcr.io/$PROJECT_ID/options-greeks-api:latest ./backend
docker push gcr.io/$PROJECT_ID/options-greeks-api:latest

# Deploy new version
gcloud run deploy options-greeks-api \
  --image gcr.io/$PROJECT_ID/options-greeks-api:latest \
  --region us-central1
```

### View Deployment History

```bash
# List revisions
gcloud run revisions list --service options-greeks-api

# Traffic distribution
gcloud run services describe options-greeks-api --region us-central1
```

---

## Cost Optimization

### Estimated Monthly Costs
- Cloud Run (128MB per 100 requests): ~$1-5/month
- Compute Engine (e2-small): ~$13/month
- Cloud SQL (db-g1-small): ~$10/month
- Load Balancer: ~$20/month
- **Total**: ~$45-50/month

### Cost Reduction Tips
1. Use Cloud Run over VMs (pay only for actual usage)
2. Use Cloud SQL for database only if needed
3. Set resource limits appropriately
4. Use regional services instead of multi-regional
5. Monitor and cleanup unused resources

---

## Troubleshooting

### Cloud Run not responding

```bash
# View Cloud Run logs
gcloud run services describe options-greeks-api --region us-central1

# Check service status
gcloud run services list --region us-central1

# View container logs
gcloud run logs read options-greeks-api --region us-central1 --limit=100
```

### High latency

```bash
# Check metrics
gcloud monitoring time-series list \
  --filter='metric.type=run.googleapis.com/execution_times'

# Check resource utilization
gcloud run services describe options-greeks-api \
  --region us-central1 \
  --format='value(status.conditions)'
```

---

## Rollback to Previous Version

```bash
# List available revisions
gcloud run revisions list --service options-greeks-api --region us-central1

# Set traffic to previous revision
gcloud run services update-traffic options-greeks-api \
  --to-revisions=REVISION_NAME=100 \
  --region us-central1
```

---

## References
- Cloud Run Documentation: https://cloud.google.com/run/docs
- Compute Engine: https://cloud.google.com/compute/docs
- App Engine: https://cloud.google.com/appengine/docs
- Cloud SQL: https://cloud.google.com/sql/docs
- gcloud CLI: https://cloud.google.com/sdk/docs/cheatsheet
