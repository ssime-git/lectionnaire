# Lectionnaire

Un site quotidien d'étude biblique. Chaque jour, les lectures du lectionnaire
romain rendues vivantes et digestes — **sans être diluées** — et une invitation
à se laisser rejoindre par le Christ, sans moralisme.

Tradition protestante (ÉPUdF) sur lectionnaire romain, accueillant aussi les
lecteurs catholiques. Sources en **domaine public** uniquement.

> Ce n'est pas un énième livre d'étude. C'est le livre d'étude *présent mais
> enterré* : accessible au clic, jamais imposé. Le lecteur pressé vit la page en
> trois minutes ; celui qui veut creuser descend jusqu'à Calvin.

---

## Ce que produit le projet

Une page par jour, statique, hébergée gratuitement sur GitHub Pages. Sa structure
suit une **croix** : on descend (profondeur spirituelle), on glisse latéralement
(exploration).

```
①  l'image        un bois gravé + une métaphore centrale
②  les textes     Segond 1910 (ou Crampon), mots glosables    → rail latéral
③  le contexte    d'où parlent ces textes
④  l'analogie     le pont vers aujourd'hui
⑤  le geste       une invitation concrète, non moralisatrice
⑥  la question    une seule, ouverte, qui habite
⑦  les racines    Calvin, Chrysostome, écarts textuels        → rail latéral
```

La couleur de la page est la **couleur liturgique du jour** (vert au temps
ordinaire, violet en Avent/Carême…) : elle vient du calendrier, jamais d'un choix
esthétique. Trois pages de démonstration sont dans `docs/`.

---

## Le principe qui gouverne tout

**Le contenu est séparé du template**, et **ce qui est déterministe ne passe
jamais par un LLM.**

```
DÉTERMINISTE (scripts)              JUGEMENT (humain + LLM cadré)
────────────────────                ─────────────────────────────
couleur liturgique  liturgie.py     métaphore centrale
références du jour   refs.py         choix des mots à gloser
texte biblique       Segond/Crampon  analogie, geste, question
bois gravé           gravure.py      lecture patristique
validation           valider.py      classe de chaque lecture
```

Une page = un template figé (`template/jour.html.j2`) + un petit JSON
(`data/jours/AAAA-MM-JJ.json`). Tant que cette frontière tient, tout le reste est
simple : corriger le template republie des mois d'archive, éditer un JSON à la
main corrige un jour, changer un index republie une autre analogie.

---

## Démarrage en 3 minutes

```bash
uv sync
make render DATE=2026-07-08          # assemble docs/2026-07-08.html
```

Ouvre `docs/2026-07-08.html` : la page du 8 juillet. Bascule ton système en mode
sombre — elle reste lisible, c'est voulu.

Les commandes utiles sont :

```bash
make check                            # tests + validation des trois jours de démo
make validate DATE=2026-07-08         # valide un seul JSON
make render DATE=2026-07-08           # rend une page et l'archive
make serve                            # aperçu local sur http://localhost:8000
```

`uv` est le seul gestionnaire Python requis. Installe-le si besoin avec la
[procédure officielle](https://docs.astral.sh/uv/getting-started/installation/),
puis lance `uv sync`. Le fichier `.venv/` est local et ignoré par Git.

Pour comprendre le pipeline et les trois étapes de travail :
**[docs-projet/PIPELINE.md](docs-projet/PIPELINE.md)**.

Pour publier le site en ligne, pas à pas :
**[docs-projet/MISE-EN-LIGNE.md](docs-projet/MISE-EN-LIGNE.md)**.

Pour **laisser Claude Code faire le setup à ta place** (création du dépôt avec
`gh`, tests, push, activation de Pages) : ouvre le projet dans Claude Code et
suis **[CLAUDE.md](CLAUDE.md)** — il s'arrête pour te demander avant chaque action
publique.

## Générer un brouillon avec Cloudflare Workers AI

La génération est volontairement séparée de la publication : elle produit un
brouillon JSON, qui doit être relu dans son aperçu HTML avant toute fusion.

1. Dans GitHub, ouvre **Actions** → **Générer un brouillon du lectionnaire** →
   **Run workflow**, puis indique une date au format `AAAA-MM-JJ`.
2. L'action interroge Workers AI, valide le JSON, rend le HTML et ouvre une pull
   request `draft/AAAA-MM-JJ`.
3. Ouvre l'URL Cloudflare Pages affichée dans la PR pour relire la page telle
   qu'elle sera servie. Choisis et ajuste notamment l'analogie proposée.
4. Fusionne la PR seulement après relecture : GitHub Pages publiera alors la
   version validée.

Pour tester localement, exporte les deux variables avant de lancer la commande :

```bash
export CLOUDFLARE_ACCOUNT_ID="…"
export CLOUDFLARE_AI_API_TOKEN="…"
make generate DATE=2026-07-08
make validate DATE=2026-07-08
make render DATE=2026-07-08
```

Ne copie jamais un jeton dans le dépôt ou dans un message. En CI, seuls les
secrets GitHub `CLOUDFLARE_ACCOUNT_ID` et `CLOUDFLARE_AI_API_TOKEN` sont lus.

Si l'action ne peut pas ouvrir sa pull request, ouvre GitHub → **Settings** →
**Actions** → **General** et autorise les workflows à lire et écrire le contenu
du dépôt ainsi qu'à créer des pull requests.

---

## Les trois étapes de travail

```
ÉTAPE 1  valider le template          (aucun LLM)
ÉTAPE 2  brancher la génération       (le skill, un modèle puissant)
ÉTAPE 3  automatiser la nuit          (GitHub Actions, avec relecture)
```

**Ne pas les mélanger.** Câbler le LLM avant d'avoir éprouvé le template revient
à déboguer les deux en même temps. Détail dans `docs-projet/PIPELINE.md`.

---

## Structure du dépôt

```
template/jour.html.j2      le moule (ne change plus)
data/
  jours/                   un JSON par jour — le contenu
  segond1910/              texte canonique (domaine public)
  crampon1923/             texte deutérocanonique (domaine public)
src/
  refs.py                  références AELF + routage Segond/Crampon
  liturgie.py              couleur liturgique du jour
  gravure.py               moteur de bois gravé (lexique de motifs)
  render.py                JSON + template → HTML + archive
  valider.py               refuse un contrat bancal
  generate.py              ÉTAPE 2 — remplit le JSON via inférence
docs/                      sortie publiée par GitHub Pages
.github/workflows/nuit.yml ÉTAPE 3 — le cron nocturne
```

Le skill portable de génération vit **hors de ce dépôt**
(`skills/lectionnaire-du-jour/`) : il se charge dans Claude Code, Codex, Cursor.

---

## Sources & droits

Texte biblique : **Louis Segond 1910** (canonique) et **Crampon 1923**
(deutérocanoniques), tous deux en domaine public. Commentaires : **Calvin**,
**Chrysostome**, Pères de l'Église — domaine public. L'API **AELF** ne sert
qu'aux *références* : sa traduction liturgique est sous droits et n'est jamais
reproduite.

Le site est un **objet d'étude, pas une autorité**. Son honnêteté tient à une
règle : chaque affirmation reste traçable vers sa source.
