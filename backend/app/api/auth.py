"""鉴权API路由"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.models.schemas import AuthLoginRequest, AuthStatusResponse
from app.core.auth import (
    get_session_manager, hash_password, verify_password,
    is_auth_enabled, get_stored_password_hash,
)

router = APIRouter()
security = HTTPBearer(auto_error=False)


def auth_required(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    """鉴权依赖 — auth.enabled=true 时校验 Bearer token"""
    if not is_auth_enabled():
        return True
    if not credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    if not get_session_manager().validate(credentials.credentials):
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return True


@router.post("/login")
async def login(req: AuthLoginRequest):
    """登录"""
    if not is_auth_enabled():
        return {"status": "ok", "message": "鉴权未启用，无需登录", "token": ""}

    stored_hash = get_stored_password_hash()
    if not stored_hash:
        raise HTTPException(status_code=500, detail="系统未配置密码，请在 settings.yaml 的 auth.password_hash 中设置")

    if not verify_password(req.password, stored_hash):
        raise HTTPException(status_code=401, detail="密码错误")

    token = get_session_manager().create()
    return {"status": "ok", "token": token, "message": "登录成功"}


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    """登出"""
    if credentials:
        get_session_manager().revoke(credentials.credentials)
    return {"status": "ok", "message": "已登出"}


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    """鉴权状态"""
    enabled = is_auth_enabled()
    authenticated = True
    expires_at = ""
    if enabled:
        if not credentials:
            authenticated = False
        else:
            authenticated = get_session_manager().validate(credentials.credentials)
            if authenticated:
                from app.core.auth import _session_manager
                if _session_manager:
                    session = _session_manager._sessions.get(credentials.credentials, {})
                    created = session.get("created_at", 0)
                    import time
                    ttl = _session_manager._ttl
                    expires_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created + ttl))
    return AuthStatusResponse(
        authenticated=authenticated,
        auth_enabled=enabled,
        session_expires_at=expires_at,
    )
