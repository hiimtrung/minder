from contextvars import ContextVar
from typing import Optional
from minder.models.user import User

_current_user: ContextVar[Optional[User]] = ContextVar("current_user", default=None)

def set_current_user(user: Optional[User]) -> None:
    _current_user.set(user)

def get_current_user() -> Optional[User]:
    return _current_user.get()
