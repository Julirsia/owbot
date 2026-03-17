import unittest

from team_bot.context_builder import (
    build_invocation_context,
    message_invokes_bot,
    message_mentions_bot,
    replace_mentions,
    strip_bot_mention,
)


class ContextBuilderTests(unittest.TestCase):
    def test_message_mentions_bot_detects_user_mention(self) -> None:
        content = "안녕 <@U:user-123|TEAM-BOT> 이거 봐줘"
        self.assertTrue(message_mentions_bot(content, "user-123"))
        self.assertFalse(message_mentions_bot(content, "other-user"))

    def test_message_invokes_bot_accepts_plain_display_name(self) -> None:
        self.assertTrue(message_invokes_bot("@TEAM-BOT 확인해줘", "user-123", "TEAM-BOT"))
        self.assertTrue(message_invokes_bot(" @팀봇 부탁해", "user-123", "팀봇"))
        self.assertFalse(message_invokes_bot("@OTHER-BOT 확인해줘", "user-123", "TEAM-BOT"))

    def test_strip_bot_mention_preserves_other_text(self) -> None:
        content = "안녕 <@U:user-123|TEAM-BOT> 이거 봐줘"
        self.assertEqual(strip_bot_mention(content, "user-123"), "안녕 이거 봐줘")

    def test_replace_mentions_uses_labels(self) -> None:
        content = "<@U:user-1|Alice> <@M:model-1|GPT> <@C:chan-1|general>"
        self.assertEqual(replace_mentions(content), "Alice GPT general")

    def test_build_invocation_context_orders_messages(self) -> None:
        invocation = {
            "id": "m3",
            "content": "<@U:user-123|TEAM-BOT> 정리해줘",
            "created_at": 30,
            "user": {"name": "Bob"},
        }
        recent = [
            {"id": "m2", "content": "두 번째", "created_at": 20, "user": {"name": "Alice"}},
            {"id": "m1", "content": "첫 번째", "created_at": 10, "user": {"name": "Bob"}},
            invocation,
        ]

        context = build_invocation_context(
            invocation_message=invocation,
            recent_channel_messages=recent,
            thread_root_message=None,
            thread_messages=[],
            bot_user_id="user-123",
        )

        self.assertEqual(
            context.channel_lines,
            ["Bob: 첫 번째", "Alice: 두 번째", "Bob: TEAM-BOT 정리해줘"],
        )
        self.assertIn("사용자 요청:\n정리해줘", context.prompt)


if __name__ == "__main__":
    unittest.main()
