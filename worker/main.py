import json
import logging
import os
import signal
import socket
import time
from pathlib import Path

from redis.exceptions import RedisError

from worker.predictors.registry import get_predictor
from worker.redis_client import (
    PREDICTION_CONSUMER_GROUP,
    PREDICTION_TASK_STREAM,
    ensure_consumer_group,
    redis_client,
    release_lock,
)


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(
    os.getenv(
        "MEDIA_ROOT",
        str(Path(__file__).resolve().parents[1] / "media"),
    )
).resolve()
CONSUMER_NAME = os.getenv(
    "PREDICTION_CONSUMER_NAME",
    f"{socket.gethostname()}-{os.getpid()}",
)
BLOCK_MILLISECONDS = int(os.getenv("PREDICTION_BLOCK_MS", "5000"))
CLAIM_IDLE_MILLISECONDS = int(
    os.getenv("PREDICTION_CLAIM_IDLE_MS", "300000")
)
RESULT_TTL_SECONDS = int(
    os.getenv("PREDICTION_RESULT_TTL_SECONDS", "300")
)

stop_requested = False


def _request_stop(signum, frame) -> None:
    global stop_requested
    stop_requested = True
    logger.info("AI worker 종료 요청 수신: signal=%s", signum)


def _safe_media_path(raw_path: str, must_exist: bool) -> Path:
    path = Path(raw_path).resolve()
    if not path.is_relative_to(MEDIA_ROOT):
        raise ValueError("허용되지 않은 media 파일 경로입니다.")
    if must_exist and not path.is_file():
        raise FileNotFoundError(path)
    return path


def _publish_success(task: dict, result: dict) -> None:
    payload = json.dumps(
        {
            "task_id": task["task_id"],
            "status": "SUCCESS",
            "result": result,
        },
        ensure_ascii=False,
    )
    with redis_client.pipeline(transaction=True) as pipe:
        pipe.set(
            task["result_cache_key"],
            payload,
            ex=RESULT_TTL_SECONDS,
        )
        pipe.publish(task["result_channel"], payload)
        pipe.execute()


def _publish_failure(task: dict, exc: Exception) -> None:
    payload = json.dumps(
        {
            "task_id": task["task_id"],
            "status": "FAILURE",
            "error": str(exc),
            "error_type": type(exc).__name__,
        },
        ensure_ascii=False,
    )
    redis_client.publish(task["result_channel"], payload)


def _acknowledge(message_id: str) -> None:
    redis_client.xack(
        PREDICTION_TASK_STREAM,
        PREDICTION_CONSUMER_GROUP,
        message_id,
    )
    redis_client.xdel(PREDICTION_TASK_STREAM, message_id)


def _process_message(message_id: str, task: dict) -> None:
    logger.info(
        "예측 작업 시작: message_id=%s task_id=%s model=%s xray=%s",
        message_id,
        task.get("task_id"),
        task.get("model_key"),
        task.get("xray_image_id"),
    )

    try:
        image_path = _safe_media_path(task["image_path"], must_exist=True)
        heatmap_path = _safe_media_path(
            task["heatmap_path"],
            must_exist=False,
        )
        heatmap_path.parent.mkdir(parents=True, exist_ok=True)

        predictor = get_predictor(task["model_key"])
        prediction = predictor.predict(image_path, heatmap_path)
        result = {
            "record_id": int(task["record_id"]),
            "xray_image_id": int(task["xray_image_id"]),
            "is_pneumonia": prediction.is_pneumonia,
            "confidence": prediction.confidence,
            "heatmap_url": task["heatmap_url"],
            "heatmap_model": prediction.heatmap_model,
            "ai_model": prediction.ai_model,
        }
        _publish_success(task, result)

    except Exception as exc:
        logger.exception(
            "예측 작업 실패: message_id=%s task_id=%s",
            message_id,
            task.get("task_id"),
        )
        # 실패 메시지 발행까지 성공해야 작업을 ACK한다.
        _publish_failure(task, exc)
        release_lock(task["lock_key"], task["task_id"])

    _acknowledge(message_id)
    logger.info(
        "예측 작업 완료: message_id=%s task_id=%s",
        message_id,
        task.get("task_id"),
    )


def _claim_stale_messages() -> list[tuple[str, dict]]:
    response = redis_client.xautoclaim(
        PREDICTION_TASK_STREAM,
        PREDICTION_CONSUMER_GROUP,
        CONSUMER_NAME,
        min_idle_time=CLAIM_IDLE_MILLISECONDS,
        start_id="0-0",
        count=1,
    )
    return response[1] if len(response) > 1 else []


def _read_new_messages() -> list[tuple[str, dict]]:
    response = redis_client.xreadgroup(
        PREDICTION_CONSUMER_GROUP,
        CONSUMER_NAME,
        {PREDICTION_TASK_STREAM: ">"},
        count=1,
        block=BLOCK_MILLISECONDS,
    )
    return response[0][1] if response else []


def run() -> None:
    ensure_consumer_group()
    logger.info(
        "AI worker 시작: stream=%s group=%s consumer=%s",
        PREDICTION_TASK_STREAM,
        PREDICTION_CONSUMER_GROUP,
        CONSUMER_NAME,
    )

    while not stop_requested:
        try:
            messages = _claim_stale_messages()
            if not messages:
                messages = _read_new_messages()
            for message_id, task in messages:
                _process_message(message_id, task)
        except RedisError:
            logger.exception("Redis 연결 오류, 3초 후 재시도합니다.")
            time.sleep(3)
        except Exception:
            logger.exception("AI worker 처리 오류, 1초 후 재시도합니다.")
            time.sleep(1)

    redis_client.close()
    logger.info("AI worker 종료")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    run()
