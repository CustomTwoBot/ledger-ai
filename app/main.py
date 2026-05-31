from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.auth import limiter
from app.database import Base, engine
from app.routers import costs, budgets
from app.routers import auth as auth_router
from app.routers import dashboard as dashboard_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Cost Tracker", version="0.1.0", docs_url=None, redoc_url=None)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' blob:; "
            "font-src 'self' blob: data:; "
            "frame-ancestors 'none'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router.router)
app.include_router(costs.router)
app.include_router(budgets.router)
app.include_router(dashboard_router.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dashboard")
def dashboard():
    return FileResponse("frontend/Dashboard.html")


@app.get("/privacy")
def privacy():
    return FileResponse("frontend/privacy.html")


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return FileResponse("frontend/robots.txt")
