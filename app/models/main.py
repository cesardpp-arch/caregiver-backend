from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import auth, shifts, pay, invoices
from app.core.config import settings

app = FastAPI(title="Caregiver Logs API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(shifts.router, prefix="/api/v1", tags=["shifts"])
app.include_router(pay.router, prefix="/api/v1", tags=["pay"])
app.include_router(invoices.router, prefix="/api/v1", tags=["admin-invoices"])