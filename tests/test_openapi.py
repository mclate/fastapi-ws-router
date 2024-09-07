from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_openapi(app: FastAPI, client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json() == app.openapi()
