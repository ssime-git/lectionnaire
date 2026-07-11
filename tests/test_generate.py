from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import generate  # noqa: E402

SECRETS = {
    "CLOUDFLARE_ACCOUNT_ID": "account-id",
    "CLOUDFLARE_AI_API_TOKEN": "token",
}


def _reponse_sse(lignes: list[str]) -> Mock:
    response = Mock()
    response.iter_lines.return_value = iter(lignes)
    response.raise_for_status.return_value = None
    return response


class WorkersAiCallTests(unittest.TestCase):
    def test_appel_envoie_messages_au_modele_workers_ai(self) -> None:
        response = _reponse_sse(
            ['data: {"response": "{\\"titre\\": "}',
             'data: {"response": "\\"Essai\\"}"}',
             "data: [DONE]"]
        )
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch("generate.requests.post", return_value=response) as post,
        ):
            self.assertEqual(generate._appel("system", "user"), '{"titre": "Essai"}')

        self.assertIn(
            "/accounts/account-id/ai/run/@cf/moonshotai/kimi-k2.6",
            post.call_args.args[0],
        )
        corps = post.call_args.kwargs["json"]
        self.assertEqual(
            corps["messages"],
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
        )
        self.assertEqual(corps["response_format"], {"type": "json_object"})
        self.assertEqual(corps["max_tokens"], 12000)
        self.assertEqual(corps["chat_template_kwargs"], {"thinking": False})
        self.assertTrue(corps["stream"])
        self.assertEqual(post.call_args.kwargs["timeout"], 300)
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertEqual(response.encoding, "utf-8")

    def test_appel_lit_le_dialecte_openai_de_kimi(self) -> None:
        response = _reponse_sse(
            ['data: {"choices": [{"delta": {"content": "{\\"titre\\": "}}]}',
             'data: {"choices": [{"delta": {"content": "\\"Kimi\\"}"}}]}',
             'data: {"choices": [{"delta": {}}]}',
             "data: [DONE]"]
        )
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch("generate.requests.post", return_value=response),
        ):
            self.assertEqual(generate._appel("system", "user"), '{"titre": "Kimi"}')

    def test_appel_refuse_secret_manquant(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CLOUDFLARE_ACCOUNT_ID"):
                generate._appel("system", "user")

        with patch.dict(
            os.environ, {"CLOUDFLARE_ACCOUNT_ID": "account-id"}, clear=True
        ):
            with self.assertRaisesRegex(RuntimeError, "CLOUDFLARE_AI_API_TOKEN"):
                generate._appel("system", "user")

    def test_appel_traduit_le_refus_http_de_l_api(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = generate.requests.HTTPError(
            "403 Client Error"
        )
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch("generate.requests.post", return_value=response),
        ):
            with self.assertRaisesRegex(RuntimeError, "Échec de l'appel Workers AI"):
                generate._appel("system", "user")

    def test_appel_explique_le_quota_epuise(self) -> None:
        reponse_http = Mock(status_code=429)
        erreur = generate.requests.HTTPError("429", response=reponse_http)
        response = Mock()
        response.raise_for_status.side_effect = erreur
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch("generate.requests.post", return_value=response),
        ):
            with self.assertRaisesRegex(RuntimeError, "Quota Workers AI épuisé"):
                generate._appel("system", "user")

    def test_appel_refuse_un_flux_vide(self) -> None:
        response = _reponse_sse(["data: [DONE]"])
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch("generate.requests.post", return_value=response),
        ):
            with self.assertRaisesRegex(RuntimeError, "aucun token"):
                generate._appel("system", "user")

    def test_appel_reessaie_une_fois_apres_timeout(self) -> None:
        response = _reponse_sse(
            ['data: {"response": "{\\"titre\\": \\"Essai\\"}"}', "data: [DONE]"]
        )
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch(
                "generate.requests.post",
                side_effect=[generate.requests.Timeout("lent"), response],
            ) as post,
        ):
            self.assertEqual(generate._appel("system", "user"), '{"titre": "Essai"}')
        self.assertEqual(post.call_count, 2)

    def test_appel_abandonne_apres_deux_timeouts(self) -> None:
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch(
                "generate.requests.post",
                side_effect=generate.requests.Timeout("toujours lent"),
            ) as post,
        ):
            with self.assertRaisesRegex(RuntimeError, "Échec de l'appel Workers AI"):
                generate._appel("system", "user")
        self.assertEqual(post.call_count, 2)


class LireFluxTests(unittest.TestCase):
    def test_ignore_les_lignes_non_sse_et_le_json_invalide(self) -> None:
        r = _reponse_sse(
            ["",
             ": commentaire",
             "data: pas-du-json",
             'data: {"response": "ok"}',
             "data: [DONE]",
             'data: {"response": "après done, jamais lu"}']
        )
        texte, echantillon = generate._lire_flux(r)
        self.assertEqual(texte, "ok")
        self.assertTrue(echantillon)


class GravureTests(unittest.TestCase):
    SVG_VALIDE = (
        '<svg viewBox="0 0 340 150" xmlns="http://www.w3.org/2000/svg" '
        'fill="none"><g class="trait-encre"><path d="M6 120 h328"/></g></svg>'
    )

    def test_accepte_un_svg_epure(self) -> None:
        self.assertTrue(generate._gravure_sure(self.SVG_VALIDE))

    def test_refuse_script_texte_mauvais_viewbox_et_liens(self) -> None:
        refusables = [
            "pas du svg",
            '<svg viewBox="0 0 100 100"><path d="M0 0"/></svg>',
            '<svg viewBox="0 0 340 150"><script>alert(1)</script></svg>',
            '<svg viewBox="0 0 340 150"><text>x</text></svg>',
            '<svg viewBox="0 0 340 150"><path d="M0 0" onclick="x()"/></svg>',
            '<svg viewBox="0 0 340 150"><path d="M0 0" href="http://x"/></svg>',
            '<svg viewBox="0 0 340 150"><path d="M0 0"',
        ]
        for svg in refusables:
            self.assertFalse(generate._gravure_sure(svg), svg[:60])

    def test_generer_gravure_retourne_le_svg_valide(self) -> None:
        reponse = f'{{"gravure_svg": {generate.json.dumps(self.SVG_VALIDE)}}}'
        with patch("generate._appel", return_value=reponse):
            self.assertEqual(generate._generer_gravure("une vigne"), self.SVG_VALIDE)

    def test_generer_gravure_retombe_sur_le_placeholder(self) -> None:
        cas = [
            patch("generate._appel", return_value='{"gravure_svg": "<svg>cassé"}'),
            patch("generate._appel", return_value="pas du json"),
            patch("generate._appel", side_effect=RuntimeError("api en panne")),
        ]
        for scenario in cas:
            with scenario:
                self.assertEqual(
                    generate._generer_gravure("une vigne"),
                    generate._GRAVURE_ABSENTE,
                )


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
