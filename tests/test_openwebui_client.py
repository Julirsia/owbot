import unittest

from team_bot.openwebui_client import OpenWebUIClient


class OpenWebUIClientTests(unittest.TestCase):
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

    def test_extract_chat_message_content_reads_history_message(self) -> None:
        response = {
            "chat": {
                "history": {
                    "messages": {
                        "assistant-1": {
                            "id": "assistant-1",
                            "content": [{"type": "text", "text": "최종 응답"}],
                        }
                    }
                }
            }
        }

        self.assertEqual(
            OpenWebUIClient._extract_chat_message_content(response, "assistant-1"),
            "최종 응답",
        )

    def test_last_user_content_returns_latest_user_message(self) -> None:
        messages = [
            {"role": "system", "content": "시스템"},
            {"role": "user", "content": "첫 요청"},
            {"role": "assistant", "content": "중간 답변"},
            {"role": "user", "content": "마지막 요청"},
        ]

        self.assertEqual(OpenWebUIClient._last_user_content(messages), "마지막 요청")

    def test_inject_assistant_placeholder_updates_chat_history(self) -> None:
        response = {
            "chat": {
                "id": "chat-1",
                "history": {
                    "messages": {
                        "user-1": {
                            "id": "user-1",
                            "role": "user",
                            "content": "질문",
                            "childrenIds": [],
                        }
                    },
                    "currentId": "user-1",
                },
                "messages": [{"id": "user-1", "role": "user", "content": "질문"}],
            }
        }

        enriched = OpenWebUIClient._inject_assistant_placeholder(
            response,
            user_message_id="user-1",
            assistant_message_id="assistant-1",
            model_id="gpt-5-mini",
            timestamp=123,
        )

        self.assertEqual(enriched["history"]["currentId"], "assistant-1")
        self.assertEqual(enriched["history"]["current_id"], "assistant-1")
        self.assertIn("assistant-1", enriched["history"]["messages"])
        self.assertIn("assistant-1", enriched["history"]["messages"]["user-1"]["childrenIds"])

    def test_extract_completed_messages_reads_chat_messages(self) -> None:
        response = {
            "chat": {
                "messages": [
                    {"id": "user-1", "role": "user", "content": "질문"},
                    {"id": "assistant-1", "role": "assistant", "content": "답변"},
                ]
            }
        }

        self.assertEqual(
            OpenWebUIClient._extract_completed_messages(response),
            response["chat"]["messages"],
        )


if __name__ == "__main__":
    unittest.main()
