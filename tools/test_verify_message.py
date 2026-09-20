"""Tests de verify_message. Lancer depuis project-flop :

    python -m unittest discover -s tools
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import verify_message as vm

PROOF = Path(__file__).resolve().parent.parent / "proofs" / "lobby_intro_2026-09-15.json"
HAS_PROOF = PROOF.is_file()
needs_proof = unittest.skipUnless(
    HAS_PROOF, "preuve locale absente (proofs/lobby_intro_2026-09-15.json)"
)
OWN_DID = "did:key:z6MkgzG86nL4pgoytHsEUAshr24ByY8pvmRxYWFuVS2Y1DQi"
OWN_SEQ = 51043019
BASE64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def did_for(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    number = int.from_bytes(vm.MULTICODEC_ED25519 + raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = vm.BASE58BTC_ALPHABET[remainder] + encoded
    return vm.DID_PREFIX + "z" + encoded


def signed_message(
    private_key: Ed25519PrivateKey,
    room: str = "lobby",
    nonce: int = 1789499904476726300,
    text: str = "Bonjour Technocore",
) -> dict:
    signature = private_key.sign(f"{room}|{nonce}|{text}".encode("utf-8"))
    return {
        "seq": 1,
        "from": did_for(private_key),
        "nonce": nonce,
        "text": text,
        "sig": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def run_main(argv: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return vm.main(argv)


class CheckMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.message = signed_message(self.key)

    def test_valid_signature(self) -> None:
        self.assertEqual(vm.check_message("lobby", self.message), (vm.VALID, ""))

    def test_nonce_as_string_is_accepted(self) -> None:
        self.message["nonce"] = str(self.message["nonce"])
        self.assertEqual(vm.check_message("lobby", self.message)[0], vm.VALID)

    def test_tampered_text_is_invalid(self) -> None:
        self.message["text"] += "!"
        self.assertEqual(vm.check_message("lobby", self.message)[0], vm.INVALID)

    def test_other_room_is_invalid(self) -> None:
        self.assertEqual(vm.check_message("technocore", self.message)[0], vm.INVALID)

    def test_other_nonce_is_invalid(self) -> None:
        self.message["nonce"] += 1
        self.assertEqual(vm.check_message("lobby", self.message)[0], vm.INVALID)

    def test_other_did_is_invalid(self) -> None:
        self.message["from"] = did_for(Ed25519PrivateKey.generate())
        self.assertEqual(vm.check_message("lobby", self.message)[0], vm.INVALID)

    def test_malformed_did_is_invalid(self) -> None:
        self.message["from"] = "did:key:z6MkPasUnVraiDid"
        self.assertEqual(vm.check_message("lobby", self.message)[0], vm.INVALID)

    def test_unsigned_message(self) -> None:
        del self.message["sig"]
        self.assertEqual(vm.check_message("lobby", self.message)[0], vm.UNSIGNED)

    def test_non_canonical_signature_is_rejected(self) -> None:
        signature = self.message["sig"]
        last = BASE64URL_ALPHABET.index(signature[-1]) ^ 1
        with self.assertRaises(vm.VerificationError):
            vm.decode_signature(signature[:-1] + BASE64URL_ALPHABET[last])


class SourcesTest(unittest.TestCase):
    def test_utf16_file_from_powershell_is_read(self) -> None:
        message = signed_message(Ed25519PrivateKey.generate())
        response = {"room": "lobby", "count": 1, "last_seq": 1, "messages": [message], "posted": message}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "intro.json"
            path.write_bytes(json.dumps(response).encode("utf-16"))
            room, messages = vm.room_messages(vm.load_json_file(path))
        self.assertEqual(room, "lobby")
        self.assertEqual(messages, [message])

    @needs_proof
    def test_recorded_lobby_intro_is_valid(self) -> None:
        room, messages = vm.room_messages(vm.load_json_file(PROOF))
        own = [m for m in messages if m.get("seq") == OWN_SEQ]
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]["from"], OWN_DID)
        self.assertEqual(vm.check_message(room, own[0]), (vm.VALID, ""))


class ExportTest(unittest.TestCase):
    def setUp(self) -> None:
        key = Ed25519PrivateKey.generate()
        self.records = []
        for seq in (10, 11, 13):
            message = signed_message(key, nonce=1789499904476726300 + seq)
            message["seq"] = seq
            self.records.append(message)
        self.lines = [json.dumps(r).encode("utf-8") + b"\n" for r in self.records]

    def test_sequence_found_with_exact_big_nonce(self) -> None:
        record = vm.find_in_export(self.lines, 11)
        self.assertEqual(record["nonce"], 1789499904476726311)
        self.assertEqual(vm.check_message("lobby", record)[0], vm.VALID)

    def test_sequence_dropped_from_ring(self) -> None:
        with self.assertRaisesRegex(vm.SourceError, "plus conservee"):
            vm.find_in_export(self.lines, 5)

    def test_sequence_missing_inside_ring(self) -> None:
        with self.assertRaisesRegex(vm.SourceError, "introuvable"):
            vm.find_in_export(self.lines, 12)

    def test_export_size_is_bounded(self) -> None:
        with self.assertRaises(vm.SourceError):
            list(vm.bounded_lines(self.lines, max_bytes=10))


class FakeResponse:
    """Flux HTTP simule, eventuellement lent."""

    def __init__(self, blocks: list[bytes], delay: float = 0.0) -> None:
        self.blocks = list(blocks)
        self.delay = delay

    def read(self, _size: int) -> bytes:
        if self.delay:
            time.sleep(self.delay)
        return self.blocks.pop(0) if self.blocks else b""


class ReadWithDeadlineTest(unittest.TestCase):
    def test_body_is_reassembled(self) -> None:
        response = FakeResponse([b"une ", b"ligne\n", b"deux\n"])
        body = vm.read_with_deadline(response, max_bytes=1000, max_seconds=10)
        self.assertEqual(body, b"une ligne\ndeux\n")

    def test_slow_stream_is_abandoned(self) -> None:
        response = FakeResponse([b"a", b"b", b"c"], delay=0.05)
        with self.assertRaisesRegex(vm.SourceError, "trop lent"):
            vm.read_with_deadline(response, max_bytes=1000, max_seconds=0.01)

    def test_oversized_body_is_refused(self) -> None:
        response = FakeResponse([b"x" * 100, b"y" * 100])
        with self.assertRaisesRegex(vm.SourceError, "trop volumineux"):
            vm.read_with_deadline(response, max_bytes=150, max_seconds=10)


class MainTest(unittest.TestCase):
    def test_manual_exit_codes(self) -> None:
        message = signed_message(Ed25519PrivateKey.generate())
        argv = ["manual", "--room", "lobby", "--did", message["from"],
                "--nonce", str(message["nonce"]), "--sig", message["sig"]]
        self.assertEqual(run_main([*argv, "--text", message["text"]]), 0)
        self.assertEqual(run_main([*argv, "--text", message["text"] + " modifie"]), 1)

    @needs_proof
    def test_file_filter_on_own_did(self) -> None:
        self.assertEqual(run_main(["file", str(PROOF), "--did", OWN_DID]), 0)

    def test_unreadable_file_exit_code(self) -> None:
        self.assertEqual(run_main(["file", "/nonexistent/intro.json"]), 2)


if __name__ == "__main__":
    unittest.main()
