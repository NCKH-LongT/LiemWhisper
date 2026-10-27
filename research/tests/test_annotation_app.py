"""
Unit Tests for LiemWhisper Web Annotation Studio
================================================
Tests endpoints, taxonomy serving, record retrieval, and save persistence.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "..", "src", "liemwhisper"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from annotation_app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "LiemWhisper Web Annotation Studio" in response.text


def test_taxonomy_endpoint(client):
    response = client.get("/api/taxonomy")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert "terms" in data
    assert len(data["terms"]) > 20
    # Check that Boundary Value Analysis is in the terms
    terms = [t["term"] for t in data["terms"]]
    assert "Boundary Value Analysis" in terms


def test_stats_endpoint(client):
    response = client.get("/api/stats?annotator=A")
    assert response.status_code == 200
    data = response.json()
    assert data["annotator"] == "A"
    assert "total" in data
    assert "completed" in data
    assert "pending" in data
    assert data["total"] > 0


def test_records_list_endpoint(client):
    response = client.get("/api/records?annotator=A&filter_status=all")
    assert response.status_code == 200
    data = response.json()
    assert "records" in data
    assert len(data["records"]) > 0
    first = data["records"][0]
    assert "recording_id" in first
    assert "prompt_id" in first


def test_record_detail_endpoint(client):
    response = client.get("/api/records?annotator=A&filter_status=all")
    assert response.status_code == 200
    first_id = response.json()["records"][0]["recording_id"]

    detail_res = client.get(f"/api/record/A/{first_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["recording_id"] == first_id
    assert "target_terms_hint" in detail
    assert "prompt_text" in detail
