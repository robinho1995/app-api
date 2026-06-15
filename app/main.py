from __future__ import annotations
import logging
import sys
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base, check_db_connection
from app.routers import health
from app.routers import items as items_router
from app.telemetry import setup_telemetry
import redis.asyncio as aioredis
import os

logging.basicConfig(
    level=logging.INFO,
    format="\033[90m%(asctime)s\033[0m %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BRIGHT = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RESET = "\033[0m"

redis_client: aioredis.Redis | None = None


def _banner(app: FastAPI):
    routes = [
        (route.path, list(route.methods or []))
        for route in app.routes
        if hasattr(route, "methods")
    ]

    print()
    print(f"  {BRIGHT}{CYAN}╔══════════════════════════════════════════════════╗{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}  {BRIGHT}{GREEN}MBA DevOps + SRE API{RESET}                          {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}╠══════════════════════════════════════════════════╣{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}  {YELLOW}Version:{RESET}     {app.version}                                {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}  {YELLOW}Environment:{RESET} {settings.ENVIRONMENT}                          {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}  {YELLOW}Database:{RESET}    {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}       {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}  {YELLOW}Redis:{RESET}       {settings.REDIS_HOST}:{settings.REDIS_PORT}                          {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}╠══════════════════════════════════════════════════╣{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}  {BRIGHT}Routes:{RESET}                                        {BRIGHT}{CYAN}║{RESET}")
    for path, methods in routes:
        method_str = " ".join(f"{GREEN}{m}{RESET}" for m in sorted(methods))
        print(f"  {BRIGHT}{CYAN}║{RESET}    {method_str}  {BLUE}{path}{RESET}")
    print(f"  {BRIGHT}{CYAN}╠══════════════════════════════════════════════════╣{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}  {BRIGHT}SLOs:{RESET}                                           {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}    {GREEN}Availability{RESET} >= 99.9%                              {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}    {GREEN}Latency p99{RESET} < 500ms                              {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}    {GREEN}Latency p95{RESET} < 200ms                              {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}║{RESET}    {GREEN}Error rate{RESET}  < 0.1%                               {BRIGHT}{CYAN}║{RESET}")
    print(f"  {BRIGHT}{CYAN}╚══════════════════════════════════════════════════╝{RESET}")
    print(f"  {DIM}Docs: http://localhost:8000/docs{RESET}")
    print()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client

    print(f"\n  {BRIGHT}{MAGENTA}>>> Starting MBA DevOps + SRE API...{RESET}\n")

    try:
        db_url = f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        print(f"  {CYAN}•{RESET}  {BRIGHT}Database:{RESET}  connecting to {db_url}...")
        import subprocess
        import os

        alembic_ini = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini")

        result = subprocess.run(
            [
                sys.executable, "-m", "alembic",
                "-c", alembic_ini,
                "-x", f"db_url={settings.SYNC_DATABASE_URL}",
                "upgrade", "head",
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env={**os.environ, "DATABASE_URL": settings.SYNC_DATABASE_URL},
        )

        if result.returncode == 0:
            print(f"  {GREEN}✓{RESET}  {BRIGHT}Alembic:{RESET}   migrations applied")
            for line in result.stdout.strip().split("\n"):
                if "Running upgrade" in line:
                    parts = line.strip().split("Running upgrade")
                    if len(parts) == 2:
                        print(f"  {GREEN}✓{RESET}  {BRIGHT}Alembic:{RESET}   {parts[1].strip()}")
            print(f"  {GREEN}✓{RESET}  {BRIGHT}Database:{RESET}  schema up to date!")
        else:
            print(f"  {YELLOW}⚠{RESET}  {BRIGHT}Alembic:{RESET}   migration failed, falling back to create_all")
            for line in result.stderr.strip().split("\n")[-2:]:
                if line.strip():
                    print(f"  {YELLOW}  {RESET}{line.strip()}")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print(f"  {GREEN}✓{RESET}  {BRIGHT}Database:{RESET}  tables created (create_all fallback)")
    except Exception as e:
        print(f"  {RED}✗{RESET}  {BRIGHT}Database:{RESET}  not available — {e}")

    try:
        redis_client = aioredis.from_url(settings.REDIS_URL_COMPUTED, decode_responses=True)
        await redis_client.ping()
        print(f"  {GREEN}✓{RESET}  {BRIGHT}Redis:{RESET}     connected ({settings.REDIS_HOST}:{settings.REDIS_PORT})")
    except Exception:
        print(f"  {RED}✗{RESET}  {BRIGHT}Redis:{RESET}     not available — caching disabled")
        redis_client = None

    _banner(app)
    print(f"  {BRIGHT}{GREEN}>>> API ready! Listening on http://0.0.0.0:8000{RESET}\n")

    yield

    print(f"\n  {YELLOW}>>> Shutting down...{RESET}\n")
    if redis_client:
        await redis_client.close()
    await engine.dispose()
    print(f"  {GREEN}✓{RESET}  Connections closed.\n")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Pega da variável de ambiente, se não existir usa um fallback
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

setup_telemetry(app=app, app_name="app-api", endpoint=otel_endpoint)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    method_colors = {
        "GET": GREEN,
        "POST": CYAN,
        "PUT": YELLOW,
        "PATCH": MAGENTA,
        "DELETE": RED,
    }
    method_color = method_colors.get(request.method, "")

    if response.status_code < 400:
        status_color = GREEN
    elif response.status_code < 500:
        status_color = YELLOW
    else:
        status_color = RED

    print(
        f"  {method_color}{BRIGHT}{request.method:7s}{RESET} "
        f"{status_color}{response.status_code}{RESET} "
        f"{BLUE}{request.url.path}{RESET} "
        f"{DIM}{duration_ms:.1f}ms{RESET}"
    )

    return response


app.include_router(health.router, tags=["health"])
app.include_router(items_router.router)


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/metrics")
async def metrics():
    db_ok = await check_db_connection()
    redis_ok = False
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            pass
    return {
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
        "uptime_seconds": 0,
    }


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)