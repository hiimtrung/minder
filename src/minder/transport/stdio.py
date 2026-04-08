from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider
from minder.transport.base import BaseTransport


class StdioTransport(BaseTransport):
    transport_name = "stdio"

    def __init__(
        self,
        *,
        config: MinderConfig,
        auth_service: AuthService | None = None,
        cache_provider: ICacheProvider | None = None,
    ) -> None:
        super().__init__(config=config, auth_service=auth_service, cache_provider=cache_provider)
