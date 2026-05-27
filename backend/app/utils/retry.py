"""接口超时重试与异常容错"""

import asyncio
import functools
import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExhaustedError(Exception):
    """重试次数耗尽异常"""

    def __init__(self, last_error: Exception, attempts: int):
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(f"重试{attempts}次后仍失败: {last_error}")


RETRYABLE_EXCEPTIONS = (
    asyncio.TimeoutError,
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    TimeoutError,
    OSError,
)


def is_retryable(exception: Exception) -> bool:
    """判断异常是否可重试"""
    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        return True
    msg = str(exception).lower()
    retryable_keywords = [
        "timeout", "rate limit", "too many requests",
        "service unavailable", "internal server error",
        "bad gateway", "gateway timeout", "connection",
        "throttle", "capacity", "overloaded",
    ]
    return any(kw in msg for kw in retryable_keywords)


async def async_retry(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    **kwargs,
) -> T:
    """异步重试装饰器，支持指数退避"""
    last_error = None
    current_delay = delay

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt >= max_retries:
                break
            if not is_retryable(e):
                raise

            logger.warning(
                f"第{attempt + 1}次尝试失败（{e}），{current_delay:.1f}秒后重试..."
            )
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * backoff, 60)

    raise RetryExhaustedError(last_error, max_retries)


def retry(
    max_retries: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
):
    """同步重试装饰器"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt >= max_retries:
                        break
                    if not is_retryable(e):
                        raise
                    import time
                    logger.warning(
                        f"第{attempt + 1}次尝试失败（{e}），{current_delay:.1f}秒后重试..."
                    )
                    time.sleep(current_delay)
                    current_delay = min(current_delay * backoff, 60)
            raise RetryExhaustedError(last_error, max_retries)
        return wrapper
    return decorator
