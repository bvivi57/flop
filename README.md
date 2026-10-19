# flop — outils pour préparer un nœud du Flop Network

Deux outils en ligne de commande, issus de la série d'articles « Préparer un nœud
mineur Flop sous Linux » :

- [`tools/verify_message.py`](#verify_messagepy--vérifier-hors-ligne-une-signature-technocore) :
  vérifier hors ligne la signature d'un message Technocore ;
- [`tools/bench_ollama.py`](#bench_ollamapy--mesurer-un-gpu-et-tester-son-endurance) :
  mesurer un GPU sous Ollama et tester son endurance sur 24 heures.

## verify_message.py — vérifier hors ligne une signature Technocore

Outil en ligne de commande qui vérifie les signatures **Ed25519** des messages
[Technocore](https://technocore.chat), le chat HTTP des agents IA édité par FLOP
Labs. Il n'utilise que le **DID public** de l'auteur : aucune clé privée, aucun
compte, aucune confiance à accorder au serveur.

Le *starter* officiel vérifie les preuves de contribution, mais pas les messages
de salon. C'est le trou que comble ce script.

> Pourquoi c'est utile : Technocore ne conserve qu'environ **10 Mio d'historique
> par salon**. Mesure du 16/09/2026 sur `lobby` : 17 056 messages conservés, soit
> **16,6 minutes** à 17 messages/seconde. Le JSON enregistré au moment de l'envoi
> est donc votre seule preuve durable — et sa signature reste vérifiable pour
> toujours, par n'importe qui, sans le serveur.

### Installation

Python 3.11 ou plus récent (testé sur 3.12), une seule dépendance (`cryptography`) :

```bash
git clone https://github.com/bvivi57/flop.git
cd flop
python3 -m venv .venv
source .venv/bin/activate          # Windows : .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Utilisation

Trois sources, selon ce que vous avez sous la main :

```bash
# 1. un JSON enregistré (réponse d'un « say » ou d'un « read »)
python tools/verify_message.py file preuves/intro.json --seq 51043019

# 2. un message encore présent sur le serveur
python tools/verify_message.py fetch lobby 51043019

# 3. des champs saisis à la main
python tools/verify_message.py manual --room lobby --did did:key:z6Mk... \
    --nonce 1789499904476726300 --text "..." --sig "..."
```

Sortie type :

```console
VALIDE     lobby #51043019  did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi
1 message(s) : 1 valide(s), 0 invalide(s), 0 non signe(s)
```

Options utiles : sur `file`, `--seq` ne vérifie qu'une séquence et `--did` qu'un
auteur ; sur `fetch`, `--base-url` vise une autre instance, `--timeout` et
`--max-seconds` bornent le téléchargement de l'historique (le serveur répond
parfois en une seconde, parfois en plusieurs minutes).

Codes de sortie : `0` tout est valide · `1` au moins un message invalide ou non
signé · `2` source illisible ou message introuvable.

La sortie console est volontairement en **ASCII pur**, pour rester lisible dans
les consoles Windows.

### Ce qui est vérifié

Un message signé couvre exactement la chaîne `salon|nonce|texte`. Le script
recalcule cette chaîne, extrait la clé publique du DID `did:key` (multicodec
Ed25519, base58btc) et vérifie la signature. Un seul caractère modifié et la
vérification échoue — c'est le meilleur moyen de se convaincre que l'outil
fonctionne vraiment.

Détail qui casse beaucoup d'implémentations : les nonces Technocore dépassent
2^53. Un lecteur JSON qui les charge en flottant les arrondit silencieusement et
invalide des signatures pourtant bonnes (`JSON.parse` en JavaScript, par
exemple). Le script les lit en entier exact.

## bench_ollama.py — mesurer un GPU et tester son endurance

Script autonome (bibliothèque standard Python, aucune dépendance) qui interroge
l'API locale d'[Ollama](https://github.com/ollama/ollama) et mesure, requête par
requête, la vitesse de lecture du prompt (*prefill*) et de génération (*decode*).
En parallèle, il relève toutes les cinq secondes la température, la puissance,
l'occupation et la mémoire du GPU via `nvidia-smi`.

```bash
# flux simple : 5 passages, prompt de 4 000 tokens, réponse de 512
python3 tools/bench_ollama.py --runs 5 --prompt-tokens 4000 --output-tokens 512

# 4 requêtes simultanées (débit total, profil serveur)
python3 tools/bench_ollama.py --runs 3 --parallel 4 --prompt-tokens 1500 --output-tokens 192

# test d'endurance de 24 heures
python3 tools/bench_ollama.py --minutes 1440 --parallel 4 --output-tokens 2048
```

Le modèle par défaut est Hermes-4-14B en Q4_K_M (`--model` pour en changer, à
récupérer d'abord avec `ollama pull`). Les résultats sont écrits dans `bench/` :
un CSV par exécution, rempli au fil de l'eau, et un journal GPU.

Ce que le script fait pour ne pas fausser les mesures :

- une requête de chauffe, non comptée, charge le modèle avant les mesures ;
- chaque prompt porte un sel propre à l'exécution : sans lui, Ollama sert la
  lecture d'un prompt déjà vu depuis son cache, et affiche un débit irréaliste ;
- en mode endurance, une requête en erreur est comptée sans arrêter le test
  (arrêt seulement après 10 séries consécutives en échec).

L'« indice H100-eq » affiché à la fin est un repère grossier, pour suivre une
machine dans le temps : le modèle, la quantification et le moteur diffèrent de
la référence officielle, et le réseau mesurera lui-même la capacité d'un mineur.

## Tests

```bash
cd tools && python -m unittest discover -s .
```

23 tests autonomes ; 2 tests supplémentaires s'exécutent si vous placez une
preuve enregistrée dans `proofs/lobby_intro_2026-09-15.json` (absente de ce
dépôt).

## Articles détaillés (français)

Série « Préparer un nœud mineur Flop sous Linux » :

1. **Technocore et DID** — la création d'identité sous Linux et Windows, et les
   pièges mesurés : <https://www.myprivatelab.tech/flop/technocore-did>
   (source : [`docs/publication/technocore-did.md`](docs/publication/technocore-did.md))
2. **Préparer un serveur GPU sous Rocky Linux 10** — pilote NVIDIA à modules
   ouverts, Secure Boot, verrouillage de version, Docker et Ollama :
   <https://www.myprivatelab.tech/flop/serveur-linux-gpu>
   (source : [`docs/publication/serveur-linux-gpu.md`](docs/publication/serveur-linux-gpu.md))
3. **24 heures à pleine charge** — méthode de mesure, benchmarks, test
   d'endurance de 24 heures avec `bench_ollama.py`, et checklist provisoire du
   jour J pour le testnet (article sur le blog à venir ; source :
   [`docs/publication/benchmarks-soak-jour-j.md`](docs/publication/benchmarks-soak-jour-j.md))

## Licence

Apache-2.0, comme Technocore. Voir [LICENSE](LICENSE).

Auteur : [@bvivi57](https://github.com/bvivi57) ·
DID `did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi`
