from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.transport.base import BaseTransport


class SSETransport(BaseTransport):
    transport_name = "sse"

    def __init__(self, *, config: MinderConfig, auth_service: AuthService | None = None) -> None:
        super().__init__(config=config, auth_service=auth_service)
