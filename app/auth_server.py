"""Minimal FastAPI server that handles the Zerodha OAuth callback."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.kite.auth import _auth

app = FastAPI(title="Kite Auth Callback")


@app.get("/callback")
def callback(request_token: str = "", status: str = "", type: str = ""):
    if status != "success" or not request_token:
        return HTMLResponse("<h2>Login failed or cancelled.</h2>", status_code=400)
    try:
        _auth.exchange_request_token(request_token)
        return HTMLResponse(
            "<h2 style='font-family:monospace;color:#10b981'>✅ Zerodha login successful!"
            " You can close this tab and return to the dashboard.</h2>"
        )
    except Exception as exc:
        return HTMLResponse(f"<h2>Error: {exc}</h2>", status_code=500)


@app.get("/health")
def health():
    return {"ok": True}
