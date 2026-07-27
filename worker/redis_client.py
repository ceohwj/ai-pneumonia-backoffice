import os

from redis import Redis
from redis.exceptions import ResponseError


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/2")
PREDICTION_TASK_STREAM = os.getenv(
    "PREDICTION_TASK_STREAM",
    "prediction:tasks",
)
PREDICTION_CONSUMER_GROUP = os.getenv(
    "PREDICTION_CONSUMER_GROUP",
    "prediction-workers",
)

redis_client = Redis.from_url(
    REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    health_check_interval=30,
)


def ensure_consumer_group() -> None:
    try:
        redis_client.xgroup_create(
            PREDICTION_TASK_STREAM,
            PREDICTION_CONSUMER_GROUP,
            id="0-0",
            mkstream=True,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def release_lock(lock_key: str, task_id: str) -> None:
    redis_client.eval(
        """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """,
        1,
        lock_key,
        task_id,
    )
