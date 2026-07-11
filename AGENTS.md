# AGENTS.md — installation pilotée

Tu es l'agent chargé de mettre le site **Lectionnaire** en ligne à la place de
l'utilisateur, depuis la création du dépôt jusqu'à la publication sur GitHub
Pages. Tu procèdes **par phases**, tu **testes après chaque phase**, et tu
**t'arrêtes** aux portes marquées ⛔ pour obtenir une confirmation humaine avant
toute action irréversible ou exposante.

## Règles absolues

- **Ne jamais franchir une porte ⛔ sans un « oui » explicite** de l'utilisateur
  dans le fil. Créer un dépôt public et pusher exposent son travail : ce sont ses
  décisions, pas les tiennes.
- **Un test échoué arrête la phase.** Tu diagnostiques, tu proposes un correctif,
  tu ne passes pas à la suite en espérant que ça se règle.
- **Tu ne modifies pas le contenu du projet** (JSON, template, scripts) sauf si un
  test le réclame et que tu expliques pourquoi.
- Tu annonces chaque commande avant de la lancer et tu montres son résultat.
- Si une commande demande une info que tu n'as pas (nom du dépôt, compte GitHub),
  tu la demandes — tu ne l'inventes pas.

---

## Phase 0 — état des lieux (aucun risque)

But : vérifier que l'environnement est prêt.

```bash
git --version
gh --version && gh auth status
python3 --version
ls -1                      # doit montrer src/ data/ template/ docs/ README.md
```

**Test 0.** `gh auth status` doit indiquer un compte authentifié. Sinon,
demander à l'utilisateur de lancer `gh auth login` et s'arrêter là.

Signaler à l'utilisateur quel compte GitHub est connecté, et rappeler :
> Le dépôt sera public et portera ce compte. Pour un anonymat réel, il faut un
> compte GitHub dédié au projet. Est-ce le bon compte ?

⛔ **Porte 0.** Ne pas continuer tant que l'utilisateur n'a pas confirmé le compte.

---

## Phase 1 — construire le site en local (aucun risque)

But : prouver que le site se génère avant de créer quoi que ce soit en ligne.

```bash
pip install -r requirements.txt
python src/render.py 2026-07-08
python src/render.py 2026-12-17
python src/render.py 2026-02-21
```

**Test 1a — les pages existent.**
```bash
ls -1 docs/*.html          # attendu : index + 3 jours = 4 fichiers
```

**Test 1b — le contenu est valide.**
```bash
for j in 2026-07-08 2026-12-17 2026-02-21; do python src/valider.py data/jours/$j.json; done
```
Les trois doivent afficher « contrat valide ». Un échec = corriger le JOUR
concerné avant d'aller plus loin.

**Test 1c — l'accueil liste bien les jours.**
```bash
grep -c '<li>' docs/index.html      # attendu : 3
```

Si les trois tests passent : le site est fonctionnel en local. L'annoncer.

---

## Phase 2 — le test qui n'a jamais tourné (aucun risque, mais révélateur)

But : confronter `refs.py` à la vraie API AELF. **Ce test n'a jamais été exécuté
pour de vrai** — c'est la première inconnue du projet.

```bash
python src/refs.py 2026-07-08
```

**Test 2 — interprétation :**
- S'il affiche des références plausibles (Os…, Ps…, Mt…) et une couleur : le
  parsing de l'API est bon. **Grande victoire**, une partie du pipeline est
  validée d'un coup. L'annoncer.
- S'il affiche « Échec (API AELF ou parsing à vérifier) » ou des références
  vides : le format réel de l'API diffère de l'hypothèse. **Ce n'est pas
  bloquant pour la mise en ligne** (les 3 jours de démo sont déjà écrits). Isoler
  le problème dans la fonction `_parse_aelf` de `src/refs.py`, montrer à
  l'utilisateur la réponse brute de l'API (`curl` ci-dessous) et proposer un
  correctif — sans le déployer sans accord.

```bash
curl -s "https://api.aelf.org/v1/messes/2026-07-08/romain" | head -c 800
```

Ne pas laisser un échec ici stopper la publication : le noter comme dette connue
et continuer.

---

## Phase 3 — créer le dépôt distant  ⛔ IRRÉVERSIBLE / EXPOSANT

But : créer le dépôt GitHub. **C'est la première action publique.**

Demander à l'utilisateur le **nom du dépôt** (proposer `lectionnaire`) et
confirmer qu'il le veut **public** (obligatoire pour Pages gratuit).

⛔ **Porte 3.** N'exécuter la commande suivante qu'après un « oui » explicite,
avec le nom validé.

```bash
git init
git add .
git commit -m "Premier jet du lectionnaire"
git branch -M main
gh repo create NOM-VALIDÉ --public --source=. --remote=origin
```

**Test 3.**
```bash
git remote -v            # origin doit pointer vers le nouveau dépôt
```

Ne **pas** pusher encore — c'est la porte suivante.

---

## Phase 4 — publier le code  ⛔ EXPOSANT

But : envoyer le dépôt. Après ça, le code est public.

Rappeler à l'utilisateur ce qui va devenir visible (tout le dépôt, y compris
`docs-projet/` — mais **pas** servi par Pages). Confirmer qu'aucun secret n'est
présent :

```bash
cat .gitignore            # doit ignorer .env
git ls-files | grep -i -E '\.env|secret|token|key' || echo "aucun secret suivi ✓"
```

⛔ **Porte 4.** N'exécuter le push qu'après confirmation.

```bash
git push -u origin main
```

**Test 4.**
```bash
gh repo view --web        # ouvre le dépôt ; l'utilisateur vérifie que tout est là
```

---

## Phase 5 — activer GitHub Pages

But : servir le dossier `docs/`.

Tenter l'activation par l'API (source = branche `main`, dossier `/docs`) :

```bash
gh api -X POST "repos/{owner}/{repo}/pages" \
  -f "source[branch]=main" -f "source[path]=/docs" 2>/dev/null \
  || gh api -X PUT "repos/{owner}/{repo}/pages" \
     -f "source[branch]=main" -f "source[path]=/docs"
```

Si l'API refuse (droits, ordre d'appel), **ne pas insister** : guider
l'utilisateur en manuel — Settings → Pages → Source = *Deploy from a branch* →
branche `main`, dossier `/docs` → Save. C'est décrit dans
`docs-projet/MISE-EN-LIGNE.md`.

**Test 5 — le site répond.** Attendre 1 à 2 minutes (premier déploiement), puis :

```bash
gh api "repos/{owner}/{repo}/pages" --jq .html_url    # récupère l'URL publiée
```

Récupérer l'URL, la donner à l'utilisateur, et vérifier qu'elle répond :

```bash
URL=$(gh api "repos/{owner}/{repo}/pages" --jq .html_url)
curl -s -o /dev/null -w "%{http_code}\n" "$URL"        # 200 attendu (404 = attendre encore)
```

Un 404 pendant deux minutes est normal. Recharger. Un 404 persistant = vérifier
le dossier source (`/docs`).

---

## Phase 6 — clôture

Annoncer à l'utilisateur :
- l'URL publique du site ;
- que trois jours de démonstration sont en ligne ;
- le geste quotidien pour publier un nouveau jour :
  ```bash
  python src/render.py AAAA-MM-JJ
  git add docs/ data/jours/ && git commit -m "Page du …" && git push
  ```
- les **deux dettes connues** à ne pas oublier : compléter les corpus Segond /
  Crampon depuis une source structurée, et régler `_parse_aelf` si la phase 2 a
  révélé un écart.

**Ne rien automatiser de plus.** Le cron nocturne (`.github/workflows/nuit.yml`)
et la génération par IA sont des étapes ultérieures, décrites dans
`docs-projet/PIPELINE.md`. Ne pas les activer sans que l'utilisateur le demande,
et ne pas laisser le cron publier sans relecture — certains jours (Passion,
Vigile pascale, généalogies) exigent une décision humaine.

---

## Récapitulatif des portes ⛔

| Porte | Avant de… | Pourquoi |
|---|---|---|
| 0 | continuer | confirmer le bon compte GitHub (anonymat) |
| 3 | `gh repo create` | création publique irréversible |
| 4 | `git push` | exposition du code |

En dehors de ces portes, tu avances de façon autonome, un test après chaque
phase, en montrant tes résultats.
