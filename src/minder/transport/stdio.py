import os

from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IOperationalStore
from minder.transport.base import BaseTransport


class StdioTransport(BaseTransport):
    transport_name = "stdio"

    def __init__(
        self,
        *,
        config: MinderConfig,
        store: IOperationalStore | None = None,
        auth_service: AuthService | None = None,
        cache_provider: ICacheProvider | None = None,
    ) -> None:
        super().__init__(
            config=config, 
            auth_service=auth_service, 
            cache_provider=cache_provider,
            store=store,
        )

    def _default_client_key(self) -> str | None:
        client_key = os.getenv("MINDER_CLIENT_API_KEY", "").strip()
        return client_key or None
