from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.routers import gifts, people, checkout, auth, admin, analytics, studio_agent

app = FastAPI(title="Kadoku API", version="0.1.0")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(gifts.router)
app.include_router(people.router)
app.include_router(checkout.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(studio_agent.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "kadoku-api"}
