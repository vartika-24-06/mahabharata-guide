"""
Task 10 test: per-visitor rate limiting.

Run with: python -m pytest tests/test_rate_limit.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import rate_limit


def test_allows_up_to_the_limit():
    rate_limit._request_log.clear()
    ip = "test-ip-1"
    t0 = 1000.0
    for i in range(rate_limit.REQUESTS_PER_WINDOW):
        allowed, _ = rate_limit.check_rate_limit(ip, now=t0 + i * 0.01)
        assert allowed, f"Request {i} should be allowed (limit is {rate_limit.REQUESTS_PER_WINDOW})"


def test_blocks_over_the_limit():
    rate_limit._request_log.clear()
    ip = "test-ip-2"
    t0 = 1000.0
    for i in range(rate_limit.REQUESTS_PER_WINDOW):
        rate_limit.check_rate_limit(ip, now=t0 + i * 0.01)
    allowed, message = rate_limit.check_rate_limit(ip, now=t0 + 1.0)
    assert not allowed
    assert "wait" in message.lower()


def test_allows_again_after_window_passes():
    rate_limit._request_log.clear()
    ip = "test-ip-3"
    t0 = 1000.0
    for i in range(rate_limit.REQUESTS_PER_WINDOW):
        rate_limit.check_rate_limit(ip, now=t0 + i * 0.01)
    allowed, _ = rate_limit.check_rate_limit(ip, now=t0 + rate_limit.WINDOW_SECONDS + 1)
    assert allowed


def test_ips_are_independent():
    rate_limit._request_log.clear()
    t0 = 1000.0
    ip_a = "test-ip-a"
    ip_b = "test-ip-b"
    for i in range(rate_limit.REQUESTS_PER_WINDOW):
        rate_limit.check_rate_limit(ip_a, now=t0 + i * 0.01)
    allowed, _ = rate_limit.check_rate_limit(ip_b, now=t0)
    assert allowed, "A different visitor's IP should have its own independent count"


if __name__ == "__main__":
    test_allows_up_to_the_limit()
    test_blocks_over_the_limit()
    test_allows_again_after_window_passes()
    test_ips_are_independent()
    print("All rate limit tests passed.")
