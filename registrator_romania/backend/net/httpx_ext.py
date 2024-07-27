from ssl import SSLCertVerificationError
import ssl
import httpx


HTTPX_NET_ERRORS = (
    httpx._exceptions.ProxyError,
    httpx._exceptions.ConnectError,
    httpx._exceptions.ReadTimeout,
    httpx._exceptions.TimeoutException,
    httpx._exceptions.ConnectError,
    SSLCertVerificationError,
    httpx._exceptions.RemoteProtocolError,
    ssl.SSLError,
)