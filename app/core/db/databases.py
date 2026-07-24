from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from typing import AsyncGenerator
from app.core.config import settings

DATABASE_PREFIX = "mysql+asyncmy://"
DATABASE_URI = f"{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
DATABASE_URL = f"{DATABASE_PREFIX}{DATABASE_URI}"


# 비동기 엔진 생성 # future=True는 SQLAlchemy 2.0에서는 기본 동작이므로 제거
async_engine = create_async_engine(
    DATABASE_URL,
    echo=settings.DB_ECHO,
    # SQLAlchemy 2.0.49의 MySQL pre-ping은 ping()을 호출하지만
    # asyncmy 어댑터는 ping(reconnect)을 요구해 TypeError가 발생합니다.
    # 오래된 연결은 pool_recycle로 교체합니다.
    pool_pre_ping=False,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
)
#async_engine = create_async_engine(DATABASE_URL, echo=False, future=True, connect_args={"check_same_thread": False})

# 비동기 세션 팩토리 생성
AsyncSessionLocal = async_sessionmaker(bind=async_engine, autoflush=False, expire_on_commit=False)
# 모델 베이스 생성
Base = declarative_base()

# 세션 생성 함수
async def async_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as db:
        yield db
