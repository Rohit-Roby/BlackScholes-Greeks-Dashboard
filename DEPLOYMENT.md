# Deployment Guide

## Local Deployment

### Prerequisites
- Python 3.9+
- Node.js (optional, for http-server)
- Git

### Step-by-Step Setup

1. **Clone Repository**
```bash
git clone <repository-url>
cd options_greeks_calculator
```

2. **Run Setup Script**

**Windows:**
```bash
setup.bat
```

**Linux/macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

3. **Start Backend**
```bash
cd backend
venv\Scripts\activate  # On Linux: source venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

4. **Start Frontend** (in another terminal)
```bash
cd frontend
python -m http.server 8080
```

5. **Access Application**
- Open browser to `http://localhost:8080`
- Backend API is available at `http://localhost:8000/api`

---

## Docker Deployment

### Prerequisites
- Docker
- Docker Compose

### Quick Start

1. **Build and Run**
```bash
docker-compose up -d
```

2. **Access Application**
- Frontend: `http://localhost`
- Backend API: `http://localhost/api`

3. **View Logs**
```bash
docker-compose logs -f backend
docker-compose logs -f frontend
```

4. **Stop Services**
```bash
docker-compose down
```

---

## Cloud Deployment

### Heroku Deployment

1. **Create Heroku App**
```bash
heroku login
heroku create your-app-name
```

2. **Deploy Backend**
```bash
cd backend
git push heroku main
```

3. **Deploy Frontend**
```bash
cd frontend
# Configure for production API URL
heroku config:set VITE_API_URL=https://your-app-name.herokuapp.com/api
```

### AWS Deployment (using Elastic Beanstalk)

1. **Install AWS EB CLI**
```bash
pip install awsebcli
```

2. **Initialize EB**
```bash
eb init -p python-3.11 options-greeks-calc
```

3. **Create Environment**
```bash
eb create production
```

4. **Deploy**
```bash
eb deploy
```

### Google Cloud Deployment

1. **Install Google Cloud SDK**
```bash
# https://cloud.google.com/sdk/docs/install
```

2. **Deploy with Cloud Run**
```bash
gcloud run deploy options-greeks-calculator \
  --source . \
  --platform managed \
  --region us-central1
```

---

## Production Configuration

### Environment Variables
Create `.env` file in root:
```bash
cp .env.example .env
```

Edit `.env` with production settings:
```env
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARNING
CORS_ORIGINS=https://yourdomain.com
```

### Security Checklist

- [ ] Set DEBUG=false
- [ ] Use strong SECRET_KEY
- [ ] Enable HTTPS/TLS
- [ ] Configure CORS properly
- [ ] Use environment variables for secrets
- [ ] Set appropriate CORS_ORIGINS
- [ ] Enable rate limiting
- [ ] Set up monitoring and logging
- [ ] Regular backups configured
- [ ] Security headers enabled

### Performance Optimization

1. **Caching**
   - Enable Redis for caching market data
   - Cache Greeks calculations

2. **Database** (if using)
   - Use connection pooling
   - Index frequently queried fields
   - Regular maintenance

3. **Frontend**
   - Minify CSS/JS
   - Compress images
   - Enable gzip compression
   - Use CDN for static files

4. **Backend**
   - Use gunicorn with multiple workers
   - Enable connection pooling
   - Monitor performance metrics

---

## Monitoring & Logging

### Backend Logs
Located in `backend/logs/app.log`

```bash
# View logs
tail -f backend/logs/app.log

# Search logs
grep "ERROR" backend/logs/app.log
```

### Docker Logs
```bash
docker-compose logs -f --tail=100 backend
```

### Application Monitoring
- Set up monitoring with DataDog, New Relic, or similar
- Configure alerts for errors and performance issues
- Track API response times and error rates

---

## Scaling & High Availability

### Horizontal Scaling
1. **Multiple Backend Instances**
   - Use load balancer (nginx, HAProxy, AWS ELB)
   - Scale based on CPU/memory usage

2. **Caching Layer**
   - Deploy Redis for market data caching
   - Cache Greeks calculations

3. **Database**
   - Use managed databases (AWS RDS, Google Cloud SQL)
   - Enable replication and backups

### Load Balancer Configuration (nginx)
```nginx
upstream backend {
    server backend1:8000;
    server backend2:8000;
    server backend3:8000;
}

server {
    listen 80;
    location /api {
        proxy_pass http://backend;
    }
}
```

---

## Troubleshooting

### Backend Won't Start
```bash
# Check port is available
lsof -i :8000  # On Linux/macOS
netstat -ano | findstr :8000  # On Windows

# Check dependencies
pip install -r requirements.txt

# Run with verbose logging
python -m uvicorn app:app --log-level debug
```

### Frontend Connection Issues
- Check backend is running on port 8000
- Verify CORS is enabled
- Check browser console for errors
- Ensure API_URL is correct

### Market Data Errors
- Check internet connection
- Verify Yahoo Finance is accessible
- Check API rate limits
- Use fallback mock data if needed

---

## Backup & Recovery

### Database Backup
```bash
# SQLite (if using)
cp database.db backup_$(date +%s).db

# Regular automated backups
# Add to cron job (Linux) or Task Scheduler (Windows)
```

### Configuration Backup
```bash
# Backup .env and settings
tar -czf backup_config.tar.gz .env *.conf
```

### Recovery Procedure
1. Restore database from backup
2. Restore configuration files
3. Verify application health
4. Run migrations if needed
5. Restart services

---

## Maintenance

### Regular Tasks
- [ ] Monitor disk space and cleanup logs
- [ ] Review and update dependencies monthly
- [ ] Check for security updates
- [ ] Monitor API usage and performance
- [ ] Backup databases and configuration

### Dependencies Update
```bash
# Check for updates
pip list --outdated

# Update all packages
pip install --upgrade -r requirements.txt

# Run tests after updating
pytest tests/ -v
```

### Database Maintenance
```bash
# For SQLite
sqlite3 greeks_calculator.db "VACUUM;"
sqlite3 greeks_calculator.db "ANALYZE;"
```

---

## Rollback Procedure

1. **Identify Issue**
   - Check logs and monitoring alerts
   - Determine affected version

2. **Stop Current Version**
   ```bash
   docker-compose stop backend
   ```

3. **Restore Previous Version**
   ```bash
   git checkout previous-tag
   docker-compose up -d backend
   ```

4. **Verify Health**
   ```bash
   curl http://localhost:8000/api/health
   ```

5. **Post-Incident Review**
   - Document what happened
   - Implement preventive measures
   - Update runbooks

---

## Support & Contact

For deployment issues:
- Check logs in `backend/logs/`
- Review this guide
- Create issue on GitHub
- Contact development team
