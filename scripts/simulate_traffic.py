"""
Traffic simulation script for AgriCNXEdge Web API.
Uses httpx (installed in backend/.venv) or standard urllib to generate traffic across endpoints:
- GET /api/health (uptime / availability)
- GET /api/model/status
- POST /api/predict (uploads sample image or generated test payloads)
- Occasional rejected/error requests to populate error rate graphs in Grafana.
"""

import io
import random
import time
import argparse
from pathlib import Path
from PIL import Image
import httpx

def generate_dummy_image() -> bytes:
    # 512x512 RGB dummy image
    img = Image.new("RGB", (512, 512), color=(random.randint(40, 180), random.randint(100, 240), random.randint(30, 150)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic traffic to AgriCNXEdge API")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of API (default: http://localhost:8000)")
    parser.add_argument("--count", type=int, default=100, help="Number of requests to send (default: 100, 0 for infinite)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests in seconds (default: 0.5)")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print(f"🚀 Starting traffic generation targeting: {base_url}")
    print(f"📈 Sending {args.count if args.count > 0 else 'infinite'} requests with {args.delay}s delay...\n")

    sent = 0
    dummy_img = generate_dummy_image()

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        try:
            while args.count == 0 or sent < args.count:
                sent += 1
                dice = random.random()

                if dice < 0.40:
                    # 40% health check probes
                    try:
                        resp = client.get("/api/health")
                        print(f"[{sent:03d}] GET /api/health -> {resp.status_code}")
                    except Exception as e:
                        print(f"[{sent:03d}] GET /api/health -> ERROR: {e}")

                elif dice < 0.60:
                    # 20% model status probes
                    try:
                        resp = client.get("/api/model/status")
                        print(f"[{sent:03d}] GET /api/model/status -> {resp.status_code}")
                    except Exception as e:
                        print(f"[{sent:03d}] GET /api/model/status -> ERROR: {e}")

                elif dice < 0.90:
                    # 30% predict with valid image
                    try:
                        files = {"file": ("test_leaf.jpg", dummy_img, "image/jpeg")}
                        resp = client.post("/api/predict", files=files)
                        print(f"[{sent:03d}] POST /api/predict (JPEG) -> {resp.status_code}")
                    except Exception as e:
                        print(f"[{sent:03d}] POST /api/predict -> ERROR: {e}")

                else:
                    # 10% invalid request (e.g. text file instead of image) to simulate 415 rejection in Grafana
                    try:
                        files = {"file": ("bad_payload.txt", b"not-an-image", "text/plain")}
                        resp = client.post("/api/predict", files=files)
                        print(f"[{sent:03d}] POST /api/predict (415 check) -> {resp.status_code}")
                    except Exception as e:
                        print(f"[{sent:03d}] POST /api/predict (415 check) -> ERROR: {e}")

                time.sleep(args.delay)

        except KeyboardInterrupt:
            print("\n⏹️ Stopped traffic generation.")

    print(f"\n✅ Completed. Sent {sent} requests.")

if __name__ == "__main__":
    main()
