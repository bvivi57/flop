# Mon mineur Flop sur le devnet : trois jours pour un parrainage, vingt minutes pour la calibration

*Épisode 5 de la série « Préparer un nœud mineur Flop sous Linux ».*

Les quatre premiers épisodes ont préparé la machine : une RTX 5070 Ti sous
Rocky Linux, mesurée, testée 24 heures à pleine charge, puis confrontée aux
exigences d'un validateur. Il manquait l'essentiel : la faire tourner **sur un
vrai réseau Flop**.

C'est possible depuis le 3 novembre. Le testnet n'est pas encore ouvert, mais
l'équipe a ouvert au public son **devnet**, le réseau de développement. Selon
@flop_labs, il est « 100 % permissionless » : pas de candidature, il suffit de
suivre le guide. Je l'ai suivi. Voici le parcours complet, de l'installation à la
calibration acceptée sur la chaîne, avec les deux obstacles qui m'ont pris
presque tout le temps.

> **Avertissement.** Le devnet n'a **aucune valeur** et peut être réinitialisé.
> L'équipe l'a dit le 4 novembre : rien ne sera migré vers le testnet (« start
> fresh »). Ce qui suit ne rapporte rien. Ça valide la chaîne technique avant le
> jour J. Tous les chiffres datent du 3 au 5 novembre 2026.

---

## 1. Le parcours officiel, en cinq étapes

La page *run-miner* (mise à jour du 2 novembre) décrit un parcours entièrement
public :

1. **Installer le pack mineur** (`miner-pack-devnet-ts-20261103c`) : des scripts
   et un fichier Docker Compose avec deux conteneurs, le *worker* (il dialogue
   avec la chaîne et les clients) et le *backend* d'inférence (vLLM).
2. **Créer un compte mineur** sr25519 dédié, et le **financer au faucet** : 25 FLOP,
   une fois par 24 heures. Ces FLOP servent à payer les frais de transaction du
   mineur.
3. **Exposer le worker en HTTPS** sur Internet. Tailscale a été abandonné. On
   peut ouvrir les ports 80 et 443 pour le relais Caddy du pack, ou passer par son
   propre tunnel ou proxy vers le port 8645.
4. **Demander le parrainage** (`sponsor.sh`) : le réseau inscrit le mineur et
   bloque pour lui environ **1 million de FLOP de mise**. Personne n'a cette somme
   au faucet, et la calibration l'exige (voir § 4).
5. **Laisser le mineur se calibrer** : le worker déclare son GPU sur la chaîne,
   puis répond à 64 tâches de mesure. Si elles sont acceptées, la chaîne lui
   attribue une **capacité** en GFLOP/s.

Sur le papier, une heure de travail. En pratique, trois jours.

## 2. Installation : Rocky Linux sans conversion

Le pack vise Ubuntu, mais il tourne tel quel sur Rocky Linux 10.2, avec le Docker
et le NVIDIA Container Toolkit de l'épisode 2. Trois remarques :

- **vLLM prend 90 % de la VRAM.** Le modèle du devnet est petit (Qwen2.5-0.5B),
  mais le backend réserve presque toute la carte. J'ai arrêté Ollama pendant les
  essais : les deux ne cohabitent pas sur 16 Go.
- **Les secrets restent dans un dossier root en 700.** Le pack crée la clé du
  mineur, le trousseau et ses mots de passe dans son répertoire d'installation.
  Je n'en ai jamais rien copié ni affiché, et tous les scripts qui signent passent
  par l'image Docker officielle de la CLI, avec le fichier de clé monté en lecture
  seule.
- **Le pilote reste verrouillé.** Aucune mise à jour NVIDIA : une recalibration
  serait nécessaire à chaque changement de pilote.

## 3. Exposition : un proxy que j'avais déjà

Je n'ai ouvert aucun port sur la box. J'ai un Traefik qui sert déjà d'entrée HTTPS
à mon cluster Kubernetes, derrière Cloudflare. Il m'a suffi d'un sous-domaine
proxifié par Cloudflare, et d'une route Traefik vers le port 8645 du serveur, en
HTTP sur le réseau local.

Le **piège Docker** de l'épisode 4 joue ici dans l'autre sens : un port publié par
Docker est ouvert sans passer par les zones de firewalld. Je n'ai donc rien eu à
ouvrir dans le pare-feu pour le 8645. C'est justement pour ça qu'il faut savoir
exactement ce que Docker publie.

Vérification : depuis l'extérieur, le worker répond `401` sans jeton. C'est la
bonne réponse, il est joignable et il refuse les inconnus.

## 4. Premier obstacle : le parrainage saturé

Faucet passé, mineur exposé, worker démarré : la demande de parrainage revient
en **429**. Pendant trois jours, j'ai vu passer trois raisons successives :

1. **3 novembre, ~13:20 UTC → 4 novembre ~09:00 UTC** : *« sponsor signer balance
   is too low »*. Le compte du parrain était vide. L'équipe l'a rechargé le 4.
2. **À partir du 4 novembre 09:05 UTC** : *« at most 3 automatically sponsored
   miners may be uncalibrated at once »*. Au plus trois mineurs parrainés peuvent
   être en cours de calibration en même temps. Or deux des trois places étaient
   tenues par des mineurs qui n'avaient **jamais tenté** de se calibrer : un autre
   opérateur l'a montré en lisant la chaîne.
3. **5 novembre ~08:50 UTC** : une seconde limite, *« daily limit »*, au plus **10
   nouveaux parrainages par 24 heures glissantes**. Elle s'ajoutait au plafond,
   relevé entre-temps de 3 à 6 places.

Pourquoi ne pas s'inscrire sans parrain ? La chaîne le permet avec 10 000 FLOP de
mise propre, mais la calibration réclame une caution d'environ **7 560 FLOP par
GFLOP/s** de capacité. Le parrainage d'un million de FLOP correspond à environ
130 GFLOP/s. Sans lui, on ne passe pas.

**Ce que j'ai mis en place pour ne pas rater une place**, en lecture seule sur la
chaîne :

- un script de fond qui retente toutes les heures, et vérifie toutes les 5 minutes
  s'il reste une place libre. Il fait une pause d'une heure quand la limite des
  24 heures est atteinte ;
- un second script qui relit l'état des places sur la chaîne environ une fois par
  seconde. Il n'envoie une demande signée que si une place **et** le quota des
  24 heures sont libres. Il relit les limites dans chaque réponse 429 et me
  signale tout changement. Il est volontairement bridé : une demande toutes les
  2 secondes au plus, 100 par heure.

Les places libérées partaient en 6 à 20 secondes, alors que le faucet met 8 à
20 secondes à répondre. Finalement, l'équipe a **relevé les deux limites** sans
annonce, le 5 novembre vers 14:09 UTC. Ma demande suivante est passée :
**parrainé à 14:10:52 UTC**, 1 000 000 FLOP délégués au mineur.

## 5. Second obstacle : le verrou du signataire

Le mineur est parrainé, je redémarre le worker pour qu'il déclare son GPU. Rien
ne part. Dans les journaux :

```
[gpu] inventory declaration failed: miner signer is fenced after an
unclassified submission failure; reconcile before restart
```

L'explication vient de mon tout premier démarrage, le 3 novembre, avant le
passage au faucet. Le worker avait tenté de déclarer le GPU avec un compte vide,
et la chaîne avait refusé (`1010: Inability to pay some fees`). Par prudence, le
worker pose alors un **verrou** : un petit fichier dans son état local, qui bloque
toute nouvelle transaction du compte mineur tant que l'opérateur n'a pas
« réconcilié ». C'est une bonne idée : sans ce verrou, une transaction au sort
incertain pourrait partir deux fois. Mais un refus net comme le 1010 est traité
comme un sort incertain, et le verrou survit aux redémarrages.

Ma réconciliation, faite à la main (aucun outil officiel n'existe à ce jour) :

1. **Vérifier que rien n'est passé** : le *nonce* du compte mineur sur la chaîne
   (le nombre de transactions déjà incluses) était toujours 0, et rien n'attendait
   dans la file des transactions. La déclaration refusée n'avait donc jamais été
   incluse.
2. **Déplacer le fichier de verrou** hors du dossier d'état du worker, en en
   gardant une copie.
3. **Redémarrer le worker.**

**L'étape 1 est la seule importante.** Si le nonce avait bougé, la transaction
aurait pu passer, et supprimer le verrou à l'aveugle aurait annulé la protection.

Je ne suis pas le seul : le même jour, un autre opérateur a décrit exactement ce
cas, avec la même version du pack (issue #94 du dépôt `flop-labs/network`).

## 6. La calibration : vingt minutes

Le verrou retiré, tout s'enchaîne. Le worker déclare le GPU, répond aux 64 tâches
de mesure, et la chaîne accepte la calibration vers **14:30 UTC** :

| Champ | Valeur |
|---|---|
| Capacité | **130 GFLOP/s** |
| Niveau d'assurance | `Soft` (sans TEE) |
| Tâches vérifiées | 64 |
| Bloc d'acceptation | 2 965 652 |
| Transactions du compte | 2 (déclaration GPU, calibration) |
| Frais payés | ~1 FLOP |

Quelques points pour bien lire ce tableau :

- **130 GFLOP/s n'est pas une mesure de la carte.** C'est le plafond que la
  caution parrainée autorise. La plupart des mineurs calibrés du devnet affichent
  la même valeur.
- **`Soft`** : c'est le niveau de tous les mineurs du devnet. La chaîne ne connaît
  pas encore de plafond par modèle de GPU, donc aucun ne peut être attesté plus haut.
- **La calibration expire** au bout d'environ 7 jours (604 800 blocs). Le mineur
  doit rester allumé pour la renouveler.
- **Pas encore de vrai travail.** Aucun modèle n'est enregistré pour les mineurs
  sur le réseau, et les sessions payantes ne sont pas ouvertes. Être calibré ne
  suffit donc pas à recevoir des requêtes.

## 7. Ce que j'en retiens pour le testnet

| Leçon | Au jour J |
|---|---|
| Le compte mineur paie ses frais | Passer au faucet **avant** le premier démarrage |
| Un refus de frais verrouille le signataire | Démarrer le worker **après** le parrainage ; sinon, vérifier le nonce avant de retirer le verrou |
| Les places de parrainage partent en secondes | Préparer la demande à l'avance, et surveiller la chaîne plutôt que les annonces |
| Les limites changent sans annonce | Relire chaque réponse 429 au lieu de supposer |
| vLLM réserve 90 % de la VRAM | Pas d'Ollama à côté sur une carte de 16 Go |
| Un proxy HTTPS existant suffit | Pas de 80/443 à ouvrir sur la box |

Le devnet ne m'a rien rapporté, et il disparaîtra au lancement du testnet. Mais
le parcours est validé de bout en bout sur ma machine : installation, exposition,
faucet, parrainage, déclaration du GPU et calibration. Le jour J, il ne restera
qu'à le refaire, plus vite.

## 8. La suite

- **Épisode 6** : l'ouverture du testnet. Selon Arthur Hayes, sa date doit être
  décidée « en début de semaine prochaine », soit la semaine du 9 novembre.

Mon DID : `did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi`
Épisode 1 : [Technocore et DID](https://www.myprivatelab.tech/flop/technocore-did)
Épisode 2 : [Serveur Linux et GPU](https://www.myprivatelab.tech/flop/serveur-linux-gpu)
Épisode 3 : [Benchmarks, endurance et jour J](https://www.myprivatelab.tech/flop/benchmarks-soak-jour-j)
Épisode 4 : [Mineur et validateur sur la même machine](https://www.myprivatelab.tech/flop/mineur-validateur-une-machine)
Me suivre : [@bvivi57](https://x.com/bvivi57) — le projet : [@flop_labs](https://x.com/flop_labs)

### Références

- Procédure mineur (devnet) : <https://docs.flop.network/docs/run-miner>
- Explorateur du devnet (mineurs) : <https://explorer.devnet.flop.network/mining>
- Retours sur le devnet, dont le parrainage saturé : <https://github.com/flop-labs/network/issues/37>
- Le verrou du signataire : <https://github.com/flop-labs/network/issues/94>
- Annonce « start fresh » : <https://x.com/flop_labs/status/2117971590122229936>

*Parcours réalisé du 3 au 5 novembre 2026 sur Rocky Linux 10.2 (pack
`miner-pack-devnet-ts-20261103c`, worker 0.1.238, backend 0.1.239) ; état de la
chaîne devnet relevé le 5 novembre 2026.*
