from fastapi.testclient import TestClient

from app.main import app


class DummyInference:
    loaded = True

    def status(self):
        return {"loaded": True, "model_path": "models/test.onnx", "inputs": ["image"], "outputs": ["leaf_logits"]}

    def predict(self, content, filename):
        return {
            "filename": filename,
            "latency_ms": 12.34,
            "leaf": {"label": "healthy", "confidence": 0.99, "scores": {"healthy": 0.99}},
            "pest": {"label": "none", "confidence": 0.98, "scores": {"none": 0.98}},
            "fruit": {"label": "apple", "apple_predictions": []},
            "yield_detection": {"apple_count": 0, "boxes": [], "tensor_shape": []},
            "raw_output_names": ["leaf_logits"],
        }


def test_model_status_and_http_metrics_are_exposed():
    client = TestClient(app)

    health_response = client.get("/api/health")
    assert health_response.status_code == 200

    status_response = client.get("/api/model/status")
    assert status_response.status_code == 200
    assert status_response.json()["loaded"] in (True, False)

    metrics_response = client.get("/api/metrics")
    assert metrics_response.status_code == 200
    metrics_text = metrics_response.text
    assert "agricnxedge_http_requests_total" in metrics_text
    assert "agricnxedge_http_errors_total" in metrics_text
    assert "agricnxedge_model_loaded" in metrics_text


def test_predict_accepts_valid_image_and_rejects_invalid_type():
    client = TestClient(app)
    app.state.inference = DummyInference()

    valid_payload = b"fake-image-data"
    valid_response = client.post(
        "/api/predict",
        files={"file": ("test_apple.jpg", valid_payload, "image/jpeg")},
    )
    assert valid_response.status_code == 200
    assert valid_response.json()["filename"] == "test_apple.jpg"

    invalid_response = client.post(
        "/api/predict",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert invalid_response.status_code == 415
    assert "JPEG, PNG, or WEBP" in invalid_response.json()["detail"]


def test_malformed_predict_request_is_rejected():
    client = TestClient(app)
    response = client.post("/api/predict", data={})
    assert response.status_code == 422
