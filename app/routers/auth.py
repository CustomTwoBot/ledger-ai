import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiKey
from app.schemas import CreateKeyRequest, CreateKeyResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/create-key", response_model=CreateKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(payload: CreateKeyRequest, db: Session = Depends(get_db)):
    key = secrets.token_hex(32)
    row = ApiKey(key=key, user_id=payload.user_id, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    return CreateKeyResponse(key=row.key, user_id=row.user_id, created_at=row.created_at)
