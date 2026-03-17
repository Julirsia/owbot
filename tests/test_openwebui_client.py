import unittest

from team_bot.openwebui_client import OpenWebUIClient


class OpenWebUIClientTests(unittest.TestCase):
    def test_flush_sse_event_lines_joins_data_lines(self) -> None:
        lines = [
            "event: message",
            'data: {"choices": [',
            'data:   {"delta": {"content": "첫째"}}',
            "data: ]}",
        ]

        self.assertEqual(
            OpenWebUIClient._flush_sse_event_lines(lines),
            '{"choices": [\n{"delta": {"content": "첫째"}}\n]}',
        )

    def test_extract_message_content_reads_text_list(self) -> None:
        response = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "첫째"},
                            {"type": "output_text", "text": " 둘째"},
                        ]
                    }
                }
            ]
        }

        self.assertEqual(OpenWebUIClient.extract_message_content(response), "첫째 둘째")

    def test_extract_message_content_reads_nested_content_blocks(self) -> None:
        response = {
            "choices": [
                {
                    "message": {
                        "content": {
                            "type": "content",
                            "content": [{"type": "text", "text": "중첩 응답"}],
                        }
                    }
                }
            ]
        }

        self.assertEqual(OpenWebUIClient.extract_message_content(response), "중첩 응답")

    def test_extract_message_content_falls_back_to_tool_call_summary(self) -> None:
        response = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {"function": {"name": "list_tools"}},
                            {"function": {"name": "run_terminal_command"}},
                        ],
                    }
                }
            ]
        }

        self.assertIn("list_tools", OpenWebUIClient.extract_message_content(response))
        self.assertIn("run_terminal_command", OpenWebUIClient.extract_message_content(response))

    def test_extract_message_text_or_empty_reads_message_content(self) -> None:
        response = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "output_text", "text": "일반"},
                            {"type": "text", "text": " 응답"},
                        ]
                    }
                }
            ]
        }

        self.assertEqual(OpenWebUIClient._extract_message_text_or_empty(response), "일반 응답")

    def test_extract_tool_names_reads_delta_tool_calls(self) -> None:
        chunk = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"function": {"name": "run_terminal_command"}},
                            {"function": {"name": "read_file"}},
                        ]
                    }
                }
            ]
        }

        self.assertEqual(
            OpenWebUIClient._extract_tool_names(chunk),
            ["run_terminal_command", "read_file"],
        )

    def test_extract_stream_delta_text_reads_chunk_text(self) -> None:
        chunk = {
            "choices": [
                {
                    "delta": {
                        "content": [
                            {"type": "text", "text": "중간"},
                            {"type": "output_text", "text": " 응답"},
                        ]
                    }
                }
            ]
        }

        self.assertEqual(OpenWebUIClient._extract_stream_delta_text(chunk), "중간 응답")

    def test_extract_stream_message_text_reads_terminal_message(self) -> None:
        chunk = {
            "choices": [
                {
                    "message": {
                        "content": [{"type": "output_text", "text": "최종 응답"}],
                    }
                }
            ]
        }

        self.assertEqual(OpenWebUIClient._extract_stream_message_text(chunk), "최종 응답")

    def test_extract_event_completion_text_prefers_final_output_message(self) -> None:
        payload = {
            "done": True,
            "content": "<details type=\"reasoning\">중간 추론</details>\n최종 응답",
            "output": [
                {
                    "type": "reasoning",
                    "content": [{"type": "output_text", "text": "중간 추론"}],
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "최종 응답"}],
                },
            ],
        }

        self.assertEqual(
            OpenWebUIClient.extract_event_completion_text(payload),
            "최종 응답",
        )

    def test_extract_event_completion_text_strips_details_markup(self) -> None:
        payload = {
            "done": True,
            "content": (
                "<details type=\"reasoning\" done=\"true\">생각 중</details>\n"
                "<details type=\"tool_calls\" done=\"true\">도구 호출</details>\n"
                "정리된 답변"
            ),
        }

        self.assertEqual(
            OpenWebUIClient.extract_event_completion_text(payload),
            "정리된 답변",
        )


if __name__ == "__main__":
    unittest.main()
