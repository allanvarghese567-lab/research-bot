"""
Research Bot FastAPI – optional instant trigger for research requests.

POST /requests/{id}/run  – verifies Supabase JWT, then fires a GitHub
                            repository_dispatch (or runs worker in background).
GET  /health             – simple health check.
"""
import os
from typing import Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

# ---------------------------------------------------------------- config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")  # JWT secret from Supabase
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")                 # PAT with repo scope
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

app = FastAPI(title="Research Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=True)


class RunResponse(BaseModel):
    ok: bool
    message: str
    request_id: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Validate Supabase JWT and return the payload."""
    token = credentials.credentials
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfigured: SUPABASE_JWT_SECRET missing",
        )
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


async def trigger_github_dispatch(request_id: str) -> bool:
    """Fire a repository_dispatch event so the GitHub Action can pick it up."""
    if not (GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO):
        return False
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "event_type": "research_request",
        "client_payload": {"request_id": request_id},
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers, timeout=15)
        return r.status_code in (200, 204)


async def verify_request_ownership(request_id: str, user_id: str) -> bool:
    """Check that the request belongs to the authenticated user (service key)."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        return False
    url = f"{SUPABASE_URL}/rest/v1/research_requests?id=eq.{request_id}&select=user_id"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return False
        data = r.json()
        if not data:
            return False
        return data[0].get("user_id") == user_id


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/requests/{request_id}/run", response_model=RunResponse)
async def run_request(
    request_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Instantly trigger processing of a research request.
    Verifies JWT + ownership, then fires GitHub repository_dispatch
    (preferred) or falls back to a no-op message if GitHub is not configured.
    """
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")

    owns = await verify_request_ownership(request_id, user_id)
    if not owns:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request not found or does not belong to you",
        )

    dispatched = await trigger_github_dispatch(request_id)
    if dispatched:
        return RunResponse(
            ok=True,
            message="Triggered via GitHub Actions",
            request_id=request_id,
        )

    return RunResponse(
        ok=True,
        message="Queued; worker will process on next cron (or configure GITHUB_TOKEN)",
        request_id=request_id,
    )
