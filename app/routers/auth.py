import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.models import ApiKey
from app.schemas import (
    CreateKeyRequest,
    CreateKeyResponse,
    MeResponse,
    SignupRequest,
    SignupResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(ApiKey).filter(ApiKey.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    key = secrets.token_hex(32)
    row = ApiKey(
        key=key,
        user_id=str(payload.email),
        email=str(payload.email),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return SignupResponse(api_key=row.key, email=row.email)


@router.get("/me", response_model=MeResponse)
def me(api_key: ApiKey = Depends(require_api_key)):
    return MeResponse(
        key=api_key.key,
        email=api_key.email,
        user_id=api_key.user_id,
        created_at=api_key.created_at,
        is_active=api_key.is_active,
    )


@router.post("/create-key", response_model=CreateKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(payload: CreateKeyRequest, db: Session = Depends(get_db)):
    key = secrets.token_hex(32)
    row = ApiKey(key=key, user_id=payload.user_id, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return CreateKeyResponse(key=row.key, user_id=row.user_id, created_at=row.created_at)
