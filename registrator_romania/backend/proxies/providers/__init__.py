from registrator_romania.backend.proxies.providers import (
    server_proxies,
    residental_proxies,
)

providers = tuple(server_proxies.__all__ + residental_proxies.__all__)


__all__ = server_proxies.__all__ + residental_proxies.__all__
