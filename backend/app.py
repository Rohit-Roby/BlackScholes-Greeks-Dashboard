"""
FastAPI main application for Options Greeks Calculator
Production-ready with security, monitoring, and comprehensive error handling
"""

import sys
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic_settings import BaseSettings


# ============================================================
# CONFIGURATION
# ============================================================
class Settings(BaseSettings):
    """Application settings from environment variables"""
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    api_title: str = "Options Greeks Calculator API"
    api_version: str = "1.0.0"
    
    # Logging
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_format: str = "standard"
    
    # Security
    cors_origins: str = "http://localhost:8080,http://localhost:3000"
    secret_key: str = "your-secret-key-change-in-production"
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_period: int = 60
    security_headers_enabled: bool = True
    hsts_max_age: int = 31536000
    
    # Market Data
    market_data_timeout: int = 30
    market_data_cache_enabled: bool = True
    market_data_cache_ttl: int = 300
    
    # Monitoring
    datadog_enabled: bool = False
    new_relic_enabled: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


# ============================================================
# LOGGING SETUP
# ============================================================
def setup_logging():
    """Configure logging with rotation and optional JSON format"""
    os.makedirs(settings.log_dir, exist_ok=True)
    
    # Parse log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        f"{settings.log_dir}/app.log",
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(log_level)
    
    # Formatter
    if settings.log_format == "json":
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_obj = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "environment": settings.environment,
                }
                if record.exc_info:
                    log_obj["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_obj)
        
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return logging.getLogger(__name__)


logger = setup_logging()


# ============================================================
# RATE LIMITER
# ============================================================
limiter = Limiter(key_func=get_remote_address)


# ============================================================
# APP LIFESPAN
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle app startup and shutdown"""
    logger.info(f"Starting Options Greeks Calculator API - {settings.api_version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    yield
    logger.info("Shutting down Options Greeks Calculator API")


# ============================================================
# CREATE FASTAPI APP
# ============================================================
app = FastAPI(
    title=settings.api_title,
    description="Calculate options Greeks (Delta, Gamma, Theta, Vega, Rho) using Black-Scholes model",
    version=settings.api_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# Rate limiting
if settings.rate_limit_enabled:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Too many requests."}
    ))

# Trust proxy headers for rate limiting and security
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[
    "localhost", "127.0.0.1", "0.0.0.0"
])

# Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS middleware
cors_origins = [o.strip() for o in settings.cors_origins.split(",")]
if settings.environment == "development" and "*" not in cors_origins:
    cors_origins.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if settings.environment == "development" else cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ============================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    
    if settings.security_headers_enabled:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = f"max-age={settings.hsts_max_age}; includeSubDomains"
    
    return response


# ============================================================
# ERROR HANDLING
# ============================================================
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=exc)
    
    if settings.debug:
        raise exc
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )


# ============================================================
# ROUTES
# ============================================================
# Import routes - support both package and standalone run
try:
    from backend.routes import api, analytics
except ImportError:
    from routes import api, analytics

# Include API routes
app.include_router(api.router)
app.include_router(analytics.router)


# ============================================================
# BASIC ENDPOINTS
# ============================================================
@app.get("/")
async def root():
    """Root endpoint - API welcome message"""
    return {
        "message": "Options Greeks Calculator API",
        "version": settings.api_version,
        "environment": settings.environment,
        "docs": "/docs" if settings.debug else None,
        "health": "/api/health"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        logger.debug("Health check performed")
        return {
            "status": "healthy",
            "service": "Options Greeks Calculator API",
            "version": settings.api_version,
            "environment": settings.environment
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


# ============================================================
# STARTUP
# ============================================================
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=settings.environment == "development",
    )
