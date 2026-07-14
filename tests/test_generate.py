from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import generate  # noqa: E402
import valider  # noqa: E402

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

    def test_appel_reessaie_puis_explique_le_429(self) -> None:
        reponse_http = Mock(status_code=429, text='{"errors": ["capacity"]}')
        erreur = generate.requests.HTTPError("429", response=reponse_http)
        response = Mock()
        response.raise_for_status.side_effect = erreur
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch("generate.requests.post", return_value=response) as post,
            patch("generate.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "429 après plusieurs"):
                generate._appel("system", "user")
        self.assertEqual(post.call_count, 4)
        self.assertEqual(sleep.call_count, 4)

    def test_appel_se_remet_d_un_429_passager(self) -> None:
        reponse_http = Mock(status_code=429, text="capacity")
        erreur = generate.requests.HTTPError("429", response=reponse_http)
        rate_limited = Mock()
        rate_limited.raise_for_status.side_effect = erreur
        ok = _reponse_sse(
            ['data: {"response": "{\\"titre\\": \\"Essai\\"}"}', "data: [DONE]"]
        )
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch("generate.requests.post", side_effect=[rate_limited, ok]) as post,
            patch("generate.time.sleep"),
        ):
            self.assertEqual(generate._appel("system", "user"), '{"titre": "Essai"}')
        self.assertEqual(post.call_count, 2)

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

    def test_appel_abandonne_apres_quatre_timeouts(self) -> None:
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch(
                "generate.requests.post",
                side_effect=generate.requests.Timeout("toujours lent"),
            ) as post,
        ):
            with self.assertRaisesRegex(RuntimeError, "Échec de l'appel Workers AI"):
                generate._appel("system", "user")
        self.assertEqual(post.call_count, 4)


class ClaudeFallbackTests(unittest.TestCase):
    SECRETS_CLAUDE = {**SECRETS, "LECTIONNAIRE_MOTEUR": "claude"}

    def test_appel_bascule_sur_claude_selon_l_environnement(self) -> None:
        resultat = Mock(returncode=0, stdout='{"titre": "Sonnet"}', stderr="")
        with (
            patch.dict(os.environ, self.SECRETS_CLAUDE, clear=True),
            patch("generate.subprocess.run", return_value=resultat) as run,
            patch("generate.requests.post") as post,
        ):
            self.assertEqual(generate._appel("système", "user"), '{"titre": "Sonnet"}')
        post.assert_not_called()
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[0], "claude")
        self.assertIn("-p", cmd)
        self.assertIn("claude-sonnet-5", cmd)
        self.assertIn("système", cmd)
        self.assertEqual(run.call_args.kwargs["input"], "user")

    def test_appel_claude_traduit_un_echec_du_cli(self) -> None:
        resultat = Mock(returncode=1, stdout="", stderr="Invalid OAuth token")
        with (
            patch.dict(os.environ, self.SECRETS_CLAUDE, clear=True),
            patch("generate.subprocess.run", return_value=resultat),
        ):
            with self.assertRaisesRegex(RuntimeError, "Invalid OAuth token"):
                generate._appel("système", "user")

    def test_appel_claude_refuse_une_sortie_vide(self) -> None:
        resultat = Mock(returncode=0, stdout="   ", stderr="")
        with (
            patch.dict(os.environ, self.SECRETS_CLAUDE, clear=True),
            patch("generate.subprocess.run", return_value=resultat),
        ):
            with self.assertRaisesRegex(RuntimeError, "aucun texte"):
                generate._appel("système", "user")

    def test_le_moteur_workers_ai_reste_le_defaut(self) -> None:
        response = _reponse_sse(
            ['data: {"response": "{\\"titre\\": \\"Kimi\\"}"}', "data: [DONE]"]
        )
        with (
            patch.dict(os.environ, SECRETS, clear=True),
            patch("generate.requests.post", return_value=response),
            patch("generate.subprocess.run") as run,
        ):
            self.assertEqual(generate._appel("système", "user"), '{"titre": "Kimi"}')
        run.assert_not_called()


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


def _contrat_valide() -> dict:
    """Le plus petit contrat qui passe valider.valider_contrat sans faute."""
    return {
        "date": "2026-07-15",
        "date_humaine": "mercredi 15 juillet 2026",
        "semaine": "15e semaine du Temps Ordinaire",
        "ferie": "férie",
        "deuterocanonique": False,
        "liturgie": {"nom": "vert", "hex": "#2f6f4f", "hex_sombre": "#8fc9a8"},
        "titre": "Essai",
        "titre_html": 'Essai <span class="it">simple</span>',
        "sous_titre": "Un sous-titre",
        "traduction_globale": "Louis Segond 1910",
        "references_brutes": [],
        "gravure_alt": "une vigne",
        "gravure_svg": generate._GRAVURE_ABSENTE,
        "lectures": [{
            "reference": "Mt 11, 25-27",
            "classe": "evangile",
            "corps_html": '<p><button class="mot" data-g="g-loue">loue</button></p>',
            "gloses": [{"id": "g-loue", "lemme": "loue", "html": "Une glose."}],
        }],
        "contexte": [
            {"titre": "a", "corps_html": "b"},
            {"titre": "c", "corps_html": "d"},
        ],
        "analogie": {"titre": "t", "variantes": ["a", "b", "c"], "choisi": 0},
        "invitation": {"intro": "i", "geste": "g", "note": "n"},
        "question": "Une question ?",
        "racines": [
            {"titre": "r1", "corps_html": "c", "attribution": "Calvin"},
            {"titre": "r2", "corps_html": "c", "attribution": "Chrysostome"},
            {"titre": "r3", "corps_html": "c", "attribution": "Augustin"},
        ],
    }


class NormaliserClassesTests(unittest.TestCase):
    def test_normalise_les_classes_accentuees_ou_majuscules(self) -> None:
        contenu = {"lectures": [
            {"classe": "évangile"},
            {"classe": "Psaume "},
            {"classe": "psaume"},
            {"classe": "inconnu"},
        ]}
        generate._normaliser_classes(contenu)
        self.assertEqual(
            [lec["classe"] for lec in contenu["lectures"]],
            ["evangile", "psaume", "psaume", "inconnu"],
        )


class ReparerTests(unittest.TestCase):
    def _casser(self, contrat: dict) -> dict:
        contrat["lectures"][0]["corps_html"] = "<p>loue</p>"  # glose orpheline
        return contrat

    def test_le_contrat_valide_de_reference_est_bien_valide(self) -> None:
        self.assertEqual(valider.valider_contrat(_contrat_valide()), [])

    def test_reparer_corrige_puis_valide(self) -> None:
        casse = self._casser(_contrat_valide())
        fautes = valider.valider_contrat(casse)
        self.assertTrue(fautes)
        repare = {k: v for k, v in _contrat_valide().items() if k != "gravure_svg"}
        with patch(
            "generate._appel",
            return_value=generate.json.dumps(repare, ensure_ascii=False),
        ) as appel:
            resultat = generate._reparer(casse, fautes)
        self.assertEqual(valider.valider_contrat(resultat), [])
        self.assertEqual(appel.call_count, 1)
        # Les fautes exactes sont montrées au modèle, la gravure ne l'est pas.
        demande = appel.call_args.args[1]
        self.assertIn("g-loue", demande)
        self.assertNotIn("gravure_svg", demande)

    def test_reparer_reimpose_les_champs_deterministes(self) -> None:
        casse = self._casser(_contrat_valide())
        fautes = valider.valider_contrat(casse)
        repare = {k: v for k, v in _contrat_valide().items() if k != "gravure_svg"}
        repare["liturgie"] = {"nom": "violet"}
        repare["date"] = "1999-01-01"
        with patch(
            "generate._appel",
            return_value=generate.json.dumps(repare, ensure_ascii=False),
        ):
            resultat = generate._reparer(casse, fautes)
        self.assertEqual(resultat["liturgie"]["nom"], "vert")
        self.assertEqual(resultat["date"], "2026-07-15")
        self.assertEqual(resultat["gravure_svg"], generate._GRAVURE_ABSENTE)

    def test_reparer_abandonne_apres_deux_essais(self) -> None:
        casse = self._casser(_contrat_valide())
        fautes = valider.valider_contrat(casse)
        toujours_casse = {
            k: v for k, v in self._casser(_contrat_valide()).items()
            if k != "gravure_svg"
        }
        with patch(
            "generate._appel",
            return_value=generate.json.dumps(toujours_casse, ensure_ascii=False),
        ) as appel:
            with self.assertRaisesRegex(ValueError, "toujours invalide"):
                generate._reparer(casse, fautes)
        self.assertEqual(appel.call_count, 2)


class ContratTests(unittest.TestCase):
    def test_cles_manquantes_detecte_les_trous(self) -> None:
        contrat = {cle: "x" for cle in generate.CLES_REQUISES}
        self.assertEqual(generate._cles_manquantes(contrat), [])
        del contrat["titre"]
        del contrat["analogie"]
        self.assertEqual(generate._cles_manquantes(contrat), ["analogie", "titre"])


if __name__ == "__main__":
    unittest.main()
