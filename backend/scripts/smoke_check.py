from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def main() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200, f"Unexpected status: {response.status_code}"
    assert response.json().get("status") == "ok", "Health response missing ok status"
    print("Smoke check passed: /health responds with status=ok")


if __name__ == "__main__":
    main()
