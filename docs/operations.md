# Operations & Monitoring Guide

## Overview
Comprehensive guide for operating, monitoring, scaling, and maintaining the Options Greeks Calculator in production.

---

## Table of Contents
1. Health Checks & Monitoring
2. Logging & Observability
3. Performance Optimization
4. Scaling & Load Management
5. Backup & Recovery
6. Security Operations
7. Incident Response
8. Maintenance Tasks

---

## 1. Health Checks & Monitoring

### Health Check Endpoint

The application provides a health check endpoint at `/api/health`:

```bash
# Check application health
curl -s http://localhost:8000/api/health | jq

# Response (healthy):
{
  "status": "healthy",
  "service": "Options Greeks Calculator API",
  "version": "1.0.0",
  "environment": "production"
}
```

### Docker Compose Health Check

```bash
# View container health status
docker ps --format "table {{.Names}}\t{{.Status}}"

# Force health check
docker exec greeks-calculator-backend-prod curl -f http://localhost:8000/api/health

# View health check history
docker inspect --format='{{json .State.Health}}' greeks-calculator-backend-prod | jq
```

### Monitoring Dashboards

#### Prometheus Setup (Optional)

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'greeks-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

#### Datadog Integration

```python
# In app.py, add:
from datadog import initialize, api
from statsd import StatsClient

options = {
    'api_key': os.getenv('DATADOG_API_KEY'),
    'app_key': os.getenv('DATADOG_APP_KEY')
}
initialize(**options)

# Use client for metrics
statsd = StatsClient()
statsd.gauge('greeks.api.requests', 1, tags=['endpoint:calculate'])
```

---

## 2. Logging & Observability

### Log Levels

Set via environment variable: `LOG_LEVEL`

```bash
# DEBUG: Verbose output for development
# INFO: General information and events
# WARNING: Warning messages for non-critical issues
# ERROR: Error messages for failures
# CRITICAL: Critical failures

# Set in .env
LOG_LEVEL=WARNING  # Production default
LOG_FORMAT=json    # Structured logging for tools
```

### Log Files

Logs are stored in `backend/logs/`:

```bash
# View application logs
tail -f backend/logs/app.log

# Search for errors
grep ERROR backend/logs/app.log

# Count errors by type
grep ERROR backend/logs/app.log | cut -d'-' -f4 | sort | uniq -c

# View today's errors
grep "$(date +'%Y-%m-%d')" backend/logs/app.log | grep ERROR

# Archive old logs (keep for 30 days)
find backend/logs -name "*.log" -mtime +30 -delete
```

### Docker Logs

```bash
# View real-time backend logs
docker logs -f greeks-calculator-backend-prod

# View last 100 lines
docker logs --tail 100 greeks-calculator-backend-prod

# View with timestamps
docker logs -t greeks-calculator-backend-prod

# Search in logs
docker logs greeks-calculator-backend-prod | grep "ERROR"

# Save logs to file
docker logs greeks-calculator-backend-prod > container.log 2>&1
```

### Structured Logging (JSON Format)

With `LOG_FORMAT=json`, logs are structured for analysis:

```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "level": "ERROR",
  "logger": "backend.routes.api",
  "message": "Market data fetch error for INVALID",
  "environment": "production",
  "request_id": "req-12345",
  "duration_ms": 1500
}
```

Parse and analyze:

```bash
# Parse JSON logs
jq '.level, .message' backend/logs/app.log | head -20

# Count by log level
jq -s 'group_by(.level) | map({level: .[0].level, count: length})' backend/logs/app.log

# Find slow requests
jq 'select(.duration_ms > 1000)' backend/logs/app.log
```

---

## 3. Performance Optimization

### API Performance Tuning

#### Request/Response Optimization

```python
# In app.py
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Already enabled

# Enable caching headers
from fastapi.responses import JSONResponse
@app.get("/api/market-data/{symbol}")
async def get_market_data(symbol: str):
    response = JSONResponse(content=data)
    response.headers["Cache-Control"] = "public, max-age=300"  # 5 min cache
    return response
```

#### Database Query Optimization (for future)

```python
# Use connection pooling
from sqlalchemy.pool import QueuePool
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True  # Test connections before use
)
```

### Frontend Performance

```bash
# Minify and optimize static assets
npm run build  # If using build tools

# Gzip static files
gzip -k frontend/styles.css
gzip -k frontend/app.js

# Verify compression in nginx
curl -H "Accept-Encoding: gzip" -I http://localhost/styles.css | grep encoding
```

### Database Query Monitoring

```python
# Add query logging
import logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Identify slow queries
from sqlalchemy import event
@event.listens_for(Engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, params, context, executemany):
    print(f"Query: {statement} | Params: {params}")
```

### Load Testing

```bash
# Install load testing tools
pip install locust

# Create locustfile.py
from locust import HttpUser, task, between

class GreeksUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def calculate_greeks(self):
        self.client.post("/api/calculate-greeks", json={
            "spot_price": 100,
            "strike_price": 100,
            "days_to_expiration": 30,
            "interest_rate": 5,
            "implied_volatility": 25
        })
    
    @task
    def market_data(self):
        self.client.get("/api/market-data/AAPL")

# Run load test
locust -f locustfile.py --host=http://localhost:8000
```

---

## 4. Scaling & Load Management

### Horizontal Scaling (Multiple Instances)

#### Docker Compose Scaling

```bash
# Scale backend service to 3 instances
docker-compose up -d --scale backend=3

# Verify
docker ps | grep greeks-backend
```

#### Nginx Load Balancing

```nginx
# In nginx.conf
upstream backend {
    server backend1:8000;
    server backend2:8000;
    server backend3:8000;
    keepalive 32;
}

# Load balancing methods:
# round_robin (default) - cycle through servers
# least_conn - route to server with fewest connections
# ip_hash - consistent routing based on client IP
# random - random selection
# weighted - assign weights (server backend1:8000 weight=5)
```

#### Vertical Scaling (More Resources)

```bash
# Increase container resources
# In docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'        # 2 CPU cores
          memory: 2G       # 2GB RAM
```

### Connection Pooling

```python
# Uvicorn workers (in Dockerfile)
CMD ["uvicorn", "app:app", "--workers", "4"]  # 4 worker processes

# Gunicorn alternative
gunicorn app:app --workers 4 --worker-class uvicorn.workers.UvicornWorker
```

### Rate Limiting Configuration

```python
# In app.py
RATE_LIMITS = {
    "calculate-greeks": "100/minute",
    "greeks-surface": "50/minute",
    "market-data": "30/minute"
}

# Adjust based on monitoring:
# If backend is overloaded, reduce limits
# If users complain, increase limits
```

---

## 5. Backup & Recovery

### Database Backup (Future SQLite/PostgreSQL)

```bash
# SQLite backup
cp backend/greeks_calculator.db backup_$(date +%Y%m%d_%H%M%S).db

# PostgreSQL backup
pg_dump -U username -d database_name > backup.sql

# Automated daily backup (cron job)
0 2 * * * cd /app && cp greeks_calculator.db /backups/backup_$(date +\%Y\%m\%d).db

# S3 backup
aws s3 cp backup.sql s3://my-backups/greeks/backup_$(date +%Y%m%d).sql
```

### Log Backup

```bash
# Compress and archive logs
tar -czf logs_$(date +%Y%m%d).tar.gz backend/logs/

# Upload to S3
aws s3 cp logs_$(date +%Y%m%d).tar.gz s3://my-backups/logs/

# Retention policy - keep 90 days
find /backups -name "logs_*.tar.gz" -mtime +90 -delete
```

### Configuration Backup

```bash
# Backup .env and configs
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
  .env \
  nginx.conf \
  docker-compose.prod.yml

# Store securely
aws s3 cp config_backup_$(date +%Y%m%d).tar.gz s3://my-backups/config/ --sse
```

### Recovery Procedures

```bash
# Restore from backup
# 1. Stop services
docker-compose -f docker-compose.prod.yml down

# 2. Restore database
cp /backups/backup_latest.db backend/greeks_calculator.db

# 3. Restart services
docker-compose -f docker-compose.prod.yml up -d

# 4. Verify health
curl http://localhost/api/health
```

---

## 6. Security Operations

### SSL/TLS Certificate Management

```bash
# Check certificate expiration
openssl x509 -in /etc/nginx/certs/cert.pem -noout -dates

# Renew certificate (Let's Encrypt)
certbot renew

# Setup auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

### Secret Rotation

```bash
# Generate new secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update .env
SECRET_KEY=new-key-here

# Restart services
docker-compose -f docker-compose.prod.yml restart backend
```

### Access Control

```bash
# SSH access - disable root login
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd

# Firewall rules
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Security Scanning

```bash
# Scan for vulnerabilities
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image greeks-calculator-backend:latest

# Check for secrets in code
pip install detect-secrets
detect-secrets scan --baseline .secrets.baseline

# Scan dependencies
pip-audit

# Check SSL/TLS configuration
testssl.sh https://yourdomain.com
```

---

## 7. Incident Response

### Incident Types & Response

#### High API Error Rate

```bash
# 1. Check logs
docker logs -f greeks-calculator-backend-prod | grep ERROR

# 2. Check metrics
curl http://localhost:8000/metrics | grep errors

# 3. Check health
curl http://localhost:8000/api/health

# 4. Restart if needed
docker-compose -f docker-compose.prod.yml restart backend

# 5. Monitor recovery
watch -n 2 'docker exec greeks-calculator-backend-prod curl -s http://localhost:8000/api/health | jq'
```

#### High Memory Usage

```bash
# Check container memory
docker stats greeks-calculator-backend-prod

# Check processes
docker exec greeks-calculator-backend-prod ps aux

# Check for memory leaks in logs
docker logs greeks-calculator-backend-prod | grep -i "memory"

# Restart container
docker-compose -f docker-compose.prod.yml restart backend

# Increase memory limit
# Edit docker-compose.prod.yml and increase memory: 1G to 2G
docker-compose -f docker-compose.prod.yml up -d
```

#### Database Connection Issues

```bash
# Test database connection
docker exec greeks-calculator-backend-prod python -c \
  "import psycopg2; conn = psycopg2.connect(DATABASE_URL); print('OK')"

# Check connection pool
docker logs greeks-calculator-backend-prod | grep "pool"

# Restart database
docker-compose -f docker-compose.prod.yml restart db

# Clear stale connections
psql -c "SELECT pid FROM pg_stat_activity WHERE state = 'idle' FOR 1 hour;" | xargs -I {} psql -c "SELECT pg_terminate_backend({});"
```

### Incident Log

```bash
# Create incident file
cat > incidents/incident_$(date +%Y%m%d_%H%M%S).md << 'EOF'
# Incident Report

**Time**: $(date)
**Service**: Options Greeks API
**Severity**: High

## Issue
[Describe issue]

## Root Cause
[Investigation results]

## Resolution
[Steps taken]

## Timeline
- 10:30 - Alert triggered
- 10:32 - Investigated logs
- 10:35 - Restarted service
- 10:40 - Verified recovery

## Follow-up
[Preventive measures]
EOF
```

---

## 8. Maintenance Tasks

### Daily Tasks

```bash
# Check application health
curl http://localhost:8000/api/health

# Review error logs
grep ERROR backend/logs/app.log | tail -20

# Check disk usage
df -h

# Monitor resource usage
docker stats
```

### Weekly Tasks

```bash
# Backup database
docker exec greeks-calculator-backend-prod \
  python -c "import shutil; shutil.copy('greeks_calculator.db', '/backups/weekly_$(date +%Y%m%d).db')"

# Review and archive logs
tar -czf logs_archive_$(date +%Y%m%d).tar.gz backend/logs/
mv logs_archive_*.tar.gz /backups/

# Check certificate expiration (if SSL)
openssl x509 -in /etc/nginx/certs/cert.pem -noout -dates

# Update OS packages
sudo apt update && sudo apt upgrade -y
```

### Monthly Tasks

```bash
# Security scanning
pip-audit
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image greeks-calculator-backend:latest

# Review access logs
awk '{print $1}' /var/log/nginx/access.log | sort | uniq -c | sort -rn | head -20

# Check for disk space issues
du -sh backend/logs/
du -sh /backups/

# Performance review
# Plot response times and error rates
```

### Quarterly Tasks

```bash
# Major update check
pip list --outdated
docker pull python:3.11-slim

# Database optimization (if applicable)
VACUUM;
ANALYZE;

# Capacity planning
# Review growth trends and estimate needs

# Security audit
# Review firewall rules, SSL config, CORS settings
```

### Annual Tasks

```bash
# License and compliance review
# Cost optimization review
# Architecture assessment
# Disaster recovery drill
# Document updates
```

---

## Alert Setup

### Nginx Health Check

```bash
# Monitor via systemd
sudo systemctl status nginx

# Custom alert script
#!/bin/bash
SERVICE="greeks-calculator-frontend"
while true; do
    if ! docker ps | grep -q $SERVICE; then
        echo "ALERT: $SERVICE is down" | mail -s "Alert" admin@example.com
        docker-compose up -d $SERVICE
    fi
    sleep 60
done
```

### Application Monitoring

```bash
# Setup alerts in your monitoring tool
# Examples for Datadog/New Relic:

# Alert when error rate > 5%
# Alert when response time > 1000ms
# Alert when CPU > 80%
# Alert when memory > 70%
# Alert when health check fails
```

---

## Best Practices Summary

✅ **Monitor regularly** - Daily health checks
✅ **Log effectively** - Structured JSON logs
✅ **Backup often** - Daily backups, tested recovery
✅ **Test scaling** - Verify load balancing works
✅ **Update dependencies** - Monthly security updates
✅ **Document incidents** - Learn from failures
✅ **Automate tasks** - Cron jobs for backups
✅ **Have playbooks** - Document common procedures

---

## Resources

- Monitoring Tools: Prometheus, Grafana, ELK Stack
- APM Services: Datadog, New Relic, Sentry
- Load Testing: Locust, Apache JMeter, k6
- Log Analysis: ELK Stack, Splunk, CloudWatch
