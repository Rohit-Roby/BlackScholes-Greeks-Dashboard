# Azure Deployment Guide

## Quick Azure Deployment

### Prerequisites
- Azure CLI installed: `az login`
- Azure subscription active
- Docker installed (for building images)

---

## Option 1: App Service + Container Registry (Recommended)

### Step 1: Create Resource Group

```bash
az group create \
  --name options-greeks-rg \
  --location eastus
```

### Step 2: Create Container Registry

```bash
az acr create \
  --resource-group options-greeks-rg \
  --name greekscontainer \
  --sku Basic
```

### Step 3: Build & Push Images

```bash
# Get login credentials
az acr login --name greekscontainer

# Build backend
docker build -f backend/Dockerfile \
  -t greekscontainer.azurecr.io/options-greeks-api:latest ./backend

# Push
docker push greekscontainer.azurecr.io/options-greeks-api:latest

# Build frontend (if custom image needed)
docker build -f frontend/Dockerfile \
  -t greekscontainer.azurecr.io/options-greeks-frontend:latest ./frontend

# Push
docker push greekscontainer.azurecr.io/options-greeks-frontend:latest
```

### Step 4: Create App Service Plan

```bash
az appservice plan create \
  --name options-greeks-plan \
  --resource-group options-greeks-rg \
  --sku B1 \
  --is-linux
```

### Step 5: Deploy Web App

```bash
az webapp create \
  --resource-group options-greeks-rg \
  --plan options-greeks-plan \
  --name options-greeks-app \
  --deployment-container-image-name greekscontainer.azurecr.io/options-greeks-api:latest
```

### Step 6: Configure Deployment

```bash
# Get registry credentials
REGISTRY_USERNAME=$(az acr credential show \
  --name greekscontainer \
  --query username -o tsv)

REGISTRY_PASSWORD=$(az acr credential show \
  --name greekscontainer \
  --query passwords[0].value -o tsv)

# Set environment variables
az webapp config appsettings set \
  --resource-group options-greeks-rg \
  --name options-greeks-app \
  --settings \
    WEBSITES_ENABLE_APP_SERVICE_STORAGE=false \
    DOCKER_REGISTRY_SERVER_URL=https://greekscontainer.azurecr.io \
    DOCKER_REGISTRY_SERVER_USERNAME=$REGISTRY_USERNAME \
    DOCKER_REGISTRY_SERVER_PASSWORD=$REGISTRY_PASSWORD \
    ENVIRONMENT=production \
    DEBUG=false \
    LOG_LEVEL=WARNING
```

### Step 7: Deploy Nginx Frontend

For frontend, you can use:
- Static Web Apps (easiest)
- Another App Service
- Azure CDN + Storage

```bash
# Using Static Web Apps
az staticwebapp create \
  --name options-greeks-frontend \
  --resource-group options-greeks-rg \
  --source ./frontend \
  --location eastus \
  --branch main
```

---

## Option 2: Container Instances (Simplest)

### Quick Deploy

```bash
# Deploy backend
az container create \
  --resource-group options-greeks-rg \
  --name greeks-api \
  --image greekscontainer.azurecr.io/options-greeks-api:latest \
  --cpu 1 \
  --memory 0.5 \
  --ports 8000 \
  --environment-variables \
    ENVIRONMENT=production \
    DEBUG=false \
  --registry-login-server greekscontainer.azurecr.io \
  --registry-username $REGISTRY_USERNAME \
  --registry-password $REGISTRY_PASSWORD

# Get public IP
az container show \
  --resource-group options-greeks-rg \
  --name greeks-api \
  --query ipAddress.ip
```

---

## Option 3: Azure Kubernetes Service (AKS) - Advanced

```bash
# Create AKS cluster
az aks create \
  --resource-group options-greeks-rg \
  --name options-greeks-aks \
  --node-count 2 \
  --vm-set-type VirtualMachineScaleSets

# Get credentials
az aks get-credentials \
  --resource-group options-greeks-rg \
  --name options-greeks-aks

# Deploy using Kubernetes manifests
kubectl apply -f deployment.yaml
```

---

## Setup Custom Domain

```bash
# Create DNS record in your domain registrar pointing to:
# App Service IP or Load Balancer IP

# Or use Azure DNS
az network dns zone create \
  --resource-group options-greeks-rg \
  --name yourdomain.com

az network dns record-set a create \
  --resource-group options-greeks-rg \
  --zone-name yourdomain.com \
  --name @ \
  --ttl 3600

az network dns record-set a add-record \
  --resource-group options-greeks-rg \
  --zone-name yourdomain.com \
  --record-set-name @ \
  --ipv4-address YOUR_APP_IP
```

---

## Setup SSL/TLS

```bash
# Use App Service Certificate
az appservice certificate create \
  --resource-group options-greeks-rg \
  --name options-greeks-cert \
  --host-name yourdomain.com

# Or import existing certificate
az appservice certificate import \
  --resource-group options-greeks-rg \
  --name options-greeks-cert \
  --certificate-file cert.pfx \
  --certificate-password password
```

---

## Monitoring & Insights

```bash
# Enable Application Insights
az monitor app-insights component create \
  --app options-greeks-insights \
  --location eastus \
  --resource-group options-greeks-rg

# View logs
az monitor app-insights query \
  --app options-greeks-insights \
  --analytics-query "requests | count"
```

---

## Scaling

```bash
# Scale App Service
az appservice plan update \
  --name options-greeks-plan \
  --resource-group options-greeks-rg \
  --sku P1V2

# Auto-scale
az monitor autoscale create \
  --resource-group options-greeks-rg \
  --resource options-greeks-plan \
  --resource-type "Microsoft.Web/serverfarms" \
  --name options-greeks-autoscale \
  --min-count 2 \
  --max-count 10 \
  --count 2
```

---

## Cost Estimation

- **App Service B1**: ~$18/month
- **Container Registry**: ~$5/month
- **Static Web Apps**: Free for basic
- **Application Insights**: ~$2-5/month
- **Total**: ~$25-30/month

---

## Useful Commands

```bash
# List resources
az resource list --resource-group options-greeks-rg

# View app configuration
az webapp config show \
  --resource-group options-greeks-rg \
  --name options-greeks-app

# Stream logs
az webapp log tail \
  --resource-group options-greeks-rg \
  --name options-greeks-app

# Restart app
az webapp restart \
  --resource-group options-greeks-rg \
  --name options-greeks-app

# Delete everything
az group delete --name options-greeks-rg --yes
```

---

## Troubleshooting

```bash
# Check container logs
az container logs \
  --resource-group options-greeks-rg \
  --name greeks-api

# Check app service logs
az webapp log download \
  --resource-group options-greeks-rg \
  --name options-greeks-app \
  --log-file logs.zip

# Test endpoint
curl https://options-greeks-app.azurewebsites.net/api/health
```

---

## References
- Azure App Service: https://docs.microsoft.com/azure/app-service/
- Container Registry: https://docs.microsoft.com/azure/container-registry/
- Container Instances: https://docs.microsoft.com/azure/container-instances/
- AKS: https://docs.microsoft.com/azure/aks/
- Azure CLI: https://docs.microsoft.com/cli/azure/
