from __future__ import annotations

import io
import json
import unittest

from groc.bridge.wire import groc_wire_body, normalize_content, response_from_sse, responses_input_from_chat


class WireTests(unittest.TestCase):
    def test_normalize_content_accepts_common_message_shapes(self) -> None:
        self.assertEqual(normalize_content("hello"), "hello")
        self.assertEqual(normalize_content([{"text": "hello"}, {"content": "world"}]), "hello\nworld")
        self.assertEqual(normalize_content(None), "")

    def test_chat_messages_become_response_input(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": [{"text": "hello"}]},
            ]
        }

        self.assertEqual(
            responses_input_from_chat(body),
            [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hello"}],
        )

    def test_groc_wire_body_preserves_current_reasoning_fields(self) -> None:
        body = {
            "model": "gpt-5.6-sol",
            "instructions": "base",
            "input": [
                {"type": "message", "role": "developer", "content": "internal rules"},
                {"type": "message", "role": "user", "content": "work"},
            ],
            "reasoning": {"effort": "high", "summary": "auto", "context": "all_turns"},
        }

        converted = groc_wire_body(
            body,
            default_model="gpt-5.6-sol",
            upstream_model=lambda model: model,
        )

        self.assertEqual(converted["model"], "gpt-5.6-sol")
        self.assertEqual(converted["instructions"], "base\n\ninternal rules")
        self.assertEqual(converted["input"], [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "work"}]}])
        self.assertEqual(converted["reasoning"], body["reasoning"])
        self.assertEqual(converted["include"], ["reasoning.encrypted_content"])

    def test_groc_wire_body_forwards_sampling_fields_and_deduplicates_include(self) -> None:
        body = {
            "input": "work",
            "include": ["web_search_call.action.sources", "reasoning.encrypted_content", "web_search_call.action.sources"],
            "max_output_tokens": 0,
            "temperature": 0,
            "top_p": 0,
        }

        converted = groc_wire_body(body, "gpt-5.6-sol", lambda model: model)

        self.assertEqual(
            converted["include"],
            ["web_search_call.action.sources", "reasoning.encrypted_content"],
        )
        self.assertEqual(converted["max_output_tokens"], 0)
        self.assertEqual(converted["temperature"], 0)
        self.assertEqual(converted["top_p"], 0)

    def test_response_from_sse_collects_deltas_until_completion(self) -> None:
        events = [
            {
                "type": "response.output_item.done",
                "item": {"type": "reasoning", "encrypted_content": "encrypted-reasoning"},
            },
            {"type": "response.output_text.delta", "delta": "gro"},
            {"type": "response.output_text.delta", "delta": "c"},
            {"type": "response.completed", "response": {"id": "resp_1", "output": []}},
        ]
        stream = io.BytesIO(b"".join(b"data: " + json.dumps(event).encode("utf-8") + b"\n\n" for event in events))

        response = response_from_sse(stream)

        self.assertEqual(response["id"], "resp_1")
        self.assertEqual(response["output_text"], "groc")
        self.assertEqual(
            response["output"],
            [{"type": "reasoning", "encrypted_content": "encrypted-reasoning"}],
        )


if __name__ == "__main__":
    unittest.main()
