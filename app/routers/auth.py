import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth import limiter, require_api_key
from app.database import get_db
from app.models import ApiKey, User
from app.schemas import (
    CreateKeyResponse,
    MeResponse,
    SignupRequest,
    SignupResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour", key_func=get_remote_address)
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == str(payload.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(email=str(payload.email))
    db.add(user)
    db.flush()  # sends the user to the database so user.id is filled in

    key = secrets.token_hex(32)
    row = ApiKey(
        key=key,
        user_id=user.id,
        email=user.email,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return SignupResponse(api_key=row.key, email=user.email)


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
@limiter.limit("10/hour", key_func=get_remote_address)
def create_api_key(
    request: Request,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_api_key),
):
    key = secrets.token_hex(32)
    row = ApiKey(key=key, user_id=api_key.user_id, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return CreateKeyResponse(key=row.key, user_id=row.user_id, created_at=row.created_at)
