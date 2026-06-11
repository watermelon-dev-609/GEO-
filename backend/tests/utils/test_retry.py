# test_retry.py — Unit tests for retry utilities

from __future__ import annotations
import sys, os, asyncio
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from app.utils.retry import async_retry, retry, RetryExhaustedError, is_retryable


class TestIsRetryable:
    def test_timeout_is_retryable(self):
        assert is_retryable(asyncio.TimeoutError()) is True
        assert is_retryable(TimeoutError()) is True

    def test_connection_error_is_retryable(self):
        assert is_retryable(ConnectionError("refused")) is True
        assert is_retryable(ConnectionRefusedError()) is True
        assert is_retryable(ConnectionResetError()) is True

    def test_os_error_is_retryable(self):
        assert is_retryable(OSError("io error")) is True

    def test_value_error_is_not_retryable(self):
        assert is_retryable(ValueError("bad value")) is False

    def test_keyword_match_makes_retryable(self):
        e = Exception("request timeout occurred")
        assert is_retryable(e) is True

    def test_rate_limit_keyword(self):
        e = Exception("rate limit exceeded")
        assert is_retryable(e) is True

    def test_service_unavailable_keyword(self):
        e = Exception("service unavailable")
        assert is_retryable(e) is True

    def test_no_keyword_match(self):
        e = Exception("something went wrong")
        assert is_retryable(e) is False


class TestSyncRetry:
    def test_decorator_success_first_try(self):
        call_count = [0]

        @retry(max_retries=2, delay=0.001)
        def succeed():
            call_count[0] += 1
            return "ok"

        result = succeed()
        assert result == "ok"
        assert call_count[0] == 1

    def test_decorator_retry_then_succeed(self):
        call_count = [0]

        @retry(max_retries=3, delay=0.001)
        def succeed_on_third():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("fail")
            return "ok"

        result = succeed_on_third()
        assert result == "ok"
        assert call_count[0] == 3

    def test_decorator_exhausted(self):
        @retry(max_retries=2, delay=0.001)
        def always_fails():
            raise ConnectionError("always down")

        with pytest.raises(RetryExhaustedError) as exc:
            always_fails()
        assert exc.value.attempts == 2

    def test_decorator_non_retryable_passes_through(self):
        @retry(max_retries=3, delay=0.001)
        def bad_value():
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            bad_value()


class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_success_first_try(self):
        call_count = [0]

        async def succeed():
            call_count[0] += 1
            return "async_ok"

        result = await async_retry(succeed, max_retries=2, delay=0.001)
        assert result == "async_ok"
        assert call_count[0] == 1

    @pytest.mark.asyncio
    async def test_retry_then_succeed(self):
        call_count = [0]

        async def succeed_on_second():
            call_count[0] += 1
            if call_count[0] < 2:
                raise asyncio.TimeoutError("timeout")
            return "async_ok"

        result = await async_retry(succeed_on_second, max_retries=2, delay=0.001)
        assert result == "async_ok"
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_exhausted(self):
        async def always_fails():
            raise ConnectionError("down")

        with pytest.raises(RetryExhaustedError) as exc:
            await async_retry(always_fails, max_retries=1, delay=0.001)
        assert exc.value.attempts == 1

    @pytest.mark.asyncio
    async def test_non_retryable(self):
        async def bad():
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await async_retry(bad, max_retries=3, delay=0.001)

    @pytest.mark.asyncio
    async def test_with_args(self):
        async def add(a, b):
            return a + b

        result = await async_retry(add, 3, 4, max_retries=1, delay=0.001)
        assert result == 7


class TestRetryExhaustedError:
    def test_str_contains_attempts(self):
        inner = ConnectionError("test")
        err = RetryExhaustedError(inner, 5)
        assert "5" in str(err)
        assert err.last_error is inner
        assert err.attempts == 5
