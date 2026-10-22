import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE_URL = "http://127.0.0.1:8002"
USER_ID = "selfheal_test_user"


def main():
    parser = argparse.ArgumentParser(description="Bounded self-healing platform load test")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds (1-120)")
    parser.add_argument("--rate", type=float, default=1.0, help="Requests per second (0.1-2)")
    args = parser.parse_args()

    if not 1 <= args.duration <= 120:
        parser.error("--duration must be between 1 and 120 seconds")
    if not 0.1 <= args.rate <= 2:
        parser.error("--rate must be between 0.1 and 2 requests per second")

    interval = 1.0 / args.rate
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    attempted = 0
    succeeded = 0
    failed = 0
    started = time.monotonic()
    deadline = started + args.duration

    print(f"Starting bounded load test: duration={args.duration}s, rate={args.rate}/s")
    print("Target: Order Service at", BASE_URL)

    while time.monotonic() < deadline:
        request_started = time.monotonic()
        attempted += 1
        payload = {
            "order_id": f"loadtest_{run_id}_{attempted:04d}",
            "user_id": USER_ID,
            "amount": 1.00,
            "currency": "USD",
        }
        request = urllib.request.Request(
            f"{BASE_URL}/orders",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace")
                if 200 <= response.status < 300:
                    succeeded += 1
                else:
                    failed += 1
                print(f"{attempted}: HTTP {response.status} - {body[:200]}")
        except urllib.error.HTTPError as exc:
            failed += 1
            body = exc.read().decode("utf-8", errors="replace")
            print(f"{attempted}: HTTP {exc.code} - {body[:200]}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            failed += 1
            print(f"{attempted}: request failed - {exc}")

        next_start = request_started + interval
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(max(0, next_start - time.monotonic()), remaining))

    elapsed = time.monotonic() - started
    print("\nLoad test summary")
    print(f"Attempted: {attempted}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed: {failed}")
    print(f"Elapsed seconds: {elapsed:.1f}")


if __name__ == "__main__":
    main()
