# Lectionnaire

**Le site : <https://lectionnaire.pages.dev/>**

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

Une page par jour, statique, hébergée gratuitement sur Cloudflare Pages. Sa structure
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

## Architecture de l'automatisation

La génération est volontairement séparée de la publication : elle produit un
brouillon JSON, qui doit être relu dans son aperçu HTML avant toute fusion.
**La fusion de la PR est le seul geste qui publie.**

```
cron nocturne (02:20 UTC, J+1)          Run workflow manuel (toute date)
        └───────────────┬───────────────────────┘
                        ▼
        make generate ── Workers AI (Kimi K2.6, quota gratuit)
                            └─ échec → Claude Sonnet 5 (abonnement Pro)
                        ▼
        make validate → make render
                        ▼
        PR draft/<date> + aperçu Cloudflare Pages
                        ▼
        RELECTURE HUMAINE ──┬─ /claude-feedback <consignes>  ──┐
                            ├─ édition manuelle du JSON        ├─ re-valide,
                            │                                  │  re-rend,
                            │  ◄────── aperçu mis à jour ──────┘  re-pousse
                            ▼
        MERGE (geste humain) → Cloudflare Pages redéploie le site
```

Trois workflows GitHub :

| Workflow | Déclencheur | Rôle |
|---|---|---|
| `generer-brouillon.yml` | cron 02:20 UTC (J+1) ou manuel (date au choix) | tests → génération → validation → rendu → PR |
| `claude-feedback.yml` | commentaire `/claude-feedback …` sur une PR draft | Claude retravaille le JSON selon les consignes |
| `rendre-brouillon.yml` | commit humain sur `data/jours/*.json` d'une branche draft | re-valide et re-rend la page |

## Générer un brouillon

Un cron nocturne (02:20 UTC, soit 04:20 à Paris l'été) génère automatiquement
le brouillon du **lendemain** et ouvre sa PR — la relecture et la fusion
restent des gestes humains. Pour une autre date, lance le workflow à la main :

1. Dans GitHub, ouvre **Actions** → **Générer un brouillon du lectionnaire** →
   **Run workflow**, puis indique une date au format `AAAA-MM-JJ`.
2. L'action interroge Workers AI, valide le JSON, rend le HTML et ouvre une pull
   request `draft/AAAA-MM-JJ`.
3. Ouvre l'URL Cloudflare Pages affichée dans les checks de la PR pour relire
   la page telle qu'elle sera servie. Choisis notamment la variante d'analogie
   (`analogie.choisi`).
4. Pour corriger, deux voies :
   - **`/claude-feedback <consignes>`** en commentaire de la PR : Claude
     retravaille le JSON selon tes consignes (« approfondis la deuxième
     glose », « l'analogie 1 est gadget, propose autre chose »…), re-valide,
     re-rend et pousse — l'aperçu se met à jour, un commentaire confirme.
   - Éditer `data/jours/AAAA-MM-JJ.json` à la main dans la PR : le workflow
     « Rendre le brouillon après édition » re-valide et re-rend à chaque
     commit.
5. Fusionne la PR seulement après relecture : Cloudflare Pages redéploie alors
   le site complet, nouveau jour inclus.

---

## Setup de l'automatisation

### Secrets GitHub (Settings → Secrets and variables → Actions)

| Secret | Rôle | Comment l'obtenir |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | moteur principal (Workers AI) | dashboard Cloudflare → Workers & Pages → Account ID |
| `CLOUDFLARE_AI_API_TOKEN` | moteur principal | dashboard Cloudflare → API Tokens → modèle « Workers AI » |
| `CLAUDE_CODE_OAUTH_TOKEN` | moteur de secours + `/claude-feedback` | `claude setup-token` sur ta machine (abonnement Claude Pro) |

Ne copie jamais un jeton dans le dépôt ou dans un message. Si une action ne
peut pas ouvrir sa pull request : **Settings → Actions → General** → autoriser
les workflows à écrire et à créer des PR.

Côté hébergement : projet **Cloudflare Pages** relié au dépôt, branche de
production `main`, dossier de sortie `docs` — chaque PR reçoit son URL
d'aperçu, chaque merge redéploie le site.

### Options (variables d'environnement)

| Variable | Valeurs | Effet |
|---|---|---|
| `LECTIONNAIRE_MOTEUR` | *(vide)* / `claude` | vide = Workers AI ; `claude` = Claude Code headless |
| `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_AI_API_TOKEN` | — | requis pour le moteur Workers AI |
| `CLAUDE_CODE_OAUTH_TOKEN` | — | requis pour le moteur `claude` en CI |

Les modèles se règlent dans [src/generate.py](src/generate.py) :
`MODELE_REDACTION` (`@cf/moonshotai/kimi-k2.6`, ~2 000 neurons/page sur les
10 000 gratuits/jour) et `MODELE_CLAUDE` (`claude-sonnet-5`).

### Générer en local

```bash
# Moteur Workers AI
export CLOUDFLARE_ACCOUNT_ID="…"
export CLOUDFLARE_AI_API_TOKEN="…"
make generate DATE=2026-07-08

# Moteur Claude (CLI `claude` connecté à ton abonnement)
LECTIONNAIRE_MOTEUR=claude make generate DATE=2026-07-08

# Puis, dans les deux cas
make validate DATE=2026-07-08
make render DATE=2026-07-08
```

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
  generate.py              remplit le JSON via inférence (2 moteurs)
tests/                     tests unitaires de la génération
docs/                      sortie publiée par Cloudflare Pages
.github/workflows/
  generer-brouillon.yml    cron nocturne + dispatch manuel → PR de brouillon
  claude-feedback.yml      /claude-feedback sur une PR → retravail par Claude
  rendre-brouillon.yml     re-rend la page après édition manuelle du JSON
```

---

## Sources & droits

Texte biblique : **Louis Segond 1910** (canonique) et **Crampon 1923**
(deutérocanoniques), tous deux en domaine public. Commentaires : **Calvin**,
**Chrysostome**, Pères de l'Église — domaine public. L'API **AELF** ne sert
qu'aux *références* : sa traduction liturgique est sous droits et n'est jamais
reproduite.

Le site est un **objet d'étude, pas une autorité**. Son honnêteté tient à une
règle : chaque affirmation reste traçable vers sa source. 

## Design et éclairages contemporains

Direction « épurée » : beaucoup d'air, de fins filets, une seule couleur
d'accent (la couleur liturgique) ; la couleur vive vit dans les scènes. Le thème
sombre est un brun cacao chaud, jamais noir.

- **Scènes** : `src/scene.py` compose, sans modèle ni réseau, des aplats
  colorés au pastel derrière le bois gravé du jour, et une scène abstraite pour
  la question finale (et la pause, si le JSON en porte une). Même date, même
  image ; couleurs en variables CSS que la météo et le thème font glisser.
- **Défilement** : ↓ les sections se révèlent, l'analogie s'éclaire mot à mot,
  les scènes de pause s'ouvrent ; → lectures et racines restent des rails.
  Tout cela ne s'applique qu'avec JavaScript (classe `js`) : sans lui, la page
  se lit d'un bloc.
- **Mots entourés** : un trait à la main se dessine à l'écran ; la glose
  s'ouvre dans le compagnon (onglet « Mot »), à côté de Voir et Demander. Les
  `details` restent dans le document pour la lecture sans JS et l'impression.
- **Champs facultatifs** du JSON : `gloses[].aujourdhui` (ce que le mot dit
  pour nous aujourd'hui) et `pauses` (au plus une `{question, suite}`). Le
  générateur les demande ; le validateur les contrôle.

La rubrique facultative « Éclairages contemporains » est alimentée par
`data/eclairages.json`, un petit corpus éditorial relu, indépendant du modèle
qui génère les brouillons. Chaque entrée contient une œuvre, un chapitre, un
lien de vérification, la date de vérification et des versets d’ancrage précis.
Elle distingue la reformulation de l’auteur, le rapprochement éditorial avec
le texte du jour et les limites de ce rapprochement. Pas de citation longue,
pas d’attribution inventée, pas de rubrique si aucun verset ne correspond.
Le corpus réunit des voix protestantes, anglicanes, catholiques, orthodoxes
et juives (Lewis, Bonhoeffer, Barth, Stott, Keller, Wright, Ellul, Ratzinger,
Nouwen, Bloom, Schmemann, Delbrêl, Heschel…) ; un champ `echo` relie parfois
l'œuvre moderne à un classique (Luther, Augustin, Kierkegaard, Edwards…), et
`decouvrir` dit pourquoi lire le livre en entier. Le champ `preuve` garde, pour
le relecteur, ce que la page source confirme.

Pour ajouter un éclairage, vérifier la source avant d’écrire une reformulation
originale, puis renseigner les champs du corpus et ses ancrages
`[livre, chapitre, verset]` ou `[livre, chapitre, début, fin]` (psaumes en
numérotation hébraïque, celle de Segond). Au plus deux encarts par jour,
d'auteurs différents, l'évangile d'abord. Les références multichapitres ne
déclenchent pas d’encart. Relancer le rendu des jours concernés après une
modification du corpus ; les brouillons futurs le prennent en compte au rendu.

### Ambiance météo

Le rendu peut lire `data/meteo.json` avec les champs `ville`, `latitude` et
`longitude`. Sans configuration, la palette chaleureuse reste disponible sans
appel réseau. Avec configuration, une requête Open-Meteo à l’ouverture de la
page nuance les fonds selon le temps actuel : soleil (miel), nuages (lin),
pluie (terre cuite), neige (ivoire). Le choix clair/sombre reste indépendant.
Aucune géolocalisation du lecteur. En cas d’échec, la palette par défaut et
l’intégralité de la lecture restent accessibles.

Documentation de la source : https://open-meteo.com/en/docs (vérifiée le
15 novembre 2026). La ville n’est pas encore configurée.
