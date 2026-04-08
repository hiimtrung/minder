from contextvars import ContextVar
from typing import Optional

from minder.auth.principal import Principal
from minder.models.user import User

_current_user: ContextVar[Optional[User]] = ContextVar("current_user", default=None)
_current_principal: ContextVar[Optional[Principal]] = ContextVar("current_principal", default=None)

def set_current_user(user: Optional[User]) -> None:
    _current_user.set(user)

def get_current_user() -> Optional[User]:
    return _current_user.get()


def set_current_principal(principal: Optional[Principal]) -> None:
    _current_principal.set(principal)
    if principal is None or not hasattr(principal, "user"):
        _current_user.set(None)
    else:
        _current_user.set(getattr(principal, "user"))


def get_current_principal() -> Optional[Principal]:
    return _current_principal.get()
