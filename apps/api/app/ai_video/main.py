"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai_video.api.v1 import router as api_v1_router
from app.ai_video.bootstrap import bootstrap_all_registries
from app.ai_video.config import settings
from app.ai_video.schemas.common import ApiResponse


def _error_message(detail: object) -> str:
    """将异常 detail 转为前端可读的 message。"""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict) and "msg" in item:
                loc = item.get("loc", ())
                loc_str = ".".join(str(x) for x in loc if x != "body")
                parts.append(f"{loc_str}: {item['msg']}" if loc_str else item["msg"])
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else "Validation error"
    return str(detail)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """HTTP 异常统一为 { code, message, data: null }。"""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        code = exc.status_code
        message = _error_message(exc.detail)
    else:
        code = 500
        message = "Internal server error"
    body = ApiResponse[None](code=code, message=message, data=None, meta=None).model_dump()
    return JSONResponse(status_code=code, content=body)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """422 校验异常统一为 { code: 422, message, data: null }。"""
    assert isinstance(exc, RequestValidationError)
    message = _error_message(exc.errors())
    body = ApiResponse[None](code=422, message=message, data=None, meta=None).model_dump()
    return JSONResponse(status_code=422, content=body)


async def initialize_ai_video_module() -> None:
    """Prepare AI Video persistence and registries inside the Incept API process."""
    # The deployed Cloud Run init job owns Cloud SQL schema setup.  Local
    # development instead uses the documented default SQLite database, so make
    # its first launch usable without a separate manual bootstrap command.
    if settings.resolved_database_url.startswith("sqlite"):
        from app.ai_video.core.db import init_db

        await init_db()
    # 启动时：供应商注册 + 任务执行器注册（幂等）
    bootstrap_all_registries()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Retain a standalone lifespan for focused AI Video module tests."""
    await initialize_ai_video_module()
    yield
    # 关闭时：清理资源
    pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 统一错误响应格式：{ code, message, data: null }
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, http_exception_handler)


@app.middleware("http")
async def require_linglong_proxy_key(request: Request, call_next):
    """Reject direct production API access while retaining empty-key local development.

    Linglong's `/api/ai-video` bridge adds this header after validating the
    NextAuth session. The Linglong Lab AI Video module intentionally has no browser credential
    handling of its own, so this narrow boundary prevents accidental public use
    when the service is deployed outside a private Cloud Run ingress policy.
    """
    expected = settings.internal_api_key.strip()
    if expected and request.headers.get("x-internal-api-key") != expected:
        body = ApiResponse[None](code=401, message="Unauthorized", data=None, meta=None).model_dump()
        return JSONResponse(status_code=401, content=body)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
# 影视技能路由同时挂到主应用，保证 /api/v1/film 一定可访问


@app.get("/health")
async def health():
    """健康检查。"""
    from app.ai_video.schemas.common import success_response
    return success_response({"status": "ok"})
