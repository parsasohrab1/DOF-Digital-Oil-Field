"""
Authentication & Authorization Service
Handles OIDC/OAuth2, RBAC/ABAC, mTLS, and session management
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
import uvicorn
import sys
import os

# Add backend root to path so `shared` is importable as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import get_db
from shared.models import User
from shared.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_2fa_secret,
    verify_2fa_token,
    generate_2fa_qr_code_uri,
    extract_token_jti,
)
from shared.config import settings
from shared.logging_config import setup_logging
from sqlalchemy.orm import Session
from shared.rate_limiter import rate_limit_dependency
from shared.token_store import refresh_token_store
from shared.security_alerts import security_alerts
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from shared.threat_detection import siem_logger, threat_detector

# Setup logging
logger = setup_logging("auth-service")

app = FastAPI(
    title="OGIM Auth Service",
    version="1.0.0",
    description="Authentication and Authorization Service",
)

setup_metrics(app, "auth-service")
setup_tracing(app, "auth-service")
# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Pydantic models
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    disabled: bool
    two_factor_enabled: bool

    class Config:
        from_attributes = True


class TwoFactorSetup(BaseModel):
    secret: str
    qr_code_uri: str


class TwoFactorVerify(BaseModel):
    token: str


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except ValueError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")

    return user


async def get_current_active_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Verify user is admin"""
    if current_user.role != "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    return current_user


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Starting auth service...")
    logger.info("Ensure database migrations are applied before accepting traffic.")


@app.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    _: bool = Depends(rate_limit_dependency),
):
    """Authenticate user and return access token"""
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Failed login attempt for user: {form_data.username}")
        security_alerts.record_login_failure(form_data.username)
        risk_score, reasons = threat_detector.evaluate(
            ip="unknown",
            user=form_data.username,
            path="/token",
            method="POST",
            status_code=401,
            user_agent="",
        )
        siem_logger.emit(
            "auth_failed_login",
            "high" if risk_score >= 60 else "medium",
            {
                "username": form_data.username,
                "risk_score": risk_score,
                "reasons": reasons,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")

    # Create tokens
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    refresh_token = create_refresh_token(data={"sub": user.username})
    refresh_payload = decode_token(refresh_token)
    refresh_jti = extract_token_jti(refresh_payload)
    expires_at = datetime.utcfromtimestamp(refresh_payload["exp"])
    refresh_token_store.register_token(refresh_jti, expires_at)
    security_alerts.reset_user(user.username)
    siem_logger.emit(
        "auth_login_success",
        "low",
        {
            "username": user.username,
            "role": user.role,
        },
    )

    logger.info(f"User logged in: {user.username}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    """Refresh access token"""
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        username: str = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()

        if not user or user.disabled:
            raise HTTPException(status_code=401, detail="Invalid token")

        old_jti = extract_token_jti(payload)
        if not refresh_token_store.is_token_active(old_jti):
            raise HTTPException(
                status_code=401, detail="Refresh token revoked or expired"
            )

        # Create new tokens
        new_access_token = create_access_token(
            data={"sub": user.username, "role": user.role}
        )
        new_refresh_token = create_refresh_token(data={"sub": user.username})
        new_payload = decode_token(new_refresh_token)
        new_jti = extract_token_jti(new_payload)
        new_exp = datetime.utcfromtimestamp(new_payload["exp"])

        # revoke old token and register new one
        if old_jti:
            refresh_token_store.revoke_token(
                old_jti, datetime.utcfromtimestamp(payload["exp"])
            )
        refresh_token_store.register_token(new_jti, new_exp)
        siem_logger.emit(
            "auth_token_refresh",
            "low",
            {"username": user.username, "old_jti": old_jti, "new_jti": new_jti},
        )

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.get("/users/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user


@app.post("/users", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_user(
    user: UserCreate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db),
):
    """Create new user (admin only)"""
    # Check if username exists
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Check if email exists
    existing_email = db.query(User).filter(User.email == user.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")

    # Create new user
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        role=user.role,
        disabled=False,
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    logger.info(f"User created: {user.username} by {current_user.username}")

    return db_user


@app.get("/users/{username}", response_model=UserResponse)
async def get_user(
    username: str,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db),
):
    """Get user by username (admin only)"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/users/me/2fa/setup", response_model=TwoFactorSetup)
async def setup_2fa(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Setup 2FA for current user"""
    if current_user.two_factor_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")

    # Generate secret
    secret = generate_2fa_secret()
    qr_uri = generate_2fa_qr_code_uri(secret, current_user.email)

    # Save secret (not enabled yet)
    current_user.two_factor_secret = secret
    db.commit()

    logger.info(f"2FA setup initiated for user: {current_user.username}")

    return {"secret": secret, "qr_code_uri": qr_uri}


@app.post("/users/me/2fa/enable")
async def enable_2fa(
    verify: TwoFactorVerify,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enable 2FA after verification"""
    if not current_user.two_factor_secret:
        raise HTTPException(status_code=400, detail="2FA not setup")

    if not verify_2fa_token(current_user.two_factor_secret, verify.token):
        raise HTTPException(status_code=400, detail="Invalid 2FA token")

    # Enable 2FA
    current_user.two_factor_enabled = True
    db.commit()

    logger.info(f"2FA enabled for user: {current_user.username}")

    return {"message": "2FA enabled successfully"}


@app.post("/users/me/2fa/disable")
async def disable_2fa(
    verify: TwoFactorVerify,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disable 2FA"""
    if not current_user.two_factor_enabled:
        raise HTTPException(status_code=400, detail="2FA not enabled")

    if not verify_2fa_token(current_user.two_factor_secret, verify.token):
        raise HTTPException(status_code=400, detail="Invalid 2FA token")

    # Disable 2FA
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    db.commit()

    logger.info(f"2FA disabled for user: {current_user.username}")

    return {"message": "2FA disabled successfully"}


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "auth-service"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
