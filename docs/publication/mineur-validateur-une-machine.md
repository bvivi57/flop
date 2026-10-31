# Mineur et validateur sur la même machine : ce que demande Flop, ce que j'ai

*Épisode 4 de la série « Préparer un nœud mineur Flop sous Linux ».*

Les trois premiers épisodes ont préparé un **mineur** : une RTX 5070 Ti sous
Rocky Linux, mesurée puis testée 24 heures à pleine charge. Mais le testnet du
Flop Network a un deuxième rôle, celui de **validateur**, qui n'a besoin ni de
GPU ni d'enclave de confiance (TEE) : un processeur, de la mémoire, un disque
rapide et une bonne connexion. Ma machine en a beaucoup, et le GPU n'en utilise
qu'une partie.

D'où la question de cet épisode : **peut-on faire tourner les deux rôles sur un
seul serveur domestique ?** Je confronte ce que demande Flop à ce que j'ai,
critère par critère, puis je liste ce qu'il faut préparer avant l'ouverture et
ce qui reste inconnu.

> **Avertissement.** Au 31 octobre 2026, le testnet du Flop Network n'est pas
> ouvert et n'a pas de date officielle. Les exigences citées sont
> **provisoires**, et les procédures publiées concernent le **devnet** (le
> réseau de développement de l'équipe, sur invitation). Rien ne garantit une
> place ni une récompense.

---

## 1. Pourquoi y penser

Ce que les pages officielles disent au 31 octobre 2026 :

- **Le rôle** : un validateur produit les blocs (un par seconde), vote sur leur
  finalité, vérifie le travail des mineurs et stocke les poids des modèles dans
  la couche de disponibilité des données (DA). Aucun GPU, aucun TEE.
- **La cohorte de l'airdrop** : jusqu'à **1 000 sièges** de **1,2 million de
  FLOP** chacun (page Airdrop, mise à jour du 5 octobre). L'admission au set
  validateur du mainnet se fait sur le **classement du testnet**, et le set
  tourne ensuite d'environ 50 validateurs par mois.
- **Le coût d'entrée** : la page Testnet indique que la mise d'un mineur ou d'un
  validateur est **parrainée par le réseau**, et la décision D-0528 du Yellow
  Paper (20 octobre) l'inscrit dans le protocole pour le devnet et le testnet.
  Il n'y a rien à acheter. Depuis D-0530, il n'y a plus non plus de délégation :
  chaque validateur ne compte que sur sa propre mise.

Autrement dit, si la machine tient la charge, tenter le second rôle ne coûte que
de l'électricité et de l'attention.

## 2. Ce que demande Flop, face à ce que j'ai

Trois sources donnent des chiffres un peu différents : la page Testnet
(« provisoire »), la documentation validateur du devnet (« estimations de
planification ») et le profil de référence du Yellow Paper. J'ai mis la plus
exigeante en face de ma machine.

| Critère | Ce que demande Flop | Mon serveur | |
|---|---|---|---|
| Processeur | 8 cœurs **dédiés** (8+ cœurs sur la page Testnet) | Ryzen 9 7900X, 12 cœurs / 24 fils | ✅ mais partagé |
| Mémoire | 64 Go (page Testnet) ; 32 Go **ECC** (Yellow Paper) | 92 Go, **sans ECC** | ✅ / ⚠️ |
| Stockage | 4 To NVMe, DA comprise (**2 To minimum**) | WD SN580 2 To, grand public, vierge | ⚠️ minimum |
| Réseau | 1 Gb/s **redondant**, faible latence | Fibre 929 Mb/s descendant, 946 Mb/s montant, **un seul lien** | ✅ débit / ❌ redondance |
| Adresse | Joignable depuis Internet (P2P et DA) | IP fixe, serveur derrière la box | ✅ ports à ouvrir |

Ce que j'en retiens, point par point.

**Le processeur.** Pendant le test d'endurance de l'épisode 3, Ollama occupait
en moyenne l'équivalent de 6 fils d'exécution sur 24. Il en reste largement pour
un nœud validateur, mais pas « 8 cœurs dédiés » au sens strict. C'est le premier
point à surveiller : un validateur qui produit ses blocs en retard parce que le
mineur sature le processeur perd des places au classement.

**La mémoire.** 92 Go suffisent pour les deux rôles. En revanche, ma carte mère
et mes barrettes n'ont pas de correction d'erreurs (ECC). Le Yellow Paper la
recommande (« SHOULD »), sans l'exiger. Sans ECC, une erreur mémoire rare passe
inaperçue au lieu d'être corrigée. Pour un testnet, je l'accepte. Pour un
validateur de mainnet, la question se reposera.

**Le stockage.** Le WD SN580 de 2 To est exactement le minimum. Il est relié en
PCIe 4.0 x2 (environ 3,9 Go/s), ce qui suffit largement. Le risque est la place :
la couche DA garde des poids de modèles, et 2 To pourraient devenir justes.

**Le réseau.** C'est le vrai point faible. Le débit est là, dans les deux sens,
mais je n'ai **aucun accès de secours**. Une coupure de la fibre arrête les deux
rôles en même temps, et la disponibilité compte dans le classement validateur.
La page Testnet parle de connexion « redondante », sans dire si c'est éliminatoire.

## 3. Le réseau : quatre ports à ouvrir, un à protéger

La documentation validateur du devnet (mise à jour du 30 octobre) décrit un nœud
en Docker Compose, avec deux conteneurs : le nœud de la chaîne et un « worker »
DA. Sur le devnet actuel, tout passe par un réseau privé Tailscale fourni par
l'équipe. Pour le testnet public, un profil « P2P public + DA filtrée » est
préparé mais pas encore publié. Côté mineur, la doc du 30 octobre ouvre aussi
une voie **sans Tailscale** (sur invitation pour l'instant) : un nom DNS qui
pointe vers la machine, et les ports 80 et 443 ouverts pour un relais HTTPS
(Caddy, certificat Let's Encrypt).

| Port | Rôle | Exposition |
|---|---|---|
| **30333/tcp** | Validateur, P2P : pairs, production de blocs, finalité | Joignable depuis Internet |
| **7001/tcp** (ou 7000) | Validateur, DA : les autres validateurs lisent les données stockées | Joignable depuis Internet |
| **80 et 443/tcp** | Mineur, voie sans Tailscale : sessions HTTPS | Joignable depuis Internet |
| **9944/tcp** | RPC du nœud validateur | **Uniquement en local** (127.0.0.1) |

Le port DA n'est pas encore fixé : la doc du 30 octobre annonce **7001** dans
la liste des ports, mais son modèle de configuration garde `DA_PORT=7000`.
L'incohérence a été signalée publiquement (issue #10 du dépôt
`flop-labs/network`). Je redirigerai celui que le client du testnet utilisera.

Mon serveur a une adresse privée derrière la box. Avec une IP fixe, il suffira
de rediriger ces ports de la box vers le serveur, et de renseigner l'adresse
publique dans la configuration (`PUBLIC_ADDR`, `DA_PUBLIC_ENDPOINT` pour le
validateur, `SESSION_PUBLIC_HOST` pour le mineur). Une IP fixe évite aussi le
piège du CGNAT, où l'adresse publique est partagée entre plusieurs abonnés et où
aucune redirection n'est possible. Je vérifierai quand même, le jour J, depuis
une connexion extérieure, que chaque port répond.

**Le piège Docker.** Sur Rocky Linux, un port publié par Docker est ouvert
**sans passer par les zones de firewalld** : Docker écrit ses propres règles.
Fermer 9944 dans firewalld ne protège donc rien. La seule protection fiable est
de publier le RPC sur 127.0.0.1, ce que prévoit la configuration du devnet :

```bash
RPC_BIND_IP=127.0.0.1
RPC_METHODS=safe
```

Pour générer les clés de session, le RPC passe brièvement en mode `unsafe`.
Depuis la mise à jour du 30 octobre, c'est l'outil d'inscription
(`pnpm onboard join`) qui s'en charge et qui remet le mode `safe` avant de se
déclarer prêt. Le RPC doit rester en local pendant tout ce temps. C'est la même
logique côté mineur : le worker reste sur 127.0.0.1 (`SESSION_BIND_IP`), seul le
relais HTTPS est exposé.

## 4. Préparer le disque

Le SN580 a servi de disque Kubernetes dans une autre vie. Je l'ai inspecté puis
effacé le 12 octobre. Il est vierge. Pour
le préparer au rôle de validateur, je le formate en XFS et je le monte par son
UUID, avec `nofail` pour qu'un disque absent ne bloque pas le démarrage :

```bash
sudo mkfs.xfs -L flop /dev/disk/by-id/nvme-WD_Blue_SN580_2TB_<numéro-de-série>
echo "UUID=$(sudo blkid -s UUID -o value /dev/disk/by-id/nvme-WD_Blue_SN580_2TB_<numéro-de-série>) /srv/flop xfs defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo mkdir -p /srv/flop && sudo systemctl daemon-reload && sudo mount /srv/flop && df -h /srv/flop
```

Deux précautions, apprises sur cette machine :

- **Toujours passer par `/dev/disk/by-id/`**. Les noms `nvme0n1` / `nvme1n1`
  changent d'un démarrage à l'autre, et un `mkfs` sur le mauvais disque efface
  le système.
- **Vérifier que rien n'est monté** avant d'écrire : `findmnt -S <disque>` doit
  ne rien renvoyer.

Les volumes Docker du validateur iront sur `/srv/flop`, séparés des modèles du
mineur qui restent sur le disque système.

## 5. Les clés : deux rôles, deux identités

La documentation du devnet est claire sur quatre points :

- **Un compte par rôle.** Le mineur utilise un compte sr25519 dédié, distinct de
  celui du validateur.
- **Trois clés de session** pour le validateur : `babe` (production de blocs),
  `audi` (découverte des pairs) et `alp0` (finalité AlephBFT). Elles restent sur
  la machine.
- **Rien de secret ne sort.** On n'envoie à l'équipe que deux valeurs publiques :
  le nom d'hôte et l'adresse SS58 du compte (`pnpm onboard prepare` les
  affiche). L'équipe lit le reste directement sur la chaîne.
- **Jamais deux validateurs avec les mêmes clés.** Deux processus qui votent
  avec les mêmes clés produisent des votes contradictoires, et c'est sanctionné.
  Une machine de secours doit rester sans clés tant que l'originale tourne.

À sauvegarder, hors de la machine et chiffrés : la graine du compte, le
trousseau du nœud, la clé libp2p et les données du worker DA. Une simple copie
de la base de la chaîne ne suffit pas à restaurer un validateur.

## 6. Ce qui reste inconnu

- **L'admission.** La page Testnet dit que la participation est ouverte à
  quiconque a le matériel. Une décision du Yellow Paper (D-0507, non ratifiée)
  parle d'une cohorte de lancement de 20 à 50 validateurs ; la question est
  posée publiquement (issue #180 du dépôt du Yellow Paper), toujours sans
  réponse de l'équipe au 31 octobre. Un signe encourageant dans la doc du
  30 octobre : les demandes de parrainage validateur signées **pourront être
  admises automatiquement**, dans la limite de plafonds inscrits sur la chaîne,
  sans liste blanche. Les mineurs, eux, restent sur liste d'invitation.
- **Le contact.** Pour l'instant, il faut s'adresser aux « opérations » de
  l'équipe, mais aucun canal n'est publié, ni pour les validateurs (issue #10),
  ni pour les invitations mineur (issue #3 du dépôt `flop-labs/network`).
- **Le cumul des rôles.** Le Yellow Paper ne l'interdit nulle part. La seule
  règle relevée est « une clé de session par machine ». Le client du testnet
  dira si un mineur et un validateur peuvent partager une adresse IP.
- **La redondance réseau.** Recommandée ; éliminatoire ou non, on ne sait pas.
- **La procédure finale.** Sur le devnet, l'équipe finance et promeut chaque
  validateur à la main. La version « testnet public » de l'outil d'inscription
  existe (`pnpm onboard preflight --profile public-testnet`), mais elle refuse
  volontairement de démarrer tant que l'identité du réseau n'est pas publiée.

## 7. Mon verdict : oui, sous conditions, sans rien acheter

| Condition | État au 31/10/2026 |
|---|---|
| Disque de 2 To dédié | Vierge, prêt à formater |
| IP fixe et ports redirigés (30333, DA, 80/443) | IP fixe ✅, redirections à faire le jour J |
| RPC en local uniquement | Prévu dans la configuration |
| Comptes séparés mineur / validateur | À créer le jour J |
| Admission | Parrainage validateur automatique annoncé ; invitation mineur sans contact |
| Cumul autorisé par le client | Inconnu |
| Accès réseau de secours | Absent, rien acheté |

Je tenterai les deux rôles à l'ouverture si le client le permet. Si le
processeur ne suit pas, la priorité ira au mineur : c'est le rôle pour lequel
cette machine a été construite. Je n'achèterai ni disque de 4 To ni accès 4G/5G
de secours avant de lire la documentation validateur officielle du testnet.

## 8. La suite

- **Épisode 5** : l'ouverture du testnet, en direct, avec la checklist de
  l'épisode 3 et celle de cet article confrontées à la réalité.

Mon DID : `did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi`
Épisode 1 : [Technocore et DID](https://www.myprivatelab.tech/flop/technocore-did)
Épisode 2 : [Serveur Linux et GPU](https://www.myprivatelab.tech/flop/serveur-linux-gpu)
Épisode 3 : [Benchmarks, endurance et jour J](https://www.myprivatelab.tech/flop/benchmarks-soak-jour-j)
Me suivre : [@bvivi57](https://x.com/bvivi57) — le projet : [@flop_labs](https://x.com/flop_labs)

### Références

- Page Testnet : <https://flop.finance/testnet>
- Page Airdrop : <https://flop.finance/airdrop>
- Rôle de validateur : <https://flop.finance/intro/validator>
- Yellow Paper (v0.5.0, brouillon) : <https://flop.finance/intro/yellowpaper/>
- Procédure validateur (devnet) : <https://ask.flop.finance/docs/run-validator>
- Procédure mineur (devnet) : <https://ask.flop.finance/docs/run-miner>
- Issue sur l'admission des validateurs : <https://github.com/flop-labs/yellowpaper/issues/180>
- Retours sur le réseau en fonctionnement : <https://github.com/flop-labs/network/issues>

*Documentation du Flop Network consultée le 31 octobre 2026 ; constats
matériels relevés sur Rocky Linux 10.2 du 12 au 24 octobre 2026.*
