from __future__ import annotations

from minder import server


def test_server_reexports_bootstrap_and_presentation_builders() -> None:
    assert server.build_store.__module__ == "minder.bootstrap.providers"
    assert server.build_cache.__module__ == "minder.bootstrap.providers"
    assert server.build_vector_store.__module__ == "minder.bootstrap.providers"
    assert server.build_transport.__module__ == "minder.bootstrap.transport"
    assert server.build_http_routes.__module__ == "minder.presentation.http.admin.routes"
    assert server.build_http_app.__module__ == "minder.presentation.http.admin.routes"
