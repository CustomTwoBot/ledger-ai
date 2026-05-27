from fastapi import Depends, Header, HTTPException, Request, status
from slowapi import Limiter
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiKey


def _key_from_api_key(request: Request) -> str:
    key = request.headers.get("X-API-Key")
    if key:
        return key
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_key_from_api_key)


def require_api_key(
    x_api_key: str = Header(...),
    db: Session = Depends(get_db),
) -> ApiKey:
    row = (
        db.query(ApiKey)
        .filter(ApiKey.key == x_api_key, ApiKey.is_active == True)  # noqa: E712
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )
    return row
