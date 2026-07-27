import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from starlette.staticfiles import StaticFiles
from starlette.responses import FileResponse
from app.apis.practice_apis import UserCreate, user_list

# apis 패키지에서 라우터를 가져옵니다.
from app.apis.practice_apis import router as practice_router
from app.apis.user_apis import router as user_router
from app.apis.mypage_apis import router as mypage_router
from app.apis.auth_apis import router as auth_router
from app.apis.patient_apis import router as patient_router
from app.apis.record_api import router as record_router
from app.apis.prediction_apis import router as prediction_router
from app.apis.analysis_apis import router as analysis_router
from app.apis.email_apis import router as email_router

# API 성능 측정
from app.core.performance import log_api_performance
from app.core.redis_client import close_redis_client, redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.ping()
    yield
    await close_redis_client()


app = FastAPI(lifespan=lifespan)

app.middleware("http")(log_api_performance) #미들웨어 등록 및 API 처리 시간 측정


@app.middleware("http")
async def disable_frontend_cache(request, call_next):
    """개발 중 정적 파일 변경사항을 브라우저에 즉시 반영합니다."""

    response = await call_next(request)
    content_type = response.headers.get("content-type", "")

    if request.url.path.startswith("/static/") or content_type.startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


# 라우터 등록
app.include_router(practice_router)
app.include_router(user_router)
app.include_router(mypage_router)
app.include_router(auth_router)
app.include_router(patient_router)
app.include_router(record_router)
app.include_router(prediction_router)
app.include_router(analysis_router)
app.include_router(email_router)

BASE_DIR = Path(__file__).resolve().parent.parent

# 만약 static, media 폴더가 존재하지 않으면 생성
if not (BASE_DIR / "static").exists():
    os.mkdir(BASE_DIR / "static")
if not (BASE_DIR / "media").exists():
    os.mkdir(BASE_DIR / "media")

# 'static' 폴더를 '/static' 경로로 마운트 (CSS, JS 파일 서빙용)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
# 'media' 폴더를 '/media' 경로로 마운트 (사용자 업로드 파일 서빙용)
app.mount("/media", StaticFiles(directory=BASE_DIR / "media"), name="media")


@app.get(path="/healthcheck", status_code=200, include_in_schema=False)
async def healthcheck():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/{path:path}", include_in_schema=False)
async def catch_all(path: str):
    # API나 정적 파일 경로는 제외 (FastAPI가 먼저 매칭하지 못한 경우에만 실행됨)
    if (
        path.startswith("api/v1")
        or path.startswith("record_api")
        or path.startswith("analysis_api")
        or path.startswith("prediction_api")
        or path.startswith("email_api")
        or path.startswith("static/")
        or path.startswith("media/")
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=404)
    return FileResponse(BASE_DIR / "static" / "index.html")
