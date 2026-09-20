#!/usr/bin/env python3
"""Verifie les signatures Ed25519 des messages Technocore, sans cle privee.

Un message signe couvre exactement `salon|nonce|texte` : la verification
n'utilise que le DID public de l'auteur. Trois sources sont possibles :

  file    un fichier JSON renvoye par Technocore (commande read ou say)
  fetch   un message lu en direct sur le serveur, par salon et sequence
  manual  les champs saisis a la main

Le serveur ne conserve qu'un historique limite par salon (~10 Mio). Mesure du
16/09/2026 : lobby ne gardait que 17 056 messages, soit 16,6 minutes a 17 msg/s.
Garder le JSON renvoye au moment de l'envoi reste la seule preuve durable.

Code de sortie : 0 si tous les messages sont valides, 1 si au moins un est
invalide ou non signe, 2 si la source est illisible ou le message introuvable.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "1.1.0"
DEFAULT_BASE_URL = "https://technocore.chat"
DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_EXPORT_BYTES = 64 * 1024 * 1024
EXPORT_CHUNK_BYTES = 1024 * 1024
DEFAULT_MAX_SECONDS = 60.0
MAX_READ_LIMIT = 200

DID_PREFIX = "did:key:"
MULTIBASE_LENGTH = 48
MULTICODEC_ED25519 = b"\xed\x01"
BASE58BTC_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ROOM_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
NONCE_PATTERN = re.compile(r"[0-9]{1,19}")
SIGNATURE_PATTERN = re.compile(r"[A-Za-z0-9_-]{86}")

VALID = "VALIDE"
INVALID = "INVALIDE"
UNSIGNED = "NON SIGNE"


class VerificationError(ValueError):
    """Le message est mal forme ou sa signature ne correspond pas."""


class SourceError(RuntimeError):
    """Le fichier ou la reponse du serveur est illisible, ou le message absent."""


def safe(value: Any, limit: int = 120) -> str:
    """Rend une valeur non fiable affichable, sans caracteres de controle."""
    text = "".join(c if c.isprintable() else "?" for c in str(value))
    return text if len(text) <= limit else text[: limit - 1] + "..."


def public_key_from_did(did: Any) -> Ed25519PublicKey:
    """Extrait la cle publique Ed25519 d'un did:key canonique."""
    if not isinstance(did, str) or not did.startswith(DID_PREFIX + "z6Mk"):
        raise VerificationError("DID attendu au format did:key:z6Mk...")
    multibase = did[len(DID_PREFIX) :]
    if len(multibase) != MULTIBASE_LENGTH:
        raise VerificationError("DID de longueur invalide pour une cle Ed25519")
    number = 0
    for character in multibase[1:]:
        digit = BASE58BTC_ALPHABET.find(character)
        if digit < 0:
            raise VerificationError(
                f"caractere base58 invalide dans le DID : {safe(character)!r}"
            )
        number = number * 58 + digit
    try:
        decoded = number.to_bytes(34, "big")
    except OverflowError as error:
        raise VerificationError("DID trop long pour une cle Ed25519") from error
    if not decoded.startswith(MULTICODEC_ED25519):
        raise VerificationError("le DID ne contient pas une cle ed25519-pub")
    try:
        return Ed25519PublicKey.from_public_bytes(decoded[2:])
    except ValueError as error:
        raise VerificationError("le DID contient une cle Ed25519 invalide") from error


def decode_signature(signature: Any) -> bytes:
    """Decode une signature base64url de 86 caracteres, forme canonique exigee."""
    if not isinstance(signature, str) or SIGNATURE_PATTERN.fullmatch(signature) is None:
        raise VerificationError(
            "signature attendue : 86 caracteres base64url sans padding"
        )
    raw = base64.urlsafe_b64decode(signature + "==")
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != signature:
        raise VerificationError("signature base64url non canonique")
    return raw


def signed_payload(room: Any, nonce: Any, text: Any) -> bytes:
    """Reconstruit les octets exacts signes par l'auteur : salon|nonce|texte."""
    if not isinstance(room, str) or ROOM_PATTERN.fullmatch(room) is None:
        raise VerificationError("nom de salon invalide")
    if (
        isinstance(nonce, bool)
        or not isinstance(nonce, (int, str))
        or NONCE_PATTERN.fullmatch(str(nonce)) is None
    ):
        raise VerificationError("nonce attendu : 1 a 19 chiffres")
    if not isinstance(text, str) or not text:
        raise VerificationError("texte du message manquant")
    return f"{room}|{nonce}|{text}".encode("utf-8")


def verify_message(room: str, message: dict[str, Any]) -> None:
    """Leve VerificationError si la signature ne correspond pas au message."""
    public_key = public_key_from_did(message.get("from"))
    raw_signature = decode_signature(message.get("sig"))
    payload = signed_payload(room, message.get("nonce"), message.get("text"))
    try:
        public_key.verify(raw_signature, payload)
    except InvalidSignature as error:
        raise VerificationError(
            "la signature ne correspond pas a ce DID, ce salon, ce nonce et ce texte"
        ) from error


def check_message(room: str, message: dict[str, Any]) -> tuple[str, str]:
    """Classe un message en VALIDE, INVALIDE ou NON SIGNE, avec le motif."""
    if not message.get("sig"):
        return UNSIGNED, "aucune signature : l'auteur n'est pas prouve"
    try:
        verify_message(room, message)
    except VerificationError as error:
        return INVALID, str(error)
    return VALID, ""


def load_json_file(path: Path) -> Any:
    """Lit un JSON en UTF-8 ou en UTF-16 (redirection `>` de PowerShell 5.1)."""
    try:
        raw = path.expanduser().read_bytes()
    except OSError as error:
        raise SourceError(f"lecture impossible de {path} : {error}") from error
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        return json.loads(raw.decode(encoding))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceError(f"{path} n'est pas un JSON lisible : {error}") from error


def room_messages(response: Any) -> tuple[str, list[dict[str, Any]]]:
    """Extrait le salon et les messages d'une reponse Technocore, sans doublon."""
    if not isinstance(response, dict) or not isinstance(response.get("room"), str):
        raise SourceError("reponse Technocore attendue : objet JSON avec un champ room")
    messages = response.get("messages", [])
    if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
        raise SourceError("le champ messages doit etre une liste d'objets")
    posted = response.get("posted")
    if isinstance(posted, dict) and all(m.get("seq") != posted.get("seq") for m in messages):
        messages = [*messages, posted]
    return response["room"], messages


def find_in_export(lines: Iterable[bytes], seq: int) -> dict[str, Any]:
    """Cherche une sequence dans l'export JSONL d'un salon, trie par seq croissant."""
    oldest: int | None = None
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceError("export Technocore illisible") from error
        record_seq = record.get("seq") if isinstance(record, dict) else None
        if isinstance(record_seq, bool) or not isinstance(record_seq, int):
            raise SourceError("export Technocore : enregistrement sans sequence")
        if oldest is None:
            oldest = record_seq
        if record_seq == seq:
            return record
        if record_seq > seq:
            break
    if oldest is not None and oldest > seq:
        raise SourceError(
            f"sequence {seq} plus conservee par le serveur (la plus ancienne est "
            f"{oldest}) ; verifie le JSON enregistre avec la commande file"
        )
    raise SourceError(f"sequence {seq} introuvable dans l'historique conserve")


def validate_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise SourceError("l'URL du serveur doit etre en HTTPS")
    return base_url.rstrip("/")


def open_url(url: str, timeout: float, accept: str) -> Any:
    request = Request(
        url,
        headers={"Accept": accept, "User-Agent": f"project-flop-verify-message/{VERSION}"},
    )
    try:
        return urlopen(request, timeout=timeout)
    except HTTPError as error:
        raise SourceError(f"Technocore a repondu HTTP {error.code}") from error
    except (URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise SourceError(f"Technocore injoignable : {safe(reason)}") from error


def read_with_deadline(
    response: Any, max_bytes: int, max_seconds: float, chunk: int = EXPORT_CHUNK_BYTES
) -> bytes:
    """Telecharge un corps en entier, borne en taille et en duree totale.

    L'export de Technocore repond parfois en une seconde et parfois en plusieurs
    minutes pour les memes octets. Le delai du socket ne couvre pas un flux lent
    mais regulier : cette limite globale evite d'attendre indefiniment.
    """
    started = time.monotonic()
    parts: list[bytes] = []
    total = 0
    while True:
        if time.monotonic() - started > max_seconds:
            raise SourceError(
                f"export Technocore trop lent (plus de {max_seconds:g} s) ; "
                "reessaie plus tard ou verifie le JSON enregistre avec la commande file"
            )
        block = response.read(chunk)
        if not block:
            return b"".join(parts)
        total += len(block)
        if total > max_bytes:
            raise SourceError("export Technocore trop volumineux")
        parts.append(block)


def bounded_lines(response: Iterable[bytes], max_bytes: int) -> Iterator[bytes]:
    total = 0
    for line in response:
        total += len(line)
        if total > max_bytes:
            raise SourceError("export Technocore trop volumineux")
        yield line


def fetch_message(
    room: str,
    seq: int,
    base_url: str,
    timeout: float,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> dict[str, Any]:
    """Lit un seul message sur le serveur ; son contenu reste non fiable."""
    if ROOM_PATTERN.fullmatch(room) is None:
        raise SourceError("nom de salon invalide")
    if seq < 1:
        raise SourceError("la sequence doit etre superieure a zero")
    base = validate_base_url(base_url)
    query = urlencode({"format": "json", "since": seq - 1, "limit": MAX_READ_LIMIT})
    try:
        with open_url(f"{base}/r/{room}?{query}", timeout, "application/json") as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise SourceError("reponse Technocore trop volumineuse")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceError("Technocore a renvoye une reponse non JSON") from error
        response_room, messages = room_messages(payload)
        if response_room != room:
            raise SourceError("Technocore a renvoye les donnees d'un autre salon")
        for message in messages:
            if message.get("seq") == seq:
                return message
        # La lecture ne renvoie que les messages les plus recents apres `since` :
        # un message plus ancien se cherche dans l'historique conserve. L'export est
        # telecharge d'un bloc puis decoupe en memoire (~10 Mio, environ 1 s) : le
        # lire par petits morceaux, ou s'arreter au milieu en laissant la connexion
        # se fermer sur des donnees non lues, coute plus d'une minute.
        with open_url(f"{base}/r/{room}/export", timeout, "application/x-ndjson") as response:
            body = read_with_deadline(response, MAX_EXPORT_BYTES, max_seconds)
        return find_in_export(bounded_lines(body.splitlines(), MAX_EXPORT_BYTES), seq)
    except OSError as error:
        raise SourceError(f"lecture Technocore interrompue : {safe(error)}") from error


def report(room: str, messages: Iterable[dict[str, Any]]) -> int:
    """Affiche une ligne par message et renvoie le code de sortie."""
    counts = {VALID: 0, INVALID: 0, UNSIGNED: 0}
    for message in messages:
        status, reason = check_message(room, message)
        counts[status] += 1
        line = (
            f"{status:<9}  {safe(room)} #{safe(message.get('seq', '-'))}  "
            f"{safe(message.get('from'), 64)}"
        )
        print(f"{line}  ({reason})" if reason else line)
    total = sum(counts.values())
    if total == 0:
        print("aucun message ne correspond aux filtres", file=sys.stderr)
        return 1
    print(
        f"{total} message(s) : {counts[VALID]} valide(s), "
        f"{counts[INVALID]} invalide(s), {counts[UNSIGNED]} non signe(s)",
        file=sys.stderr,
    )
    return 0 if counts[VALID] == total else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_message.py",
        description="Verifie des messages Technocore a partir du seul DID public.",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    file_parser = commands.add_parser(
        "file", help="verifier un JSON enregistre (reponse de read ou say)"
    )
    file_parser.add_argument("path", type=Path)
    file_parser.add_argument("--seq", type=int, help="ne verifier que cette sequence")
    file_parser.add_argument("--did", help="ne verifier que les messages de ce DID")

    fetch_parser = commands.add_parser(
        "fetch", help="lire un message encore conserve par le serveur et le verifier"
    )
    fetch_parser.add_argument("room")
    fetch_parser.add_argument("seq", type=int)
    fetch_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    fetch_parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    fetch_parser.add_argument(
        "--max-seconds",
        type=float,
        default=DEFAULT_MAX_SECONDS,
        help="duree totale maximale du telechargement de l'historique",
    )

    manual_parser = commands.add_parser(
        "manual", help="verifier des champs saisis a la main"
    )
    manual_parser.add_argument("--room", required=True)
    manual_parser.add_argument("--did", required=True)
    manual_parser.add_argument("--nonce", required=True)
    manual_parser.add_argument("--sig", required=True)
    manual_parser.add_argument(
        "--text", required=True, help="texte exact tel que stocke par le serveur"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "file":
            room, messages = room_messages(load_json_file(args.path))
            selected = [
                m
                for m in messages
                if (args.seq is None or m.get("seq") == args.seq)
                and (args.did is None or m.get("from") == args.did)
            ]
            return report(room, selected)
        if args.command == "fetch":
            message = fetch_message(
                args.room, args.seq, args.base_url, args.timeout, args.max_seconds
            )
            return report(args.room, [message])
        message = {"from": args.did, "nonce": args.nonce, "sig": args.sig, "text": args.text}
        return report(args.room, [message])
    except SourceError as error:
        print(f"erreur : {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
