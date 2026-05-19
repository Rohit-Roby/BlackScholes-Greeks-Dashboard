#!/usr/bin/env bash
# Deployment Validation Script for Options Greeks Calculator
# Validates Docker build, containers, API health, and performance

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="${1:-http://localhost:8000}"
FRONTEND_URL="${2:-http://localhost}"
TIMEOUT=10
RETRIES=3

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Functions
print_header() {
    echo -e "\n${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
    ((PASSED++))
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
    ((FAILED++))
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
    ((WARNINGS++))
}

# 1. Docker Build Validation
print_header "1. Docker Build Validation"

if ! command -v docker &> /dev/null; then
    print_error "Docker not installed"
else
    print_success "Docker installed"
    
    # Check Docker daemon
    if docker info > /dev/null 2>&1; then
        print_success "Docker daemon running"
    else
        print_error "Docker daemon not accessible"
    fi
fi

# 2. Image Validation
print_header "2. Docker Image Validation"

if docker images | grep -q "options-greeks-backend"; then
    print_success "Backend image exists"
else
    print_warning "Backend image not found - may need rebuild"
fi

if docker images | grep -q "nginx:alpine"; then
    print_success "Frontend image available"
else
    print_warning "Nginx image not cached"
fi

# 3. Container Status
print_header "3. Container Status"

# Check backend container
BACKEND_RUNNING=$(docker ps -q -f name="greeks.*backend" 2>/dev/null || echo "")
if [ -n "$BACKEND_RUNNING" ]; then
    print_success "Backend container running"
    
    # Get container stats
    MEMORY=$(docker stats --no-stream "$BACKEND_RUNNING" 2>/dev/null | tail -1 | awk '{print $4}')
    CPU=$(docker stats --no-stream "$BACKEND_RUNNING" 2>/dev/null | tail -1 | awk '{print $3}')
    echo "  Memory: $MEMORY | CPU: $CPU"
else
    print_error "Backend container not running"
fi

# Check frontend container
FRONTEND_RUNNING=$(docker ps -q -f name="greeks.*frontend" 2>/dev/null || echo "")
if [ -n "$FRONTEND_RUNNING" ]; then
    print_success "Frontend container running"
else
    print_error "Frontend container not running"
fi

# 4. Network Connectivity
print_header "4. Network Connectivity"

# Test backend API
for i in $(seq 1 $RETRIES); do
    if timeout $TIMEOUT curl -s "$API_URL/api/health" > /dev/null 2>&1; then
        print_success "Backend API reachable at $API_URL"
        break
    elif [ $i -eq $RETRIES ]; then
        print_error "Backend API not reachable at $API_URL"
    else
        echo "  Retry $i/$RETRIES..."
        sleep 2
    fi
done

# Test frontend
for i in $(seq 1 $RETRIES); do
    if timeout $TIMEOUT curl -s "$FRONTEND_URL" > /dev/null 2>&1; then
        print_success "Frontend reachable at $FRONTEND_URL"
        break
    elif [ $i -eq $RETRIES ]; then
        print_error "Frontend not reachable at $FRONTEND_URL"
    else
        echo "  Retry $i/$RETRIES..."
        sleep 2
    fi
done

# 5. API Endpoints
print_header "5. API Endpoints Validation"

# Health check
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" "$API_URL/api/health")
HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -n1)
BODY=$(echo "$HEALTH_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    print_success "Health endpoint responding (HTTP $HTTP_CODE)"
    echo "  Response: $(echo "$BODY" | jq -c '.status' 2>/dev/null || echo "$BODY")"
else
    print_error "Health endpoint returned HTTP $HTTP_CODE"
fi

# Calculate Greeks endpoint
CALC_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/calculate-greeks" \
  -H "Content-Type: application/json" \
  -d '{
    "spot_price": 100.0,
    "strike_price": 100.0,
    "days_to_expiration": 30,
    "interest_rate": 5,
    "implied_volatility": 25
  }')

CALC_CODE=$(echo "$CALC_RESPONSE" | tail -n1)
if [ "$CALC_CODE" = "200" ]; then
    print_success "Calculate Greeks endpoint working (HTTP $CALC_CODE)"
else
    print_error "Calculate Greeks endpoint returned HTTP $CALC_CODE"
fi

# Greeks Surface endpoint
SURFACE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/greeks-surface" \
  -H "Content-Type: application/json" \
  -d '{
    "spot_price": 100.0,
    "strike_price": 100.0,
    "days_to_expiration": 30,
    "interest_rate": 5,
    "implied_volatility": 25,
    "num_points": 10,
    "spot_range": [0.8, 1.2]
  }')

SURFACE_CODE=$(echo "$SURFACE_RESPONSE" | tail -n1)
if [ "$SURFACE_CODE" = "200" ]; then
    print_success "Greeks Surface endpoint working (HTTP $SURFACE_CODE)"
else
    print_error "Greeks Surface endpoint returned HTTP $SURFACE_CODE"
fi

# 6. Performance Testing
print_header "6. Performance Testing"

# Measure response time
START=$(date +%s%N)
curl -s "$API_URL/api/health" > /dev/null
END=$(date +%s%N)
ELAPSED=$((($END - $START) / 1000000))

if [ $ELAPSED -lt 1000 ]; then
    print_success "Health check response time: ${ELAPSED}ms"
elif [ $ELAPSED -lt 2000 ]; then
    print_warning "Health check response time: ${ELAPSED}ms (acceptable)"
else
    print_warning "Health check response time: ${ELAPSED}ms (slow)"
fi

# Calculate Greeks performance
START=$(date +%s%N)
curl -s -X POST "$API_URL/api/calculate-greeks" \
  -H "Content-Type: application/json" \
  -d '{
    "spot_price": 100.0,
    "strike_price": 100.0,
    "days_to_expiration": 30,
    "interest_rate": 5,
    "implied_volatility": 25
  }' > /dev/null
END=$(date +%s%N)
CALC_TIME=$((($END - $START) / 1000000))

if [ $CALC_TIME -lt 500 ]; then
    print_success "Calculate Greeks response time: ${CALC_TIME}ms"
elif [ $CALC_TIME -lt 1000 ]; then
    print_warning "Calculate Greeks response time: ${CALC_TIME}ms (acceptable)"
else
    print_error "Calculate Greeks response time: ${CALC_TIME}ms (slow)"
fi

# 7. Security Checks
print_header "7. Security Checks"

# Check for security headers
HEADERS=$(curl -s -I "$FRONTEND_URL" | grep -i "x-frame-options\|x-content-type\|strict-transport")
if [ -n "$HEADERS" ]; then
    print_success "Security headers present"
    echo "$HEADERS" | sed 's/^/  /'
else
    print_warning "Security headers not detected"
fi

# 8. Configuration Validation
print_header "8. Configuration Validation"

# Check environment variables
if [ -f ".env" ]; then
    print_success ".env file exists"
    
    if grep -q "ENVIRONMENT=production" .env; then
        print_success "Production environment configured"
    else
        print_warning "Not configured for production"
    fi
    
    if grep -q "DEBUG=false" .env; then
        print_success "Debug mode disabled"
    else
        print_warning "Debug mode may be enabled"
    fi
else
    print_warning ".env file not found"
fi

# 9. Docker Compose Configuration
print_header "9. Docker Compose Validation"

if [ -f "docker-compose.prod.yml" ]; then
    print_success "Production compose file exists"
    
    # Validate YAML
    if command -v docker-compose &> /dev/null; then
        if docker-compose -f docker-compose.prod.yml config > /dev/null 2>&1; then
            print_success "Docker Compose configuration valid"
        else
            print_error "Docker Compose configuration invalid"
        fi
    fi
else
    print_warning "Production compose file not found"
fi

# 10. Volume & Persistence
print_header "10. Volume & Persistence Check"

BACKEND_VOLUME=$(docker inspect "$BACKEND_RUNNING" 2>/dev/null | jq -r '.[0].Mounts[0].Name' 2>/dev/null || echo "")
if [ -n "$BACKEND_VOLUME" ]; then
    print_success "Backend volume mounted: $BACKEND_VOLUME"
else
    print_warning "Backend volume not found"
fi

# 11. Logging
print_header "11. Logging Validation"

if docker exec "$BACKEND_RUNNING" [ -d "/app/logs" ] 2>/dev/null; then
    print_success "Logs directory exists"
    
    LOG_SIZE=$(docker exec "$BACKEND_RUNNING" du -sh /app/logs 2>/dev/null | cut -f1)
    echo "  Log directory size: $LOG_SIZE"
else
    print_warning "Logs directory not accessible"
fi

# 12. Summary
print_header "Validation Summary"

TOTAL=$((PASSED + FAILED + WARNINGS))
echo -e "Total Checks: $TOTAL"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✓ Deployment validation successful!${NC}"
    exit 0
else
    echo -e "\n${RED}✗ Deployment validation failed - $FAILED issues detected${NC}"
    exit 1
fi
