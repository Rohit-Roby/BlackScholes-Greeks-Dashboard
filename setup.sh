#!/bin/bash
# Options Greeks Calculator - Complete Setup Script
# This script automates the setup of both backend and frontend

set -e

echo "================================================"
echo "  Options Greeks Calculator - Setup Script"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${BLUE}Checking Python version...${NC}"
if ! command -v python &> /dev/null; then
    echo "Error: Python is not installed"
    exit 1
fi

PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python ${PYTHON_VERSION} found${NC}"
echo ""

# Setup Backend
echo -e "${BLUE}Setting up backend...${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d "backend/venv" ]; then
    echo "Creating virtual environment..."
    cd backend
    python -m venv venv
    cd ..
else
    echo "Virtual environment already exists"
fi

# Activate virtual environment
if [ -f "backend/venv/bin/activate" ]; then
    source backend/venv/bin/activate
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
else
    echo "Error: Could not activate virtual environment"
    exit 1
fi

# Install backend dependencies
echo "Installing backend dependencies..."
cd backend
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
cd ..
echo -e "${GREEN}✓ Backend dependencies installed${NC}"
echo ""

# Summary and next steps
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

echo "Next steps:"
echo ""
echo -e "${YELLOW}1. Start the Backend Server:${NC}"
echo "   cd backend"
echo "   source venv/bin/activate  # On Windows: venv\\Scripts\\activate"
echo "   python -m uvicorn app:app --host 0.0.0.0 --port 8000"
echo ""
echo -e "${YELLOW}2. Start the Frontend Server (in another terminal):${NC}"
echo "   cd frontend"
echo "   python -m http.server 8080"
echo ""
echo -e "${YELLOW}3. Open in Browser:${NC}"
echo "   http://localhost:8080"
echo ""
echo -e "${YELLOW}4. Run Tests (optional):${NC}"
echo "   cd backend"
echo "   pip install pytest"
echo "   pytest tests/ -v"
echo ""

echo "For more information, see README.md and frontend/README.md"
