import json
import time
from typing import Iterable, List
import websockets
from websockets.sync.client import ClientConnection


class WebsocketLogStream:
    def __init__(self, wss_url: str, address: str, topics: List[str]):
        self.wss_url = wss_url
        self.address = address
        self.topics = topics
        self.subscription_id: str | None = None

    def _subscribe(self, ws: ClientConnection) -> str:
        payload = {
            "id": 1,
            "method": "eth_subscribe",
            "params": ["logs", {"address": self.address, "topics": self.topics}],
        }
        ws.send(json.dumps(payload))
        response = json.loads(ws.recv())
        if "error" in response:
            raise RuntimeError(response["error"])
        self.subscription_id = response["result"]
        return self.subscription_id

    def stream(self) -> Iterable[dict]:
        while True:
            try:
                with websockets.sync.client.connect(self.wss_url, ping_interval=20, ping_timeout=20) as ws:
                    sub_id = self._subscribe(ws)
                    for raw in ws:
                        message = json.loads(raw)
                        if message.get("method") != "eth_subscription":
                            continue
                        params = message.get("params", {})
                        if params.get("subscription") != sub_id:
                            continue
                        result = params.get("result")
                        if result is not None:
                            yield result
            except Exception:
                time.sleep(3)
                continue
