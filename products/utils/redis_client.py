from typing import Optional

import redis
from django.conf import settings

_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        _client = redis.Redis.from_url(redis_url, decode_responses=True)
    return _client

