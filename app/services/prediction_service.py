import asyncio
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.prediction_models import get_ai_model_name
from app.core.redis_client import (
    get_redis_client,
    prediction_cache_key,
    prediction_lock_key,
    prediction_result_cache_key,
    prediction_result_channel,
    release_prediction_lock,
)
from app.models.ai_analysis_results import AIAnalysisResult
from app.models.medical_records import MedicalRecord
from app.models.xray_images import XrayImages


MEDIA_ROOT = Path(__file__).resolve().parents[2] / "media"
HEATMAP_DIR = MEDIA_ROOT / "uploads" / "heatmaps"


class MedicalRecordNotFoundError(Exception):
    """진료기록을 찾을 수 없는 경우."""


class XrayImageNotFoundError(Exception):
    """진료기록에 예측 가능한 X-Ray가 없는 경우."""


class PredictionFailedError(Exception):
    """AI worker가 예측에 실패한 경우."""


class PredictionQueueUnavailableError(Exception):
    """Redis 작업 큐를 사용할 수 없는 경우."""


class PredictionResultTimeoutError(TimeoutError):
    """제한 시간 안에 worker 결과를 받지 못한 경우."""


async def _find_medical_record(
    db: AsyncSession,
    record_id: int,
) -> MedicalRecord | None:
    result = await db.execute(
        select(MedicalRecord).where(MedicalRecord.id == record_id)
    )
    return result.scalar_one_or_none()


async def _find_latest_xray(
    db: AsyncSession,
    record_id: int,
) -> XrayImages | None:
    result = await db.execute(
        select(XrayImages)
        .where(XrayImages.record_id == record_id)
        .order_by(
            XrayImages.shooting_datetime.desc(),
            XrayImages.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_existing_prediction(
    db: AsyncSession,
    xray_image_id: int,
    ai_model: str,
) -> AIAnalysisResult | None:
    result = await db.execute(
        select(AIAnalysisResult).where(
            AIAnalysisResult.xray_image_id == xray_image_id,
            AIAnalysisResult.ai_model == ai_model,
        )
    )
    return result.scalar_one_or_none()


def _resolve_media_path(media_url: str) -> Path:
    media_prefix = "/media/"
    if not media_url.startswith(media_prefix):
        raise XrayImageNotFoundError

    media_root = MEDIA_ROOT.resolve()
    file_path = (
        media_root / media_url.removeprefix(media_prefix)
    ).resolve()
    if not file_path.is_relative_to(media_root) or not file_path.is_file():
        raise XrayImageNotFoundError
    return file_path


def _has_available_heatmap(analysis: AIAnalysisResult) -> bool:
    if not analysis.heatmap_url or not analysis.heatmap_model:
        return False
    try:
        _resolve_media_path(analysis.heatmap_url)
    except XrayImageNotFoundError:
        return False
    return True


def _heatmap_destination(
    record_id: int,
    xray_image_id: int,
    model_key: str,
    ai_model: str,
) -> tuple[Path, str]:
    model_hash = hashlib.sha256(
        ai_model.encode("utf-8")
    ).hexdigest()[:12]
    file_name = (
        f"record_{record_id}_xray_{xray_image_id}_{model_hash}.jpg"
    )
    return (
        HEATMAP_DIR / model_key / file_name,
        f"/media/uploads/heatmaps/{model_key}/{file_name}",
    )


async def get_cached_prediction(
    db: AsyncSession,
    record_id: int,
    model_key: str,
) -> AIAnalysisResult | None:
    if await _find_medical_record(db, record_id) is None:
        raise MedicalRecordNotFoundError

    xray = await _find_latest_xray(db, record_id)
    if xray is None:
        raise XrayImageNotFoundError

    analysis = await _find_existing_prediction(
        db,
        xray.id,
        get_ai_model_name(model_key),
    )
    if analysis is not None and _has_available_heatmap(analysis):
        return analysis
    return None


async def _wait_for_worker_result(
    pubsub,
    result_cache_key: str,
    timeout_seconds: float,
) -> dict:
    redis = get_redis_client()
    cached_payload = await redis.get(result_cache_key)
    if cached_payload:
        return json.loads(cached_payload)

    try:
        async with asyncio.timeout(timeout_seconds):
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is not None:
                    return json.loads(message["data"])

                cached_payload = await redis.get(result_cache_key)
                if cached_payload:
                    return json.loads(cached_payload)
                await asyncio.sleep(0.01)
    except TimeoutError as exc:
        raise PredictionResultTimeoutError from exc


async def _save_worker_result(
    db: AsyncSession,
    payload: dict,
    record_id: int,
    xray_image_id: int,
    expected_ai_model: str,
) -> tuple[AIAnalysisResult, bool]:
    result_data = payload["result"]
    if (
        int(result_data["record_id"]) != record_id
        or int(result_data["xray_image_id"]) != xray_image_id
        or result_data["ai_model"] != expected_ai_model
    ):
        raise PredictionFailedError("예측 결과 식별자가 요청과 일치하지 않습니다.")

    existing = await _find_existing_prediction(
        db,
        xray_image_id,
        expected_ai_model,
    )
    if existing is not None and _has_available_heatmap(existing):
        return existing, True

    if existing is None:
        analysis = AIAnalysisResult(
            record_id=record_id,
            xray_image_id=xray_image_id,
            ai_model=expected_ai_model,
            is_pneumonia=bool(result_data["is_pneumonia"]),
            confidence=Decimal(str(result_data["confidence"])),
            heatmap_url=result_data["heatmap_url"],
            heatmap_model=result_data.get("heatmap_model"),
        )
        db.add(analysis)
    else:
        analysis = existing
        analysis.is_pneumonia = bool(result_data["is_pneumonia"])
        analysis.confidence = Decimal(str(result_data["confidence"]))
        analysis.heatmap_url = result_data["heatmap_url"]
        analysis.heatmap_model = result_data.get("heatmap_model")

    try:
        await db.commit()
        await db.refresh(analysis)
        return analysis, False
    except IntegrityError:
        await db.rollback()
        concurrent_result = await _find_existing_prediction(
            db,
            xray_image_id,
            expected_ai_model,
        )
        if concurrent_result is not None:
            return concurrent_result, True
        raise
    except Exception:
        await db.rollback()
        raise


async def enqueue_prediction_and_wait(
    db: AsyncSession,
    record_id: int,
    model_key: str,
    timeout_seconds: float,
) -> tuple[AIAnalysisResult, bool]:
    if await _find_medical_record(db, record_id) is None:
        raise MedicalRecordNotFoundError

    xray = await _find_latest_xray(db, record_id)
    if xray is None:
        raise XrayImageNotFoundError

    xray_image_id = int(xray.id)
    xray_image_url = str(xray.image_url)
    ai_model = get_ai_model_name(model_key)
    existing = await _find_existing_prediction(
        db,
        xray_image_id,
        ai_model,
    )
    if existing is not None and _has_available_heatmap(existing):
        return existing, True

    image_path = _resolve_media_path(xray_image_url)
    heatmap_path, heatmap_url = _heatmap_destination(
        record_id,
        xray_image_id,
        model_key,
        ai_model,
    )
    await db.rollback()

    redis = get_redis_client()
    cache_key = prediction_cache_key(xray_image_id, model_key)
    channel = prediction_result_channel(cache_key)
    result_cache_key = prediction_result_cache_key(cache_key)
    lock_key = prediction_lock_key(cache_key)
    task_id = str(uuid4())
    pubsub = redis.pubsub()
    subscribed = False

    try:
        await pubsub.subscribe(channel)
        subscribed = True

        payload = await redis.get(result_cache_key)
        if payload is None:
            lock_acquired = await redis.set(
                lock_key,
                task_id,
                nx=True,
                ex=settings.PREDICTION_LOCK_TTL_SECONDS,
            )
            if lock_acquired:
                try:
                    await redis.xadd(
                        settings.PREDICTION_TASK_STREAM,
                        {
                            "task_id": task_id,
                            "record_id": str(record_id),
                            "xray_image_id": str(xray_image_id),
                            "model_key": model_key,
                            "image_path": str(image_path),
                            "heatmap_path": str(heatmap_path),
                            "heatmap_url": heatmap_url,
                            "result_channel": channel,
                            "result_cache_key": result_cache_key,
                            "lock_key": lock_key,
                        },
                        maxlen=settings.PREDICTION_STREAM_MAXLEN,
                        approximate=True,
                    )
                except Exception:
                    await release_prediction_lock(lock_key, task_id)
                    raise

            payload = await _wait_for_worker_result(
                pubsub,
                result_cache_key,
                timeout_seconds,
            )
        else:
            payload = json.loads(payload)

    except PredictionResultTimeoutError:
        raise
    except RedisError as exc:
        raise PredictionQueueUnavailableError from exc
    finally:
        if subscribed:
            try:
                await pubsub.unsubscribe(channel)
            except RedisError:
                pass
        await pubsub.aclose()

    result_task_id = payload.get("task_id", task_id)
    if payload.get("status") != "SUCCESS":
        await release_prediction_lock(lock_key, result_task_id)
        raise PredictionFailedError(payload.get("error"))

    analysis, cached = await _save_worker_result(
        db,
        payload,
        record_id,
        xray_image_id,
        ai_model,
    )
    await redis.delete(result_cache_key)
    await release_prediction_lock(lock_key, result_task_id)
    return analysis, cached


async def get_prediction_results(
    db: AsyncSession,
    record_id: int,
) -> list[AIAnalysisResult]:
    if await _find_medical_record(db, record_id) is None:
        raise MedicalRecordNotFoundError

    result = await db.execute(
        select(AIAnalysisResult)
        .where(AIAnalysisResult.record_id == record_id)
        .order_by(
            AIAnalysisResult.created_at.desc(),
            AIAnalysisResult.id.desc(),
        )
    )
    return list(result.scalars().all())
