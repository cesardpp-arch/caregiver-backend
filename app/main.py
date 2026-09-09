from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from app.core.config import settings

# Import routers that already exist
from app.api.v1 import auth, shifts, pay, caregivers, clients, admin_shifts, admin_reports, admin_users
from app.api.v1 import invoice_suggest, holidays
from app.api.v1 import scheduler as scheduler_api
import app.api.v1.invoices as invoices


# ----------------------------------------------------------
# 1️⃣  CREATE THE APP FIRST
# ----------------------------------------------------------
app = FastAPI(
    title="Caregiver Logs API",
    description="Shift logging, payroll, and admin management system",
    version="1.0.0",
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_REDOC else None,
    openapi_url="/openapi.json" if settings.ENABLE_OPENAPI else None,
)

# ----------------------------------------------------------
# 2️⃣  CORS (allow front-end apps or local testing)
# ----------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def _resolve_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


@app.middleware("http")
async def protect_docs_endpoints(request: Request, call_next):
    if settings.is_production and settings.docs_allowed_ips:
        path = request.url.path
        docs_paths = {"/docs", "/redoc", "/openapi.json"}
        if path in docs_paths:
            client_ip = _resolve_client_ip(request)
            if client_ip not in settings.docs_allowed_ips:
                return JSONResponse(status_code=403, content={"detail": "Docs access forbidden from this IP"})

    return await call_next(request)

# ----------------------------------------------------------
# 3️⃣  BASIC HEALTH CHECK ENDPOINT
# ----------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# ----------------------------------------------------------
# 4️⃣  REGISTER ROUTERS AFTER app IS CREATED
# ----------------------------------------------------------
app.include_router(auth.router,         prefix="/api/v1", tags=["auth"])
app.include_router(shifts.router,       prefix="/api/v1", tags=["shifts"])
app.include_router(pay.router,          prefix="/api/v1", tags=["pay"])
app.include_router(admin_shifts.router, prefix="/api/v1", tags=["admin-shifts"])
app.include_router(caregivers.router,   prefix="/api/v1", tags=["admin-caregivers"])
app.include_router(clients.router,      prefix="/api/v1", tags=["admin-clients"])
app.include_router(admin_reports.router, prefix="/api/v1", tags=["admin-reports"])
app.include_router(admin_users.router, prefix="/api/v1", tags=["admin-users"])
app.include_router(invoices.router, prefix="/api/v1", tags=["admin-invoices"])
app.include_router(invoice_suggest.router, prefix="/api/v1", tags=["admin-invoices"])
app.include_router(holidays.router, prefix="/api/v1", tags=["admin-holidays"])
app.include_router(scheduler_api.router, prefix="/api/v1", tags=["scheduler"])


# ----------------------------------------------------------
# 5️⃣  CUSTOM OPENAPI TO ENABLE "Authorize" BUTTON IN SWAGGER
# ----------------------------------------------------------
def custom_openapi():
    if not settings.ENABLE_OPENAPI:
        return None

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Caregiver Logs API",
        version="1.0.0",
        description="Shift logging, payroll, and admin management system",
        routes=app.routes,
    )

    # JWT security scheme for Swagger Authorize
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    # Apply BearerAuth to all endpoints for convenience
    for path in openapi_schema.get("paths", {}):
        for method in openapi_schema["paths"][path]:
            openapi_schema["paths"][path][method].setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
