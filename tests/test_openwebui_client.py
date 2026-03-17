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


if __name__ == "__main__":
    unittest.main()
