from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import generate  # noqa: E402


class WorkersAiCallTests(unittest.TestCase):
    def test_appel_envoie_messages_au_modele_workers_ai(self) -> None:
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {"response": '{"titre": "Essai"}'},
        }

        with (
            patch.dict(
                os.environ,
                {
                    "CLOUDFLARE_ACCOUNT_ID": "account-id",
                    "CLOUDFLARE_AI_API_TOKEN": "token",
                },
                clear=True,
            ),
            patch("generate.requests.post", return_value=response) as post,
        ):
            self.assertEqual(generate._appel("system", "user"), '{"titre": "Essai"}')

        self.assertIn(
            "/accounts/account-id/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            post.call_args.args[0],
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["messages"],
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["response_format"],
            {"type": "json_object"},
        )
        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 6000)


if __name__ == "__main__":
    unittest.main()
