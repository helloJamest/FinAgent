# -*- coding: utf-8 -*-
"""Regression tests for API error response sanitization."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers


def test_http_500_detail_does_not_leak_exception_text():
    app = FastAPI()
    add_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "secret path C:/prod/.env token=sk-test",
            },
        )

    response = TestClient(app).get("/boom")

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "internal_error"
    assert payload.get("detail") is None
    assert "secret path" not in response.text
    assert "sk-test" not in response.text
