# 24 heures à pleine charge : benchmarks, test d'endurance et checklist du jour J

*Épisode 3 de la série « Préparer un nœud mineur Flop sous Linux ».*

Dans l'épisode 2, la RTX 5070 Ti a quitté Windows pour un serveur Rocky Linux
10.2, avec le pilote verrouillé, Docker et Ollama. Restait à vérifier deux
choses : que les chiffres tiennent quand on les mesure proprement, et que la
machine tienne **24 heures sur 24** sans broncher. C'est l'exigence de base d'un
mineur sur le Flop Network : une machine qui décroche perd des tâches, et une
tâche sans réponse se paie.

Cet article donne la méthode de mesure, les résultats d'un test d'endurance de
24 heures à pleine charge, ce que ces chiffres valent (et ne valent pas) face au
réseau, puis une **checklist provisoire du jour J**, construite à partir de la
documentation opérateur que Flop Labs publie pour son réseau de développement.

> **Avertissement.** Au 19 octobre 2026, le testnet du Flop Network n'est pas
> ouvert et n'a pas de date officielle. La checklist de la fin s'appuie sur la
> documentation du **devnet** (le réseau privé de l'équipe) : elle changera
> probablement. Rien ne garantit une récompense future.

---

## 1. Mesurer sans se mentir

J'utilise un petit script Python, `bench_ollama.py`, que j'ajoute à
[mon dépôt](https://github.com/bvivi57/flop) avec cet épisode. Il interroge l'API locale
d'Ollama, relève pour chaque requête les deux vitesses qui comptent, et note en
parallèle la température, la puissance et l'occupation du GPU :

- **la lecture du prompt** (*prefill*) : le modèle ingère le texte d'entrée.
  C'est limité par la puissance de calcul de la carte ;
- **la génération** (*decode*) : le modèle produit sa réponse, un token après
  l'autre. C'est limité par la bande passante de la mémoire.

Le modèle de test est Hermes-4-14B en quantification Q4_K_M, avec un contexte de
8 192 tokens : environ 9 Go de poids, ce qui laisse de la place au cache de
plusieurs conversations sur une carte de 16 Go.

Trois règles que j'ai apprises à mes dépens :

1. **Écarter le premier passage.** La toute première requête charge le modèle et
   initialise CUDA : chez moi, 1 025 tokens/s en lecture au lieu de 3 500. Je
   lance plusieurs passages et je retiens la **médiane**, pas la moyenne.
2. **Ne jamais envoyer deux fois le même prompt.** Comme raconté dans
   l'épisode 2, Ollama garde en cache les prompts déjà lus. Un prompt identique
   d'une série à l'autre donnait une lecture à 277 000 tokens/s, soixante-dix
   fois trop. Le script ajoute désormais à chaque prompt un « sel » qui dépend de
   l'heure de lancement.
3. **Écrire les résultats au fil de l'eau.** Pour un test de 24 heures, le
   script enregistre chaque série dans le CSV dès qu'elle se termine : une
   coupure en pleine nuit ne fait pas perdre les heures déjà mesurées. Une
   requête en erreur est comptée, sans arrêter le test.

Les commandes :

```bash
# Mesure en flux simple : 5 passages, prompt de 4 000 tokens, réponse de 512
python3 tools/bench_ollama.py --runs 5 --prompt-tokens 4000 --output-tokens 512

# Mesure en parallèle : 4 requêtes simultanées, prompt de 1 500 tokens, réponse de 192
python3 tools/bench_ollama.py --runs 3 --parallel 4 --prompt-tokens 1500 --output-tokens 192
```

## 2. Les résultats en détail

Mesures du 10 octobre 2026 : Rocky Linux 10.2, pilote 615.71.09, Ollama 0.40.2
avec `OLLAMA_NUM_PARALLEL=4`.

| Mesure | Windows 11 (09/09) | Rocky Linux 10 (10/10) |
|---|---|---|
| Lecture du prompt, une requête (médiane) | 3 344 tokens/s | **3 577 tokens/s** |
| Génération, une requête (médiane) | 72,0 tokens/s | **78,5 tokens/s** |
| Génération, 2 requêtes simultanées (total) | 62,6 tokens/s | 67,2 tokens/s |
| Génération, 4 requêtes simultanées (total) | — | **151,2 tokens/s** (53,8 par requête) |
| VRAM occupée | 11,9 Go | 13,7 Go |
| Pic GPU | 64 °C, 284 W | 67 °C, 301 W |

Deux lectures :

- **À deux requêtes, le parallélisme ne sert presque à rien.** Le total passe de
  62,6 à 67,2 tokens/s. C'est à **quatre** requêtes que le gain apparaît : le
  débit total est multiplié par 1,9 par rapport à une requête seule, chaque
  requête ralentissant de 78 à 54 tokens/s. Un serveur doit servir plusieurs
  clients en même temps : c'est ce chiffre agrégé qui compte.
- **La mémoire est le prix à payer.** Avec quatre conversations possibles,
  Ollama réserve 1,8 Go de plus pour leur cache. Il reste environ 2,6 Go libres :
  monter plus haut en parallélisme ou en contexte demanderait un modèle plus
  petit.

## 3. Le test d'endurance : 24 heures à fond

Un benchmark de quelques minutes ne dit rien sur ce qui se passe à la
dix-huitième heure : chauffe de la mémoire, limitation de puissance, erreur du
pilote, fuite de mémoire. J'ai donc lancé le même script pour **24 heures**, à
4 requêtes simultanées en permanence (le réglage de production), avec des
réponses longues de 2 048 tokens pour que la génération domine.

Pour que le test survive à la fermeture de ma session SSH, je l'ai lancé comme
unité systemd utilisateur, en autorisant mon utilisateur à garder des services
actifs sans session ouverte :

```bash
sudo loginctl enable-linger "$USER"
systemd-run --user --unit=flop-soak -p WorkingDirectory="$PWD" \
  -p StandardOutput=append:"$PWD/bench/soak.log" -p StandardError=append:"$PWD/bench/soak.log" \
  python3 tools/bench_ollama.py --minutes 1440 --parallel 4 --output-tokens 2048

systemctl --user status flop-soak     # suivi
tail -f bench/soak.log                 # journal en direct
```

Pendant ce temps, le script relève la température, la puissance, l'occupation
et la mémoire du GPU toutes les cinq secondes (17 215 relevés en 24 heures). À la
fin, le pilote donne aussi le temps cumulé passé en ralentissement thermique ou
en limitation de puissance :

```bash
nvidia-smi -q -d PERFORMANCE
```

### Résultat (10 octobre 22 h 35 → 11 octobre 22 h 35)

| Indicateur | Valeur |
|---|---|
| Requêtes | 2 258 séries de 4 = **9 032 requêtes, 0 erreur** |
| Tokens générés | **17,6 millions** |
| Débit total (médiane) | **205,8 tokens/s**, entre 202 et 208 d'heure en heure |
| Dérive sur 24 h | 204,9 tokens/s sur les 200 premières séries, 206,3 sur les 200 dernières |
| Par requête (médianes) | 56,9 tokens/s en génération, 2 825 tokens/s en lecture |
| Température GPU | 71-72 °C en moyenne chaque heure, pic à 77 °C |
| Puissance | 294-296 W en moyenne, pic à 307 W |
| Occupation GPU | 94 % en moyenne |
| Ralentissement thermique | **0 seconde** (matériel comme logiciel) |
| Limitation de puissance | 652 s cumulées, soit 0,75 % du temps |
| Système | aucune erreur dans le journal du noyau (ni Xid NVIDIA, ni erreur PCIe), Ollama jamais redémarré, VRAM fixe à 13 712 Mio |

**Verdict : la machine tient un fonctionnement 24/7 à pleine charge.** Le débit
ne baisse pas, la température se stabilise en une heure et ne bouge plus.

Trois remarques :

- **Le débit est plus élevé qu'au benchmark court** (206 contre 151 tokens/s)
  simplement parce que les réponses sont plus longues : la phase de génération,
  où les quatre requêtes avancent ensemble, pèse davantage face à la lecture du
  prompt.
- **63 séries sur 2 258 sont passées sous 185 tokens/s.** Ce n'est pas une
  instabilité : 58 % des réponses s'arrêtent naturellement avant 2 048 tokens.
  Quand une requête finit avant les autres, la série se termine avec moins de
  requêtes actives.
- **Le seul point d'attention est la puissance.** La carte vit à sa limite de
  300 W : elle y bute brièvement de temps en temps, sans conséquence mesurable.
  La température de la mémoire, elle, n'est pas lisible : `nvidia-smi` renvoie
  `N/A` sur cette GeForce. Je surveille donc la température du GPU.

### Ce que ça coûte en électricité

En intégrant le relevé de puissance, le GPU a consommé **7,07 kWh en 24 heures**,
soit environ 2,5 millions de tokens générés par kWh. À 0,20 € le kWh (à
remplacer par le prix de votre contrat), cela fait environ **1,40 € par jour** et
**130 € pour les 90 jours** annoncés du testnet, **pour le GPU seul** : il faut y
ajouter le reste de la machine, que je n'ai pas mesuré.

## 4. Ce que ces chiffres valent face au réseau

C'est la question que j'avais laissée en suspens dans l'épisode 2, et la réponse
honnête est : **pas grand-chose pour prédire un gain, beaucoup pour la
fiabilité.**

- **Le réseau mesurera lui-même.** D'après le Yellow Paper (v0.5.0, règle R8.4),
  le score d'un mineur est le calcul effectivement servi et vérifié
  (« PoUI-verified effective-FLOP served »). Ni le nombre de tâches ni le nombre
  de jours d'activité ne comptent en soi, et la page Airdrop précise qu'aucune
  prime n'est attachée à la classe de matériel. La capacité d'un mineur est
  fixée par une **calibration** sur des tâches réelles, renouvelée tous les sept
  jours.
- **Le moteur ne sera pas le même.** La documentation opérateur du devnet décrit
  un backend basé sur **vLLM** (`miner-vllm-toploc`), pas Ollama. vLLM regroupe
  les requêtes bien plus efficacement : mes chiffres Ollama sont un plancher et
  un indicateur de santé de la machine, pas la capacité que le réseau retiendra.
- **Les machines de référence jouent dans une autre catégorie.** Le calculateur
  du projet prend un H100 comme unité, avec un débit de génération de l'ordre de
  3 700 tokens/s en traitement groupé. Mon estimation personnelle, non
  officielle, situe la 5070 Ti entre **0,08 et 0,11 équivalent H100** : une
  petite part, que seule la calibration confirmera.

Ce qui reste vrai quoi qu'il arrive : **la disponibilité**. Un mineur qui ne
répond pas à une tâche dans le délai imparti est sanctionné sur son stake. Un
test d'endurance réussi est le meilleur investissement avant le jour J.

## 5. Checklist du jour J (provisoire)

Cette liste reprend la documentation opérateur de Flop Labs
(ask.flop.finance, pages `run-miner` et `run-operator`, mises à jour le
16 et le 19 octobre 2026). Elle décrit le **devnet**, et indique elle-même
qu'il n'existe pas encore de procédure publique pour demander un accès mineur.
**À revérifier ligne par ligne le jour de l'ouverture.**

### Avant l'ouverture : la machine

- [ ] GPU, pilote et version définitifs, **verrouillés** (épisode 2) : tout
  changement de carte ou d'empreinte matérielle impose de recalibrer.
- [ ] Docker et NVIDIA Container Toolkit fonctionnels : le mineur tourne en deux
  conteneurs, un *backend* (le modèle) et un *worker* (signature des
  transactions, sessions, preuves, calibration), lancés avec Docker Compose.
- [ ] Test d'endurance de 24 heures réussi, sans erreur noyau.
- [ ] Supervision et alertes : le worker doit tourner **en permanence**.
  *(Pas encore fait chez moi.)*
- [ ] Onduleur et redémarrage automatique après coupure. *(Pas encore fait.)*

### Le jour J : identité et stake

- [ ] Récupérer l'outil en ligne de commande `flop` **uniquement** depuis un
  lien officiel (flop.finance, @flop_labs), en vérifiant l'empreinte de l'image.
  Sur le devnet, il est distribué en image Docker publique sur GHCR, épinglée
  par son empreinte `sha256`.
- [ ] Créer un **compte mineur sr25519 dédié**, distinct de tout compte
  validateur. C'est le type de clé standard des chaînes Substrate, dont le
  Flop Network fait partie. Ce compte signe en continu depuis le serveur : c'est
  une clé « chaude ».
- [ ] Noter la phrase secrète **hors ligne**. Ne jamais la taper en argument de
  commande : la documentation passe le secret et le mot de passe du keystore par
  variables d'environnement, et le fichier de clé du worker appartient à root,
  en mode `0600`.
- [ ] Vérifier l'identité de la chaîne (*genesis hash*) avant toute transaction
  signée.
- [ ] **Stake** : le mineur doit bloquer 10 000 FLOP de base, plus un stake de
  capacité proportionnel à la puissance mesurée. Bonne nouvelle de la mise à
  jour du 19 octobre : sur le devnet, ce stake peut être **parrainé**. Le
  mineur signe une demande, et le parrain enregistre le compte et dépose
  environ un million de FLOP, qui restent sa propriété et ne servent que de
  stake. Si ce mécanisme est repris sur le testnet, **il n'y aura rien à
  acheter**. Méfiance absolue envers quiconque propose de vendre des FLOP.

### Le jour J : mise en route

- [ ] Accès réseau : sur le devnet, la passerelle de Flop Labs joint le worker
  par un réseau privé Tailscale, en HTTPS sur le port 8645. Ne jamais exposer
  publiquement l'API du backend, qui n'a pas d'authentification.
- [ ] Démarrer le backend, attendre qu'il soit sain, puis démarrer le worker.
- [ ] **Calibration** : tant qu'elle n'est pas faite, le mineur ne reçoit aucune
  session. Sur le devnet, elle demande 64 tâches vérifiées sur au moins
  600 blocs finalisés, et elle expire au bout de sept jours.
- [ ] Ne plus arrêter le worker : une tâche sans réponse au-delà de 600 blocs
  (une dizaine de minutes avec des blocs d'une seconde) **expire et entraîne une
  sanction**.

### Pendant le testnet

- [ ] Tenir un journal quotidien : disponibilité, sessions servies, incidents.
- [ ] Suivre les canaux officiels : les règles bougent encore. En une semaine,
  le partage des paiements d'inférence est passé de 99 % à **85 %** pour le
  mineur (15 % pour les validateurs), et le parrainage du stake est apparu.

### Point ouvert pour une carte grand public

Ma 5070 Ti n'a pas d'environnement d'exécution de confiance (TEE) : elle relève
du niveau **SOFT**. La documentation du devnet le dit clairement : « SOFT is the
default tier and needs no confidential-computing hardware ». Mais deux réserves
demeurent : le registre des modèles exige encore un type de TEE, si bien qu'un
mineur SOFT reçoit son trafic par un routage hors chaîne, et le règlement des
paiements et litiges en SOFT n'est pas finalisé. La question est posée sur le
dépôt du Yellow Paper (issue #104) ; je mettrai l'article à jour quand l'équipe y
répondra.

## 6. Récapitulatif

- [ ] Médiane de plusieurs passages, premier passage écarté
- [ ] Un prompt différent à chaque série, pour ne pas mesurer le cache
- [ ] Test à 4 requêtes simultanées : c'est le débit total qui compte
- [ ] 24 heures à pleine charge : 0 erreur, débit stable, température stable
- [ ] Compteurs de ralentissement thermique à zéro, journal du noyau propre
- [ ] Consommation mesurée, coût estimé avant de s'engager pour 90 jours
- [ ] Checklist du jour J relue contre la documentation officielle à l'ouverture

## 7. La suite

- **Épisode 4** : l'ouverture du testnet, en direct, avec la checklist confrontée
  à la réalité.

Mon DID : `did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi`
Épisode 1 : [Technocore et DID](https://www.myprivatelab.tech/flop/technocore-did)
Épisode 2 : [Serveur Linux et GPU](https://www.myprivatelab.tech/flop/serveur-linux-gpu)
Me suivre : [@bvivi57](https://x.com/bvivi57) — le projet : [@flop_labs](https://x.com/flop_labs)

### Références

- Flop Network : <https://flop.finance>
- Yellow Paper (v0.5.0, brouillon) : <https://flop.finance/intro/yellowpaper/>
- Documentation opérateur (devnet) : <https://ask.flop.finance/docs/run-miner>
- Ollama : <https://github.com/ollama/ollama>
- Mes outils, dont `bench_ollama.py` : <https://github.com/bvivi57/flop>

*Mesures effectuées sur Rocky Linux 10.2 du 10 au 11 octobre 2026 ;
documentation du Flop Network consultée le 19 octobre 2026.*
