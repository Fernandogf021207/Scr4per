from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from ..db import get_sqlalchemy_session
from src.services.session_manager import SessionManager, ResourceExhaustedException
from src.utils.exceptions import AccountBannedException, NetworkException, SessionExpiredException


@dataclass
class PoolSession:
    account_id: int
    username: str
    storage_state: dict[str, Any]
    proxy_url: Optional[str] = None


@asynccontextmanager
async def checkout_pool_session(platform: str) -> AsyncIterator[PoolSession]:
    db = get_sqlalchemy_session()
    session_manager = SessionManager()
    account = None

    try:
        account = session_manager.checkout_account(platform, db)
        yield PoolSession(
            account_id=account.id,
            username=account.username,
            storage_state=account.storage_state,
            proxy_url=account.proxy_url,
        )
    except ResourceExhaustedException:
        raise
    except SessionExpiredException as exc:
        if account:
            session_manager.mark_as_suspended(account.id, db, reason=f"Session Expired: {exc.message}")
        raise
    except AccountBannedException as exc:
        if account:
            session_manager.mark_as_banned(account.id, db, reason=f"Account Banned: {exc.message}")
        raise
    except Exception as exc:
        if account:
            if isinstance(exc, NetworkException):
                session_manager.release_account(account.id, success=True, db=db)
            else:
                session_manager.release_account(account.id, success=False, db=db, error_message=str(exc))
        raise
    else:
        if account:
            session_manager.release_account(account.id, success=True, db=db)
    finally:
        db.close()