
import aiohttp
import orjson


class AiohttpSession:
    def generate_connector(self):
        return aiohttp.TCPConnector(
            limit=0,
            limit_per_host=0,
        )

    def generate(
        self,
        connector: aiohttp.TCPConnector = None,
        close_connector: bool = False,
        total_timeout: int = 5,
    ):
        if connector is None:
            connector = self.generate_connector()

        timeout = aiohttp.ClientTimeout(connect=total_timeout)
        session = aiohttp.ClientSession(
            trust_env=True,
            connector=connector,
            json_serialize=orjson.dumps,
            connector_owner=close_connector,
            timeout=timeout,
        )
        return session
