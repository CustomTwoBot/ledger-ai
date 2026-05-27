from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth import limiter
from app.database import Base, engine
from app.routers import costs, budgets
from app.routers import auth as auth_router
from app.routers import dashboard as dashboard_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Cost Tracker", version="0.1.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(costs.router)
app.include_router(budgets.router)
app.include_router(dashboard_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dashboard")
def dashboard():
    return FileResponse("frontend/Dashboard.html")
