# Complete Production Deployment Checklist

## Pre-Deployment Verification

### 1. Code Quality & Testing

- [ ] Backend unit tests passing: `pytest tests/ -v`
- [ ] API endpoints responding correctly
- [ ] Frontend loads without console errors
- [ ] No hardcoded credentials in code
- [ ] No debug statements in production code
- [ ] All imports resolve correctly

### 2. Environment Configuration

- [ ] `.env` file created from `.env.example`
- [ ] `ENVIRONMENT=production`
- [ ] `DEBUG=false`
- [ ] `LOG_LEVEL=WARNING`
- [ ] `SECRET_KEY` is generated and secure
- [ ] `CORS_ORIGINS` set to your domain(s)
- [ ] All required variables present

### 3. Docker Configuration

- [ ] `Dockerfile` in backend directory
- [ ] `docker-compose.prod.yml` exists
- [ ] All volumes properly defined
- [ ] Health checks configured
- [ ] Resource limits set appropriately
- [ ] Logging configuration present

### 4. Security

- [ ] HTTPS/SSL certificate ready (or will be installed after)
- [ ] Security headers configured in nginx
- [ ] Rate limiting enabled
- [ ] CORS properly configured (not wildcard)
- [ ] No secrets in docker-compose.yml
- [ ] Non-root user in Docker (appuser)
- [ ] API requires authentication if needed

### 5. Monitoring & Logging

- [ ] Structured JSON logging configured
- [ ] Log rotation configured
- [ ] Health check endpoint working
- [ ] Monitoring tools prepared (optional)
- [ ] Alerting rules created (optional)
- [ ] Log storage plan in place

---

## Platform-Specific Deployment

### AWS Deployment

**Option A: EC2 (Traditional)**
- [ ] EC2 instance launched (t3.small minimum)
- [ ] Security groups configured (80, 443, 22)
- [ ] Elastic IP assigned
- [ ] Docker and Docker Compose installed
- [ ] Repository cloned to /home/ubuntu/options_greeks_calculator
- [ ] .env file configured
- [ ] Services running: `docker-compose -f docker-compose.prod.yml up -d`
- [ ] Health check passing
- [ ] Domain pointed to Elastic IP
- [ ] SSL/TLS configured

**Option B: Elastic Beanstalk**
- [ ] AWS account with EB CLI configured
- [ ] `app.yaml` created
- [ ] `eb init` completed
- [ ] Environment created: `eb create production`
- [ ] Environment variables set: `eb setenv`
- [ ] Deployment successful: `eb deploy`
- [ ] Health status: `eb status`

**Option C: ECS**
- [ ] ECR repositories created for backend and frontend
- [ ] Docker images built and pushed to ECR
- [ ] ECS cluster created
- [ ] Task definition registered
- [ ] Service created with load balancer
- [ ] Desired count: 2+ instances

### Google Cloud Deployment

**Option A: Cloud Run (Recommended)**
- [ ] GCP project created and configured
- [ ] gcloud CLI authenticated: `gcloud auth login`
- [ ] Docker image built: `docker build -t options-greeks-api:latest ./backend`
- [ ] Image pushed to Container Registry
- [ ] Cloud Run service deployed: `gcloud run deploy`
- [ ] Service URL obtained
- [ ] Health check passing
- [ ] Custom domain mapped (optional)
- [ ] Secrets configured via Secret Manager

**Option B: Compute Engine**
- [ ] VM instance created (e2-small minimum)
- [ ] SSH keys configured
- [ ] Connected via SSH and Docker installed
- [ ] Docker images built and started
- [ ] Firewall rules configured
- [ ] Health check passing

### Azure Deployment

- [ ] Resource group created
- [ ] Container registry created
- [ ] App Service plan created
- [ ] App Service created
- [ ] Container image deployed
- [ ] Application settings configured
- [ ] Custom domain configured
- [ ] SSL/TLS certificate installed

### Heroku Deployment

- [ ] Heroku account created
- [ ] Heroku CLI installed and authenticated
- [ ] App created: `heroku create app-name`
- [ ] Procfile configured (if needed)
- [ ] Environment variables set: `heroku config:set`
- [ ] Deployment successful: `git push heroku main`
- [ ] Health check: `heroku logs --tail`

### DigitalOcean Deployment

- [ ] DigitalOcean account created
- [ ] App created or Droplet launched
- [ ] DNS configured
- [ ] Docker and Docker Compose installed
- [ ] Application deployed
- [ ] Health check passing
- [ ] Backups configured

---

## Post-Deployment Verification

### 1. Health Checks

```bash
# API Health
curl https://yourdomain.com/api/health

# Expected response:
{
  "status": "healthy",
  "service": "Options Greeks Calculator API",
  "version": "1.0.0",
  "environment": "production"
}
```

- [ ] HTTP 200 response
- [ ] Response time < 500ms
- [ ] Environment shows "production"

### 2. API Functionality

```bash
# Test Calculate Greeks
curl -X POST https://yourdomain.com/api/calculate-greeks \
  -H "Content-Type: application/json" \
  -d '{
    "spot_price": 100.0,
    "strike_price": 100.0,
    "days_to_expiration": 30,
    "interest_rate": 5,
    "implied_volatility": 25
  }'
```

- [ ] HTTP 200 response
- [ ] Greeks calculated correctly
- [ ] Response time < 1000ms

### 3. Frontend Access

- [ ] Frontend loads at https://yourdomain.com
- [ ] No console errors
- [ ] Dark/light mode toggle works
- [ ] Market data fetch works
- [ ] Greeks calculation works
- [ ] Charts display correctly

### 4. Security Headers

```bash
curl -I https://yourdomain.com

# Check for headers:
# X-Frame-Options: DENY
# X-Content-Type-Options: nosniff
# X-XSS-Protection: 1; mode=block
# Strict-Transport-Security: max-age=...
# Content-Security-Policy: ...
```

- [ ] X-Frame-Options present
- [ ] X-Content-Type-Options present
- [ ] HSTS header present (HTTPS)
- [ ] CSP header present

### 5. SSL/TLS

```bash
# Check certificate
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com

# Verify:
# Certificate subject matches domain
# Valid dates
# Chain complete
```

- [ ] Certificate valid
- [ ] No mixed content warnings
- [ ] HTTPS enforced
- [ ] Grade A at SSL Labs (optional: https://www.ssllabs.com)

### 6. Performance

- [ ] Time to First Byte (TTFB) < 500ms
- [ ] Page load time < 3s
- [ ] API response time < 1s
- [ ] Charts render smoothly
- [ ] No timeout errors

### 7. Monitoring

- [ ] Logs being written
- [ ] Error logs monitored
- [ ] Alerts configured (if applicable)
- [ ] Metrics being collected (if applicable)
- [ ] Dashboard accessible (if applicable)

---

## Operational Tasks (Post-Deployment)

### Daily

- [ ] Check health endpoint
- [ ] Review error logs
- [ ] Monitor disk space

### Weekly

- [ ] Backup database
- [ ] Review performance metrics
- [ ] Check certificate expiration (SSL)

### Monthly

- [ ] Security scanning
- [ ] Dependency updates
- [ ] Cost review
- [ ] Capacity planning

### Quarterly

- [ ] Major updates
- [ ] Security audit
- [ ] Disaster recovery drill

---

## Rollback Plan

If deployment fails or issues arise:

```bash
# Docker Compose rollback
docker-compose -f docker-compose.prod.yml down
git checkout previous-tag
docker-compose -f docker-compose.prod.yml up -d

# AWS EC2 rollback
ssh -i key.pem ubuntu@instance
cd options_greeks_calculator
git checkout previous-tag
docker-compose -f docker-compose.prod.yml up -d --build

# Elastic Beanstalk rollback
eb abort

# Cloud Run rollback
gcloud run services update-traffic options-greeks-api \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region us-central1
```

---

## Support Resources

### Documentation

- **Main README**: [README.md](README.md)
- **AWS Deployment**: [aws.md](aws.md)
- **GCP Deployment**: [gcp.md](gcp.md)
- **Operations**: [operations.md](../operations.md)
- **Production Guide**: [production.md](production.md)

### Validation

- **Linux/macOS**: `./validate-deployment.sh`
- **Windows**: `validate-deployment.bat`

### Troubleshooting

```bash
# View logs
docker logs -f greeks-calculator-backend-prod

# Check status
docker ps
docker ps -a

# Check health
curl http://localhost/api/health

# Restart service
docker-compose -f docker-compose.prod.yml restart backend
```

### External Resources

- Docker Docs: https://docs.docker.com/
- AWS Documentation: https://docs.aws.amazon.com/
- GCP Documentation: https://cloud.google.com/docs
- Azure Documentation: https://docs.microsoft.com/azure
- FastAPI Docs: https://fastapi.tiangolo.com/
- Nginx Docs: https://nginx.org/en/docs/

---

## Final Verification Checklist

Before going live, verify:

- [ ] All environment variables set
- [ ] Health check passing
- [ ] API endpoints responding
- [ ] Frontend loads
- [ ] Security headers present
- [ ] HTTPS/SSL working
- [ ] Logging working
- [ ] Monitoring in place
- [ ] Backups configured
- [ ] Team trained on operations
- [ ] Documentation complete
- [ ] Support contacts updated

---

## Sign-Off

- **Deployed by**: ________________
- **Date**: ________________
- **Environment**: Production
- **Version**: 1.0.0
- **Status**: ✓ Ready for Production

---

## Contact & Support

For issues:
1. Check documentation in [operations.md](../operations.md)
2. Review application logs
3. Check platform-specific documentation
4. Contact development team

**API Support**: support@example.com
**Infrastructure**: ops@example.com
