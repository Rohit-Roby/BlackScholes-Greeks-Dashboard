# Production Deployment Guide

## Quick Start (All Platforms)

The Options Greeks Calculator is production-ready and can be deployed to any major cloud platform or on-premises.

---

## 1. Local Development Setup

```bash
# Clone repository
git clone https://github.com/your-repo/options_greeks_calculator.git
cd options_greeks_calculator

# Setup environment
cp .env.example .env

# Start with Docker Compose
docker-compose up -d

# Validate deployment
./validate-deployment.sh
```

**Access:**
- Frontend: http://localhost
- API: http://localhost/api
- API Docs: http://localhost:8000/docs (dev only)

---

## 2. Production Docker Deployment

### Using Production Compose File

```bash
# Setup .env for production
cp .env.example .env
nano .env  # Set ENVIRONMENT=production, DEBUG=false, etc.

# Start production stack
docker-compose -f docker-compose.prod.yml up -d

# Monitor health
docker-compose -f docker-compose.prod.yml logs -f backend

# Validate
./validate-deployment.sh http://localhost
```

### Manual Docker Commands

```bash
# Build backend
docker build -f backend/Dockerfile -t greeks-api:latest ./backend

# Build frontend (if needed)
docker build -f frontend/Dockerfile -t greeks-frontend:latest ./frontend

# Run with environment
docker run -d \
  -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e DEBUG=false \
  --restart always \
  greeks-api:latest
```

---

## 3. Cloud Deployment Options

### AWS
See [DEPLOYMENT-AWS.md](DEPLOYMENT-AWS.md) for:
- EC2 deployment
- ECS deployment
- Elastic Beanstalk deployment

```bash
# Quick Elastic Beanstalk deploy
eb create production
eb deploy
```

### Google Cloud Platform
See [DEPLOYMENT-GCP.md](DEPLOYMENT-GCP.md) for:
- Cloud Run deployment (recommended - simplest)
- Compute Engine deployment
- App Engine deployment

```bash
# Quick Cloud Run deploy
gcloud run deploy options-greeks-api \
  --image gcr.io/$PROJECT_ID/options-greeks-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### Azure
```bash
# Create resource group
az group create --name greeks-rg --location eastus

# Create App Service
az appservice plan create --name greeks-plan --resource-group greeks-rg --sku B1 --is-linux

# Deploy container
az webapp create --resource-group greeks-rg --plan greeks-plan --name greeks-app \
  --deployment-container-image-name greeks-api:latest
```

### Heroku
```bash
# Login
heroku login

# Create app
heroku create your-app-name

# Deploy
git push heroku main

# View logs
heroku logs --tail
```

### DigitalOcean
```bash
# Create App
doctl apps create --spec app.yaml

# Or use Droplet
doctl compute droplet create --image ubuntu-22-04-x64 \
  --size s-1vcpu-1gb --region nyc3 greeks-app
```

---

## 4. Environment Configuration

### Essential Variables

```env
# Deployment
ENVIRONMENT=production    # production or development
DEBUG=false              # Never true in production
LOG_LEVEL=WARNING        # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json          # json for structured logging

# Server
HOST=0.0.0.0
PORT=8000

# Security
CORS_ORIGINS=https://yourdomain.com  # Your domain(s)
SECRET_KEY=<generate-securely>       # Use: python -c "import secrets; print(secrets.token_urlsafe(32))"
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_PERIOD=60

# Market Data
MARKET_DATA_TIMEOUT=30
MARKET_DATA_CACHE_ENABLED=true
MARKET_DATA_CACHE_TTL=300
```

### Generate Secure Secret Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Output: xK9mP2...pL_q8w
```

Copy this and set it in `.env` as `SECRET_KEY`

---

## 5. SSL/TLS Configuration

### Using Let's Encrypt (Linux)

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --standalone -d yourdomain.com

# Configure nginx
# Update docker-compose to mount certs:
volumes:
  - /etc/letsencrypt/live/yourdomain.com:/etc/nginx/certs:ro

# Enable auto-renewal
sudo systemctl enable certbot.timer
```

### Using Cloud Provider SSL

- **AWS**: Use ACM (AWS Certificate Manager)
- **GCP**: Use Google-managed certificates
- **Azure**: Use App Service Certificates
- **Heroku**: Automatic HTTPS

---

## 6. Health Checks & Monitoring

### Health Check Endpoint

```bash
# Check application health
curl http://localhost:8000/api/health

# Response:
{
  "status": "healthy",
  "service": "Options Greeks Calculator API",
  "version": "1.0.0",
  "environment": "production"
}
```

### Docker Health

```bash
# Check container status
docker ps --format "table {{.Names}}\t{{.Status}}"

# View detailed health
docker inspect --format='{{json .State.Health}}' greeks-calculator-backend-prod | jq
```

### Validation Script

```bash
# Linux/macOS
./validate-deployment.sh http://yourdomain.com

# Windows
validate-deployment.bat
```

---

## 7. Scaling & Performance

### Horizontal Scaling

```bash
# Scale with Docker Compose
docker-compose up -d --scale backend=3

# With load balancer (nginx)
upstream backend {
    server backend1:8000;
    server backend2:8000;
    server backend3:8000;
}
```

### Resource Limits

```yaml
# docker-compose.prod.yml
backend:
  deploy:
    resources:
      limits:
        cpus: '1'
        memory: 512M
```

### Performance Tuning

```python
# Uvicorn workers (in Dockerfile)
CMD ["python", "-m", "uvicorn", "app:app", "--workers", "4"]
```

---

## 8. Logging & Monitoring

### View Logs

```bash
# Docker logs
docker logs -f greeks-calculator-backend-prod

# Nginx logs
docker logs -f greeks-calculator-frontend-prod

# File logs (if mounted)
tail -f backend/logs/app.log
```

### Structured Logging

With `LOG_FORMAT=json`, logs are JSON for easy parsing:

```bash
# Parse logs
cat backend/logs/app.log | jq 'select(.level=="ERROR")'

# Count errors
cat backend/logs/app.log | jq 'select(.level=="ERROR")' | wc -l
```

### Monitoring Tools Integration

#### Datadog
```python
# Add to app.py
from datadog import initialize, statsd
initialize(api_key="YOUR_API_KEY")
statsd.gauge('greeks.api.requests', 1)
```

#### Prometheus
```yaml
# Expose metrics endpoint
GET /metrics
```

---

## 9. Backup & Recovery

### Database Backup

```bash
# SQLite
docker exec greeks-calculator-backend-prod \
  cp greeks_calculator.db /backups/backup_$(date +%Y%m%d).db

# PostgreSQL
pg_dump -U username database_name > backup.sql
```

### Automated Backup

```bash
# Add to cron (Linux)
0 2 * * * docker exec greeks-calculator-backend-prod \
  bash -c "cp greeks_calculator.db /backups/backup_$(date +\%Y\%m\%d).db"
```

### Recovery

```bash
# Stop services
docker-compose -f docker-compose.prod.yml down

# Restore backup
docker cp backup_20240115.db greeks-calculator-backend-prod:/app/greeks_calculator.db

# Start services
docker-compose -f docker-compose.prod.yml up -d
```

---

## 10. Security Best Practices

✅ **Implemented:**
- Non-root Docker user
- Security headers (X-Frame-Options, CSP, etc.)
- Rate limiting (100 req/min default)
- Input validation
- CORS restrictions
- HTTPS support

✅ **Recommended:**
- Use secret manager for keys (AWS Secrets Manager, GCP Secret Manager)
- Enable WAF (Web Application Firewall)
- Regular security patches
- Monitoring and alerting
- Regular backups
- Audit logging

### Secret Management

```bash
# AWS Secrets Manager
aws secretsmanager create-secret --name greeks-secret-key --secret-string "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

# GCP Secret Manager
echo -n "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" | \
  gcloud secrets create greeks-secret-key --data-file=-
```

---

## 11. Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs greeks-calculator-backend-prod

# Check environment
docker inspect greeks-calculator-backend-prod | jq '.[0].Config.Env'

# Verify image
docker images | grep greeks
```

### High Memory Usage

```bash
# Check container stats
docker stats greeks-calculator-backend-prod

# Restart if needed
docker-compose restart backend

# Increase resource limit in docker-compose.yml
```

### API Not Responding

```bash
# Check health
curl http://localhost:8000/api/health

# Check nginx logs
docker logs greeks-calculator-frontend-prod

# Verify backend is running
docker ps | grep backend
```

---

## 12. Updates & Maintenance

### Updating Application

```bash
# Pull latest code
git pull origin main

# Rebuild images
docker-compose -f docker-compose.prod.yml build --no-cache

# Deploy with zero downtime (if multiple replicas)
docker-compose -f docker-compose.prod.yml up -d

# Verify
./validate-deployment.sh
```

### Updating Dependencies

```bash
# Update Python dependencies
pip install --upgrade -r backend/requirements.txt

# Update base Docker image
docker pull python:3.11-slim

# Rebuild
docker build -f backend/Dockerfile -t greeks-api:latest ./backend
```

---

## 13. Cost Optimization

### Estimated Monthly Costs

| Platform | Min Config | Cost |
|----------|-----------|------|
| EC2 (t3.small) | 1 instance | ~$15 |
| Cloud Run | Serverless | ~$1-5 |
| Elastic Beanstalk | Single instance | ~$20 |
| Heroku | 1 Dyno | ~$7 |
| DigitalOcean | $5/month | ~$5 |

### Cost Reduction Tips

1. **Use spot/preemptible instances** (-70% cost)
2. **Consolidate services** on single instance
3. **Use serverless** (Cloud Run, Lambda)
4. **Cache aggressively** to reduce API calls
5. **Monitor and cleanup** unused resources

---

## 14. Support & Documentation

- **Deployment**: See DEPLOYMENT-AWS.md, DEPLOYMENT-GCP.md
- **Operations**: See OPERATIONS.md
- **Development**: See README.md
- **API Docs**: http://yourdomain.com:8000/docs (dev mode)

---

## Quick Reference

```bash
# Start production
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose -f docker-compose.prod.yml down

# Restart backend
docker-compose -f docker-compose.prod.yml restart backend

# Validate deployment
./validate-deployment.sh

# SSH into container
docker exec -it greeks-calculator-backend-prod bash

# Check health
curl http://localhost/api/health | jq
```

---

## Checklist Before Production

- [ ] .env configured for production
- [ ] ENVIRONMENT=production
- [ ] DEBUG=false
- [ ] SECRET_KEY set securely
- [ ] CORS_ORIGINS set to your domain
- [ ] SSL/TLS certificate installed
- [ ] Health check passing
- [ ] Logs monitored
- [ ] Backup configured
- [ ] Monitoring set up
- [ ] Rate limits appropriate
- [ ] Security headers verified

---

**Ready to deploy!** Choose your platform above and follow the specific guide.

For questions, see OPERATIONS.md or check cloud platform documentation.
