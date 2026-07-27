from redis.asyncio import Redis

from app.core.config import settings


redis_client = Redis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    health_check_interval=30,
)


def get_redis_client() -> Redis:
    return redis_client


def prediction_cache_key(xray_image_id: int, model_key: str) -> str:
    return f"{xray_image_id}:{model_key}"


def prediction_result_channel(cache_key: str) -> str:
    return f"prediction:result:{cache_key}"


def prediction_result_cache_key(cache_key: str) -> str:
    return f"prediction:result-cache:{cache_key}"


def prediction_lock_key(cache_key: str) -> str:
    return f"prediction:lock:{cache_key}"


async def release_prediction_lock(
    lock_key: str,
    task_id: str,
) -> None:
    await redis_client.eval(
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


async def close_redis_client() -> None:
    await redis_client.aclose()
