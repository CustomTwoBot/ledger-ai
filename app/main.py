from fastapi import FastAPI

from app.database import Base, engine
from app.routers import costs, budgets

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Cost Tracker", version="0.1.0")

app.include_router(costs.router)
app.include_router(budgets.router)


@app.get("/health")
def health():
    return {"status": "ok"}
