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
            "/accounts/account-id/ai/run/@cf/moonshotai/kimi-k2.6",
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
        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 12000)
        self.assertEqual(post.call_args.kwargs["timeout"], 300)

    def test_appel_lit_le_format_openai_de_kimi(self) -> None:
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "id": "x",
                "object": "chat.completion",
                "choices": [
                    {"message": {"role": "assistant", "content": '{"titre": "Kimi"}'}}
                ],
                "usage": {},
            },
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
            patch("generate.requests.post", return_value=response),
        ):
            self.assertEqual(generate._appel("system", "user"), '{"titre": "Kimi"}')

    def test_appel_reessaie_une_fois_apres_timeout(self) -> None:
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
            patch(
                "generate.requests.post",
                side_effect=[generate.requests.Timeout("lent"), response],
            ) as post,
        ):
            self.assertEqual(generate._appel("system", "user"), '{"titre": "Essai"}')
        self.assertEqual(post.call_count, 2)

    def test_appel_abandonne_apres_deux_timeouts(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "CLOUDFLARE_ACCOUNT_ID": "account-id",
                    "CLOUDFLARE_AI_API_TOKEN": "token",
                },
                clear=True,
            ),
            patch(
                "generate.requests.post",
                side_effect=generate.requests.Timeout("toujours lent"),
            ) as post,
        ):
            with self.assertRaisesRegex(RuntimeError, "Échec de l'appel Workers AI"):
                generate._appel("system", "user")
        self.assertEqual(post.call_count, 2)

    def test_appel_refuse_secret_manquant(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CLOUDFLARE_ACCOUNT_ID"):
                generate._appel("system", "user")

        with patch.dict(
            os.environ, {"CLOUDFLARE_ACCOUNT_ID": "account-id"}, clear=True
        ):
            with self.assertRaisesRegex(RuntimeError, "CLOUDFLARE_AI_API_TOKEN"):
                generate._appel("system", "user")

    def test_appel_traduit_le_refus_de_l_api(self) -> None:
        response = Mock()
        response.json.return_value = {
            "success": False,
            "errors": [{"code": 7000, "message": "No route"}],
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
            patch("generate.requests.post", return_value=response),
        ):
            with self.assertRaisesRegex(RuntimeError, "refusé"):
                generate._appel("system", "user")

    def test_appel_refuse_une_reponse_sans_texte(self) -> None:
        for resultat in ({}, {"response": ""}, {"response": None}, None):
            response = Mock()
            response.json.return_value = {"success": True, "result": resultat}
            with (
                patch.dict(
                    os.environ,
                    {
                        "CLOUDFLARE_ACCOUNT_ID": "account-id",
                        "CLOUDFLARE_AI_API_TOKEN": "token",
                    },
                    clear=True,
                ),
                patch("generate.requests.post", return_value=response),
            ):
                with self.assertRaisesRegex(RuntimeError, "texte exploitable"):
                    generate._appel("system", "user")

    def test_appel_traduit_l_erreur_reseau(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "CLOUDFLARE_ACCOUNT_ID": "account-id",
                    "CLOUDFLARE_AI_API_TOKEN": "token",
                },
                clear=True,
            ),
            patch(
                "generate.requests.post",
                side_effect=generate.requests.ConnectionError("réseau coupé"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Échec de l'appel Workers AI"):
                generate._appel("system", "user")


class JsonPropreTests(unittest.TestCase):
    def test_json_propre_retire_les_clotures_markdown(self) -> None:
        brut = '```json\n{"titre": "Essai"}\n```'
        self.assertEqual(generate._json_propre(brut), {"titre": "Essai"})

    def test_json_propre_accepte_le_json_nu(self) -> None:
        self.assertEqual(generate._json_propre('{"a": 1}'), {"a": 1})


class ContratTests(unittest.TestCase):
    def test_cles_manquantes_detecte_les_trous(self) -> None:
        contrat = {cle: "x" for cle in generate.CLES_REQUISES}
        self.assertEqual(generate._cles_manquantes(contrat), [])
        del contrat["titre"]
        del contrat["analogie"]
        self.assertEqual(generate._cles_manquantes(contrat), ["analogie", "titre"])


if __name__ == "__main__":
    unittest.main()
