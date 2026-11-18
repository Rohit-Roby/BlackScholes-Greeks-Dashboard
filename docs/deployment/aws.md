# AWS Deployment Guide - Options Greeks Calculator

## Overview
This guide covers deploying the Options Greeks Calculator to AWS using multiple deployment options:
- **EC2**: Traditional VPS deployment
- **ECS**: Container orchestration
- **Elastic Beanstalk**: Managed container platform
- **RDS**: Managed database (for future features)

---

## Prerequisites
- AWS Account with appropriate IAM permissions
- AWS CLI configured locally (`aws configure`)
- Docker installed locally
- Docker Hub account (optional, for image registry)

---

## Option 1: AWS EC2 Deployment

### Step 1: Launch EC2 Instance

```bash
# Using AWS CLI
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.small \
  --key-name your-key-pair \
  --security-groups web-server \
  --count 1 \
  --region us-east-1
```

**Recommended Settings:**
- AMI: Ubuntu 22.04 LTS
- Instance Type: t3.small (1 CPU, 2GB RAM) minimum
- Storage: 20GB gp3 (general purpose)
- Security Group: Allow HTTP (80), HTTPS (443), SSH (22)

### Step 2: Configure Security Group

```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 22 \
  --cidr YOUR_IP/32  # Restrict SSH to your IP
```

### Step 3: Connect and Setup

```bash
# SSH into instance
ssh -i your-key.pem ubuntu@your-instance-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Clone repository
git clone https://github.com/your-repo/options_greeks_calculator.git
cd options_greeks_calculator
```

### Step 4: Setup Environment

```bash
# Create .env file
cp .env.example .env

# Edit .env with production settings
nano .env

# IMPORTANT: Set these for production
# ENVIRONMENT=production
# DEBUG=false
# CORS_ORIGINS=https://yourdomain.com
# SECRET_KEY=<generate-with-'python -c "import secrets; print(secrets.token_urlsafe(32))"'>
```

### Step 5: Deploy with Docker Compose

```bash
# Build and start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Verify health
curl http://localhost/api/health
```

### Step 6: Setup SSL/TLS with Let's Encrypt

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot certonly --standalone -d yourdomain.com

# Update nginx configuration to use SSL
# Uncomment and configure SSL section in nginx.conf
```

---

## Option 2: AWS ECS Deployment (Recommended for Production)

### Step 1: Create ECR Repository

```bash
# Create registry for backend
aws ecr create-repository \
  --repository-name options-greeks-backend \
  --region us-east-1

# Create registry for frontend
aws ecr create-repository \
  --repository-name options-greeks-frontend \
  --region us-east-1
```

### Step 2: Build and Push Docker Images

```bash
# Get ECR login token
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Build and tag backend
docker build -t options-greeks-backend:latest ./backend
docker tag options-greeks-backend:latest \
  <YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/options-greeks-backend:latest

# Push to ECR
docker push <YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/options-greeks-backend:latest

# Repeat for frontend
docker build -t options-greeks-frontend:latest ./frontend
docker tag options-greeks-frontend:latest \
  <YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/options-greeks-frontend:latest
docker push <YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/options-greeks-frontend:latest
```

### Step 3: Create ECS Cluster

```bash
# Create cluster
aws ecs create-cluster \
  --cluster-name options-greeks-prod \
  --region us-east-1

# Create VPC and networking (if needed)
# Or use default VPC
```

### Step 4: Create Task Definition

```bash
# Create task-definition.json
cat > task-definition.json << 'EOF'
{
  "family": "options-greeks-task",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "<YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/options-greeks-backend:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "ENVIRONMENT", "value": "production"},
        {"name": "DEBUG", "value": "false"},
        {"name": "LOG_LEVEL", "value": "WARNING"}
      ],
      "secrets": [
        {
          "name": "SECRET_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:greeks-secret-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/options-greeks",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

### Step 5: Create Service

```bash
aws ecs create-service \
  --cluster options-greeks-prod \
  --service-name options-greeks-service \
  --task-definition options-greeks-task \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxxxxx],securityGroups=[sg-xxxxxxxx],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=backend,containerPort=8000
```

---

## Option 3: AWS Elastic Beanstalk Deployment (Easiest)

### Step 1: Install EB CLI

```bash
pip install awsebcli
```

### Step 2: Initialize Elastic Beanstalk

```bash
cd options_greeks_calculator
eb init -p "Docker running on 64bit Amazon Linux 2" \
  --region us-east-1 \
  options-greeks-calc
```

### Step 3: Create Environment

```bash
# Create production environment
eb create production \
  --instance-type t3.small \
  --envvars ENVIRONMENT=production,DEBUG=false,LOG_LEVEL=WARNING
```

### Step 4: Configure Environment Variables

```bash
eb setenv ENVIRONMENT=production DEBUG=false LOG_LEVEL=WARNING
```

### Step 5: Deploy Application

```bash
git add .
git commit -m "Deploy to Elastic Beanstalk"
eb deploy
```

### Step 6: Monitor and Scale

```bash
# View logs
eb logs

# SSH into instance
eb ssh

# Scale up
eb scale 2

# View environment info
eb status
```

---

## Post-Deployment Configuration

### 1. Setup CloudFront CDN

```bash
# Create CloudFront distribution
aws cloudfront create-distribution \
  --origin-domain-name yourdomain.com \
  --default-root-object index.html
```

### 2. Setup Route 53 DNS

```bash
# Create hosted zone
aws route53 create-hosted-zone \
  --name yourdomain.com \
  --caller-reference $(date +%s)

# Create A record pointing to ALB/instance
```

### 3. Setup CloudWatch Monitoring

```bash
# Create alarms for high CPU
aws cloudwatch put-metric-alarm \
  --alarm-name options-greeks-high-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold
```

### 4. Enable Auto-Scaling

```bash
# Create launch template
aws ec2 create-launch-template \
  --launch-template-name options-greeks-template \
  --version-description "Options Greeks prod"

# Create auto-scaling group
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name options-greeks-asg \
  --launch-template LaunchTemplateName=options-greeks-template,Version='$Latest' \
  --min-size 2 \
  --max-size 10 \
  --desired-capacity 2
```

---

## Maintenance & Operations

### Health Monitoring

```bash
# Check service health (EC2)
curl https://yourdomain.com/api/health

# Check ECS service status
aws ecs describe-services \
  --cluster options-greeks-prod \
  --services options-greeks-service
```

### Viewing Logs

```bash
# EC2: SSH and view logs
ssh -i key.pem ubuntu@instance-ip
docker-compose logs -f backend

# ECS: View CloudWatch logs
aws logs tail /ecs/options-greeks --follow

# Elastic Beanstalk
eb logs
```

### Updating Application

```bash
# EC2
git pull origin main
docker-compose -f docker-compose.prod.yml up -d

# Elastic Beanstalk
eb deploy

# ECS
aws ecr get-login-password | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
docker build -t options-greeks-backend:latest ./backend
docker tag options-greeks-backend:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/options-greeks-backend:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/options-greeks-backend:latest
aws ecs update-service --cluster options-greeks-prod --service options-greeks-service --force-new-deployment
```

---

## Cost Optimization

### Estimated Monthly Costs (EC2 t3.small)
- EC2 Instance: ~$15/month
- Data Transfer: ~$1-5/month
- CloudFront (if used): ~$0.085 per GB
- **Total**: ~$20-30/month for small instance

### Cost Reduction Tips
1. Use spot instances for non-critical workloads (-70% cost)
2. Enable S3 lifecycle policies for old logs
3. Use CloudFront for static content caching
4. Monitor and cleanup unused resources
5. Use Reserved Instances for committed capacity (-25% cost)

---

## Security Best Practices

✅ **Implemented:**
- VPC with public/private subnets
- Security groups restricting access
- HTTPS with SSL/TLS
- Environment variables for secrets
- Docker non-root user
- Rate limiting on API

✅ **Recommended:**
- Enable VPC Flow Logs
- Setup WAF (Web Application Firewall)
- Enable CloudTrail for audit logs
- Use AWS Secrets Manager for sensitive data
- Enable S3 versioning for backups
- Regular security patches

---

## Troubleshooting

### Container won't start
```bash
# Check logs
docker logs greeks-calculator-backend-prod

# Check image exists
docker images

# Verify environment variables
docker inspect greeks-calculator-backend-prod
```

### High latency
```bash
# Check network connectivity
aws ec2 describe-network-interfaces

# Monitor CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization
```

### Disk space full
```bash
# Clean up Docker
docker system prune -a

# Check disk usage
df -h

# Rotate logs
docker exec greeks-calculator-backend-prod \
  bash -c "find /app/logs -type f -mtime +7 -delete"
```

---

## Rollback Procedure

```bash
# EC2
docker-compose -f docker-compose.prod.yml down
git checkout previous-working-commit
docker-compose -f docker-compose.prod.yml up -d

# ECS
aws ecs describe-services --cluster options-greeks-prod --services options-greeks-service
aws ecs update-service \
  --cluster options-greeks-prod \
  --service options-greeks-service \
  --task-definition options-greeks-task:PREVIOUS_REVISION

# Elastic Beanstalk
eb abort
```

---

## Support & Resources

- AWS EC2 Documentation: https://docs.aws.amazon.com/ec2/
- ECS Documentation: https://docs.aws.amazon.com/ecs/
- Elastic Beanstalk: https://docs.aws.amazon.com/elasticbeanstalk/
- AWS CLI Reference: https://docs.aws.amazon.com/cli/
