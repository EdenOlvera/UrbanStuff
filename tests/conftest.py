import os, tempfile

os.environ["UMEP_DATA_DIR"] = tempfile.mkdtemp(prefix="umep-tests-")
import pytest
from fastapi.testclient import TestClient
from backend.api import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def project(client):
    return client.post("/api/projects", json={"name": "Test district"}).json()
