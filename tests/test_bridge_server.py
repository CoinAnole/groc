from __future__ import annotations

import io
import json
import unittest
from email.message import Message

from groc.bridge.server import BridgeHandler, relay_responses_stream
from groc.errors import BridgeError


class BridgeServerTests(unittest.TestCase):
    def handler_with_body(self, body: bytes, content_length: str | None = None) -> BridgeHandler:
        handler = object.__new__(BridgeHandler)
        headers = Message()
        headers["content-length"] = str(len(body)) if content_length is None else content_length
        handler.headers = headers
        handler.rfile = io.BytesIO(body)
        return handler

    def test_read_json_accepts_object_body(self) -> None:
        handler = self.handler_with_body(b'{"model":"gpt-5.5"}')

        self.assertEqual(handler.read_json(), {"model": "gpt-5.5"})

    def test_read_json_rejects_bad_content_length_as_client_error(self) -> None:
        handler = self.handler_with_body(b"{}", content_length="bad")

        with self.assertRaises(BridgeError) as raised:
            handler.read_json()

        self.assertEqual(raised.exception.status, 400)

    def test_read_json_rejects_invalid_json_as_client_error(self) -> None:
        handler = self.handler_with_body(b"{")

        with self.assertRaises(BridgeError) as raised:
            handler.read_json()

        self.assertEqual(raised.exception.status, 400)

    def test_read_json_rejects_non_object_json_as_client_error(self) -> None:
        handler = self.handler_with_body(b'["not", "an", "object"]')

        with self.assertRaises(BridgeError) as raised:
            handler.read_json()

        self.assertEqual(raised.exception.status, 400)

    def test_stream_relay_preserves_reasoning_items_in_completed_response(self) -> None:
        reasoning_item = {"type": "reasoning", "encrypted_content": "encrypted-reasoning"}
        events = [
            {"type": "response.output_item.done", "item": reasoning_item},
            {"type": "response.completed", "response": {"id": "resp_1", "output": []}},
        ]
        source = io.BytesIO(
            b"".join(b"data: " + json.dumps(event).encode("utf-8") + b"\n\n" for event in events)
        )
        destination = io.BytesIO()

        relay_responses_stream(source, destination)

        relayed = [
            json.loads(line.removeprefix(b"data: "))
            for line in destination.getvalue().splitlines()
            if line.startswith(b"data: ")
        ]
        self.assertEqual(relayed[-1]["response"]["output"], [reasoning_item])


if __name__ == "__main__":
    unittest.main()
