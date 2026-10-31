from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.routes import router as admin_router
from app.auth.routes import router as auth_router
from app.auth.service import bootstrap_admin
from app.catalog.routes import router as catalog_router
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.quoting.routes import router as quoting_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create the first admin from env (the only non-API admin path)
    with SessionLocal() as db:
        bootstrap_admin(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Intelligent Subscription Billing & Revenue Management Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(catalog_router)
app.include_router(quoting_router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": settings.app_name}
