# Generated from literate/71-tests-identity.md by opensheaf-literate: edit the document, not this file.
"""Tests of names, owners, keys and signatures (OpenSheaf 0.2), against the
examples of appendix C of the specification."""

import base64
import copy
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest
from nacl import pwhash
from nacl.signing import VerifyKey

from opensheaf import keys, names, owners, sign

A = "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa"     # the authors' owner
J = "tqr6lchnd2vk7ezskdc5zdxpaidpsiuduo5sqhiis3i55iautdka"     # the journal's owner
N = "zzgdggwlldcrw4bdeuvntiaobtw2kge6bc4go737pfekhfc5oz4q"     # the paper
N1 = "aajozkubvmxu37pbu2lumdl37llv4ntkazd6j2es54zn23fkiknb"    # the paper, by algorithm 1
C = "kdye5s4igsyn6i6c46lqhercobkiv5avkepkdy6hcs6wr2pakxeq"     # the main catalogue
ORCID_A = "https://orcid.org/0000-0002-1234-5677"
KL1 = ("afaabe7b9489bc408ecbb20e8477a7eeb4e8a0ebde0dc15e32d30be17d922207"
       "504953e3e52101015f770844449c8382c4c4d9bec472a908ed47200efaef1220")
KL2 = ("7673bfae6ba91f6e9acf862635649efde7b6af0e1a787f6dc2cb2f2a583d5d4f"
       "ab7bf236f7284582a4894aebef2769eacbf69d9036f1ecd4f89c07bc31313f84")
KL3 = ("d006b40d988e88c16cfe7d83d81c5b8a0cb318daad1a78180566568c2553f4b7"
       "ef7de1d3ebadd785fba94bb3648e70d6a8f8b40cb8a7cfdd913fc76ba959ce7e")
KL3T = ("58415b38113b6fffbb302784e338c95d955537aa29f2bdea6e10fd9b237418f9"
        "89cda4f10ae7ab32288b7421a9e0a1cc1e3b02c6d01df1a3117793aed56aab3a")
KL4 = ("95db6b39532bf52a003dce5b79ad012a365823331123cbb8c234d57caa424af0"
       "b8a102e5ef39e41dfdb5da521283307edc0af26150313db594a1ad398aa221da")
JL1 = ("c2fea5c6cefaa97afaa689a4d8fea511d760741d1f1ae8c8cf3758b7ad32878f"
       "ee0f82a33b646536311cd6358a0a79a1480fa80498681e5aa383acb5801c66c7")
D1 = ("a6a22e10cf4bf5a611a9e708b19d22e2f6edc8a5d7d9b09750a8fcec3c396fa4"
      "68d4d06cc5e1d695a262222cb94f084a2c9ea269dee1580c66f54d0dd7da8d04")
D2 = ("e3e1319055b967af645713c3baa4dc1974eb8ce02f6b2591bbcce55b068e7a98"
      "df54dfa8ab2fd8996d27a2b31df8bee814281d681187014eaa0316f048edbb25")
D3T = "f35la3m3ue36z36u"
TIMESTAMPS = {"https://opensheaf.org/opensheaf-timestamps-0.2": {"timestampAuthorities": [
    "5b4e3f0c9d2a7e18c6f4b0a39d7e2c51f8a6b3d09e4c7a12f5b8d6e3a0c9f147"]}}
USER_A = {"name": "Massimiliano Gubinelli", "address": ORCID_A}

K = keys.example_key
K1, K3, K5 = K("authors laptop"), K("authors new laptop"), K("authors third laptop")
T, TR = K("thief"), K("thief rotation")
R = [None] + [K(f"authors rotation {i}") for i in range(1, 10)]


def nonce(label):
    return hashlib.sha256(("nonce " + label).encode()).hexdigest()[:32]


def authors_log(upto=3):
    log = owners.new_owner([K1], [R[1], R[2], R[3]], threshold=1, next_threshold=2, keeper=ORCID_A,
                           extensions=TIMESTAMPS, created="2026-03-01T17:40:00Z", nonce=nonce("A"))
    if upto >= 2:
        log.rotate([R[1], R[2]], add=[K3], retire=[K1.did], next_keys=R[4:7], next_threshold=2,
                   message="Laptop replaced: key added, old key retired", user=USER_A,
                   created="2026-06-10T08:00:00Z")
    if upto >= 3:
        log.expose([R[4], R[5]], [K3.did], add=[K5], next_keys=R[7:10], next_threshold=2,
                   message="Laptop stolen: its key exposed, a new key", user=USER_A,
                   created="2026-11-02T10:00:00Z")
    return log


def thief_v3(exposed=()):
    log = owners.KeyLog(authors_log(2).genesis, copy.deepcopy(authors_log(2).versions))
    return log.rotate([R[5], R[6]], add=[T], retire=[K3.did], exposed=exposed, next_keys=[TR],
                      next_threshold=1, extensions=None, message="Keys changed",
                      user={"name": "M. Gubinelli"}, created="2026-11-03T03:12:00Z")


def forked_log(exposed=()):
    log = authors_log(3)
    log.record_fork([thief_v3(exposed)], user={"name": "Papers of Massimiliano Gubinelli"},
                    message="Fork record: another version 3 met", created="2026-11-05T12:00:00Z")
    return log


def test_owner_names_of_appendix_c():
    log = authors_log(1)
    assert log.owner == A and names.name(log.genesis) == A
    assert log.genesis.startswith(b'{\n  "format": "opensheaf-genesis/0.2",\n  "kind": "owner",\n')
    rec = names.read_genesis(log.genesis)
    assert rec["next"] == [R[1].digest, R[2].digest, R[3].digest] and rec["keeper"] == [ORCID_A]
    journal = owners.new_owner([K("journal 1"), K("journal 2"), K("journal 3")],
                               [K(f"journal rotation {i}") for i in (1, 2, 3)], threshold=2,
                               keeper="https://journal.example.org/", created="2026-01-15T10:00:00Z",
                               nonce=nonce("J"))
    assert journal.owner == J and journal.versions[0].digest == JL1


def test_document_names_and_algorithms():
    g = names.genesis_record("document", originator=A, created="2026-03-02T09:14:00Z", nonce=nonce("N"))
    assert g == (b'{\n  "format": "opensheaf-genesis/0.2",\n  "kind": "document",\n'
                 b'  "created": "2026-03-02T09:14:00Z",\n  "originator": "' + A.encode() + b'",\n'
                 b'  "nonce": "6f65cd32058c16d6d78b05011772ff1d"\n}\n')
    assert names.name(g) == N and names.name(g, 1) == N1
    all16 = [names.name(g, k) for k in range(16)]
    assert len(set(all16)) == 16 and [names.algorithm(n) for n in all16] == list(range(16))
    assert all(names.is_name_of(n, g) for n in all16) and not names.is_name_of(A, g)
    assert names.OWNER_NAME.match(N) and not names.OWNER_NAME.match(N1)
    c = names.genesis_record("collection", originator=A, created="2026-03-02T09:30:00Z", nonce=nonce("C"))
    assert names.name(c) == C
    with pytest.raises(ValueError):
        names.name(g, 16)


def test_genesis_records_are_checked(tmp_path):
    with pytest.raises(ValueError):
        names.genesis_record("owner", originator=A, keys=[K1.did], threshold=1,
                             next_digests=[R[1].digest], next_threshold=1)
    with pytest.raises(ValueError):
        names.genesis_record("document", originator=A, keys=[K1.did])
    with pytest.raises(ValueError):
        names.genesis_record("document", originator=N1)
    for kw in ({"threshold": 2}, {"next_threshold": 2}, {"next_digests": [K1.digest]},
               {"keeper": "https://orcid.org/0000-0002-1234-5678"}):
        args = dict(keys=[K1.did], threshold=1, next_digests=[R[1].digest], next_threshold=1)
        args.update(kw)
        with pytest.raises(ValueError):
            names.genesis_record("owner", **args)
    g = names.genesis_record("document", originator=A)
    rec = names.read_genesis(g)
    assert len(rec["nonce"]) == 32 and rec["created"].endswith("Z")
    assert names.genesis_record("document", originator=A) != g
    with pytest.raises(ValueError):
        names.read_genesis(b"\xef\xbb\xbf" + g)
    names.write_genesis(tmp_path / "genesis.json", g)
    with pytest.raises(FileExistsError):
        names.write_genesis(tmp_path / "genesis.json", g)


def test_did_keys_of_appendix_c():
    expected = {
        K1: ("did:key:z6MksKLDefPeXwhL6SJCLqpW1dGZcvBjfsv9mxGCFpMkMuVW", "w7htq42yt7tllefi"),
        K3: ("did:key:z6MkugKqPPkysjyartSzszBbMh8fVhENmqGXvddtD8DDvThn", "4hz7zgsiazl6hx7i"),
        K5: ("did:key:z6MkteCfnkhWgCnLtR7Wdzi81tk4FDb9Juk5CxgjqCRo4UHJ", "gfa3pywxqreot3xs"),
        R[1]: ("did:key:z6Mkh5i2epG9LsWNnYbBHG7ctEiNLZPjsBNXxNUcsaYgEtNm", "oxthfb6b4q3sqath"),
        R[2]: ("did:key:z6Mks6ftndAzXUHxbN65ePQ9hGK41r2zBzUeF5MFUZvW5GXs", "h6k4k6c5u4dusj4s"),
        R[4]: ("did:key:z6MksaMy3cmXbnUKqzGv18xhbBreY6berNYVtTZyDrYRb1Hn", "j77iavvdclktxkwm"),
        R[5]: ("did:key:z6Mkpaxp735EvUsV352jLr1ivKTiAoqNv19gPqEZAYNgXk6x", "nzvwkea25p62akdy"),
    }
    for key, (did, kid) in expected.items():
        assert key.did == did and key.id == kid and names.key_id(did) == kid
        assert names.did_key_public(did) == key.public
        assert sign.file_name(did) == f"signature-{kid}.json"
    assert R[1].digest == "oxthfb6b4q3sqathmcpnciqggfxlr3aekgfg2tpm2lgrm2qnalha"
    assert R[6].digest.startswith("fhujijfn3zmvteie")
    assert "@" not in repr(K1) and base64.b64encode(K1.seed).decode() not in repr(K1)
    bad = ["did:key:z" + names.b58encode(b"\xec\x01" + K1.public),     # X25519, not Ed25519
           "did:key:z" + names.b58encode(b"\xed\x01" + K1.public[:31]),
           "did:key:z1" + K1.did[len("did:key:z"):],                    # a leading zero byte
           K1.did.replace("6Mk", "6M0"), "did:web:example.org"]
    for did in bad:
        with pytest.raises(ValueError):
            names.did_key_public(did)


def test_base58_and_base32():
    for data in (b"", b"\0", b"\0\0\x01", b"hello", bytes(range(40))):
        assert names.b58decode(names.b58encode(data)) == data
        assert names.b32decode(names.b32(data)) == data
        assert names.b32decode(names.b32(data).upper()) == data
    assert names.b58encode(b"\0\0\x01") == "112"
    assert names.b32(b"\xff") == "74"
    for text in ("0", "abc=", "a"):
        with pytest.raises(ValueError):
            names.b32decode(text)
    with pytest.raises(ValueError):
        names.b58decode("0OIl")


def test_jcs_of_rfc_8785():
    sorting = {"€": "Euro Sign", "\r": "Carriage Return", "דּ": "Hebrew Letter Dalet With Dagesh",
               "1": "One", "\U0001f600": "Emoji: Grinning Face", "\u0080": "Control",
               "ö": "Latin Small Letter O With Diaeresis"}
    out = names.jcs(sorting).decode("utf-8")
    values = [v for _, v in json.loads(out, object_pairs_hook=lambda pairs: pairs)]
    assert values == ["Carriage Return", "One", "Control", "Latin Small Letter O With Diaeresis",
                      "Euro Sign", "Emoji: Grinning Face", "Hebrew Letter Dalet With Dagesh"]
    assert out.startswith('{"\\r":"Carriage Return","1":"One","\u0080":"Control"')
    value = {"string": "€$\u000f\nA'B\"\\\\\"/", "literals": [None, True, False]}
    assert names.jcs(value) == '{"literals":[null,true,false],"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'.encode()
    assert names.jcs({"b": [1, -2, {"a": 0}], "a": {}}) == b'{"a":{},"b":[1,-2,{"a":0}]}'
    for bad in (1.5, 2 ** 53 + 1, {"a": "\ud800"}, {"\udc00": 1}, {1: 2}):
        with pytest.raises((ValueError, TypeError)):
            names.jcs(bad)


URIS_C7 = [
    f"sheaf:{N}",
    f"sheaf:{N}/v2",
    f"sheaf:{N}/v2?sha512={D2}",
    f"sheaf:{N}/v2?sha512={D2}&at=https%3A%2F%2Fmgubi.org%2Fpapers%2F",
    f"sheaf:{N}:{J}/v2",
    f"sheaf:{N}:*",
    f"sheaf:{A}",
    f"sheaf:{A}/v2?sha512={KL2}",
]


def test_sheaf_uris_of_appendix_c():
    for text in URIS_C7:
        assert str(names.parse_sheaf(text)) == text
    u = names.parse_sheaf(URIS_C7[3])
    assert (u.name, u.owner, u.version, u.sha512, u.at) == (N, None, 2, D2, "https://mgubi.org/papers/")
    assert u.canonical() == URIS_C7[2]
    assert names.parse_sheaf(URIS_C7[5]).owner == "*"
    assert names.key_log_pin(A, 2, KL2) == URIS_C7[7]
    for short in (f"sheaf:{N[:8]}/v2", f"sheaf:{N[:8]}:{J[:8]}/v2"):
        with pytest.raises(ValueError):
            names.parse_sheaf(short)
        s = names.parse_sheaf(short, short=True)
        assert str(s) == short and not s.is_complete() and s.matches(N, J)
        with pytest.raises(ValueError):
            s.canonical()
    assert not names.parse_sheaf(f"sheaf:{N[:8]}:{J[:8]}", short=True).matches(N, A)


def test_sheaf_uri_syntax():
    bad = [f"sheaf:{N}?sha512={D2}", f"sheaf:{N}/v2?sha512={D2[:-1]}", f"sheaf:{N}/v02",
           f"sheaf:{N}/v0", f"sheaf:{N}:*/v2", f"sheaf:{N}/v2?sha512={D2}&sha512={D2}",
           f"sheaf:{N}/v2?at=https%3A%2F%2Fa.org%2F&sha512={D2}", f"sheaf:{N}?at=http%3A%2F%2Fa.org%2F",
           f"sheaf:{N}?at=https://a.org/", f"sheaf:{N}:{N1}", f"sheaf:{N[:-1]}1", f"sheaf:{N}#x",
           f"sheaf:{N}?x", f"sheaf:{N}?", f"sheaf:{N[:7]}", f"urn:{N}", f"sheaf:{N}/v2/x"]
    for text in bad:
        with pytest.raises(ValueError):
            names.parse_sheaf(text, short=True)
    upper = f"SHEAF:{N.upper()}/V2?SHA512={D2.upper()}&at=https%3A%2F%2FA.org%2F"
    with pytest.raises(ValueError):
        names.parse_sheaf(upper)
    u = names.parse_sheaf(upper, fold=True)
    assert (u.name, u.version, u.sha512, u.at) == (N, 2, D2, "https://A.org/")
    u = names.parse_sheaf(f"sheaf:{N}:{A}/v2?sha512={D2}&lang=en")
    assert u.params == (("lang", "en"),) and str(u).endswith("&lang=en")
    assert u.canonical() == f"sheaf:{N}:{A}/v2?sha512={D2}"
    assert u.canonical(originator=A) == f"sheaf:{N}/v2?sha512={D2}"
    assert names.parse_sheaf(f"sheaf:{N}:{J}").canonical(originator=A) == f"sheaf:{N}:{J}"
    assert names.parse_sheaf(f"sheaf:{N1}:*").canonical(genesis_name=N) == f"sheaf:{N}:*"
    with pytest.raises(ValueError):
        names.parse_sheaf(f"sheaf:{N1}:*").canonical()


def test_orcid_check_digit():
    for good in (ORCID_A, "0000-0002-1825-0097", "https://orcid.org/0000-0001-5109-3700",
                 "0000-0002-1694-233X"):
        assert names.orcid_valid(good)
    for bad in ("0000-0002-1234-5678", "0000-0002-1694-2339", "0000-0002-1825-009", "http://orcid.org/0000-0002-1825-0097"):
        assert not names.orcid_valid(bad)
    assert names.orcid_check_digit("000000021234567") == "7"
    assert names.keeper_valid(ORCID_A) and names.keeper_valid("https://journal.example.org/")
    assert not names.keeper_valid("https://orcid.org/0000-0002-1234-5678")
    assert not names.keeper_valid("https://journal.example.org")


def test_computed_first_version():
    log = authors_log(1)
    v1 = log.versions[0]
    assert v1.files["object.json"] == (
        b'{"format":"opensheaf-object/0.2","kind":"owner","name":"' + A.encode() + b'","owner":"'
        + A.encode() + b'","specification":"0.2","status":"active"}')
    assert v1.files["keys.json"] == (
        b'{"format":"opensheaf-keys/0.2","keys":["' + K1.did.encode() + b'"],"next":["'
        + b'","'.join(r.digest.encode() for r in R[1:4]) + b'"],"nextThreshold":2,"threshold":1}')
    assert set(v1.files) == {"genesis.json", "object.json", "keys.json"} and not v1.witnesses
    inv = json.loads(v1.inventory)
    assert v1.inventory == names.jcs(inv) and v1.digest == KL1
    assert inv["id"] == f"sheaf:{A}:{A}" and inv["versions"]["v1"] == {
        "created": "2026-03-01T17:40:00Z",
        "state": {names.sha512_hex(b): [p] for p, b in v1.files.items()}}
    assert set(inv) == {"digestAlgorithm", "head", "id", "manifest", "type", "versions"}
    assert log.pin(1) == f"sheaf:{A}/v1?sha512={KL1}"
    assert log.check() == ([], []) and log.latest() is v1 and log.extensions() == TIMESTAMPS


def test_key_log_versions_of_appendix_c():
    log = authors_log(3)
    v2, v3 = log.versions[1], log.versions[2]
    assert v2.digest == KL2 and v3.digest == KL3
    assert json.loads(v2.files["keys.json"]) == {
        "format": "opensheaf-keys/0.2", "keys": [K3.did], "threshold": 1,
        "next": [R[4].digest, R[5].digest, R[6].digest], "nextThreshold": 2, "extensions": TIMESTAMPS}
    assert v2.files["keys.json"].startswith(b'{\n  "format": "opensheaf-keys/0.2",\n  "keys": [\n')
    assert json.loads(v3.files["keys.json"])["exposed"] == [K3.did]
    assert json.loads(v2.files["object.json"])["previous"] == KL1
    assert v2.files["object.json"].endswith(b'"previous":"' + KL1.encode() + b'","specification":"0.2","status":"active"}')
    assert sorted(v2.witnesses) == ["signature-h6k4k6c5u4dusj4s.json", "signature-oxthfb6b4q3sqath.json"]
    sig = json.loads(v2.witnesses["signature-oxthfb6b4q3sqath.json"])
    assert sig == {"format": "opensheaf-signature/0.2", "object": f"sheaf:{A}:{A}", "version": "v2",
                   "inventorySha512": KL2, "signer": A, "key": R[1].did, "keyLog": f"sheaf:{A}/v1?sha512={KL1}",
                   "signature": "MyYYLDn6FPmfVz478eKdcQF2FOkRTL8/ZV9qV35/PuC5u09ZYwDVxunX3S4Z1jWHICWsxgA+/L3MW49O0Z7vCA=="}
    assert json.loads(v2.witnesses["signature-h6k4k6c5u4dusj4s.json"])["signature"] == (
        "cZEYKDIoCgvI/mSGgWX3Mw+Tin4DLn8RVvqRhNcqJ0PkT8Gaa0U9mV4COFUqJztVZM0A8vyqrLh7hw3hgE8hCg==")
    sig3 = json.loads(v3.witnesses["signature-j77iavvdclktxkwm.json"])
    assert sig3["keyLog"] == f"sheaf:{A}/v2?sha512={KL2}" and sig3["signature"] == (
        "lAQKAGCR6HxrUX+mv5DbqOFehbfo1zlLtYVPrNmyG+Wq5p0RuWEC+PyL7c0amQ+lRc0EKgJpfY5eRAt9oGU8Dw==")
    assert "signature-nzvwkea25p62akdy.json" in v3.witnesses
    assert log.check() == ([], [])
    assert log.latest() is v3 and log.exposed_keys() == {K3.did} and not log.ended
    assert log.extensions() == TIMESTAMPS


def test_fork_record_of_appendix_c():
    other = thief_v3()
    assert other.digest == KL3T and names.b32(names.sha256(other.inventory))[:16] == D3T
    log = forked_log()
    v4 = log.versions[3]
    assert v4.digest == KL4 and v4.fork_record and "keys.json" not in v4.files
    assert sorted(v4.files) == ["forked/f35la3m3ue36z36u/inventory.json",
                                "forked/f35la3m3ue36z36u/inventory.json.sha512",
                                "forked/f35la3m3ue36z36u/keys.json",
                                "forked/f35la3m3ue36z36u/signature-fhujijfn3zmvteie.json",
                                "forked/f35la3m3ue36z36u/signature-nzvwkea25p62akdy.json",
                                "genesis.json", "object.json"]
    assert json.loads(v4.files["object.json"])["previous"] == KL3
    assert log.check() == ([], [])
    assert log.ended and log.fork_point == 3 and log.latest() is None
    assert log.lookup(3, KL3T) is not None and log.lookup(3, KL3) is log.versions[2]
    assert "Status        ended by a fork at v3" in owners.describe(log)
    with pytest.raises(owners.OwnerError):
        log.rotate([R[7], R[8]], next_keys=[K("x")], next_threshold=1, user=USER_A)
    with pytest.raises(owners.OwnerError):
        log.record_fork([other], user=USER_A)


def test_rules_of_keys():
    v1 = authors_log(1).versions[0].keys
    def problems(**fields):
        k = {"format": "opensheaf-keys/0.2", "keys": [K3.did], "threshold": 1,
             "next": [R[4].digest], "nextThreshold": 1}
        k.update(fields)
        return " ".join(owners.key_rules({f: v for f, v in k.items() if v is not None}, [v1], A))

    assert problems() == ""
    assert "rule 1" in problems(threshold=2) and "rule 1" in problems(nextThreshold=2)
    assert "rule 2" in problems(keys=[K3.did], exposed=[K3.did])
    assert "rule 2" in problems(keys=[R[1].did])
    assert "rules 2 and 3" in problems(next=[K3.digest])
    assert "rule 3" in problems(next=[K1.digest]) and "rule 3" in problems(next=[R[2].digest])
    assert "rule 4" in problems(exposed=[K5.did])
    assert problems(exposed=[K1.did]) == ""
    assert "ending" in problems(ended=True)
    assert problems(keys=None, threshold=None, next=None, nextThreshold=None, ended=True, successor=J) == ""
    assert "successor" in problems(keys=None, threshold=None, next=None, nextThreshold=None, ended=True, successor=A)
    assert "successor" in problems(successor=J)
    assert "not define" in problems(keeper=[ORCID_A])
    log = authors_log(1)
    for kw in ({"add": [R[2]]}, {"next_keys": [K1]}, {"next_keys": [R[1]]}, {"threshold": 3},
               {"exposed": [K5.did]}, {"next_threshold": 4}):
        args = dict(next_keys=R[4:7], next_threshold=2, user=USER_A)
        args.update(kw)
        with pytest.raises(owners.OwnerError):
            log.rotate([R[1], R[2]], **args)
    assert len(log.versions) == 1 and log.check() == ([], [])


def test_a_final_line_feed_is_refused():
    from opensheaf import wallet
    v1 = authors_log(1).versions[0].keys
    fields = {"format": "opensheaf-keys/0.2", "keys": [K3.did, K3.did + "\n"], "threshold": 2,
              "next": [R[4].digest], "nextThreshold": 1}
    assert owners.key_rules(fields, [v1], A) != []
    for pattern, good in ((names.OWNER_NAME, A), (names.NAME, A), (names.DID_KEY, K3.did),
                          (names.NONCE, "00" * 16), (sign.FIELDS["version"], "v2")):
        assert pattern.match(good) and not pattern.match(good + "\n")
    with pytest.raises(wallet.WalletError):
        wallet.entry_path(A + "\n", "a" * 16)
    with pytest.raises(wallet.WalletError):
        wallet.entry_path(A, "a" * 16 + "\n")
    obj = "sheaf:" + "a" * 52 + ":" + A
    pin = names.key_log_pin(A, 1, "0" * 128)
    good = json.loads(sign.signature_file(K3, obj, "v2", "0" * 128, A, pin))
    assert sign.read_signature_file(json.dumps(good).encode())
    with pytest.raises(ValueError, match="keyLog"):
        sign.read_signature_file(json.dumps(dict(good, keyLog=pin + "\n")).encode())


def test_signing_the_key_log():
    log = authors_log(2)
    args = dict(next_keys=R[7:10], next_threshold=2, user=USER_A)
    for signers in ([R[4]], [K3, R[4]], [R[1], R[2]], [R[4], R[4]]):
        with pytest.raises(owners.OwnerError):
            log.rotate(signers, add=[K5], **args)
    with pytest.raises(owners.OwnerError):
        log.end([R[4], R[5]], successor=A, user=USER_A)
    v3 = log.end([R[4], R[5]], successor=J, user=USER_A)
    assert json.loads(v3.files["keys.json"]) == {"format": "opensheaf-keys/0.2", "ended": True, "successor": J}
    assert log.ended and log.successor == J and log.latest() is None and log.check() == ([], [])
    with pytest.raises(owners.OwnerError):
        log.rotate([R[7], R[8]], add=[K5], **args)


def test_key_log_on_disk(tmp_path):
    log = authors_log(2)
    d = tmp_path / A / A
    owners.write_key_log(d, log)
    assert (d / "0=ocfl_object_1.1").exists() and (d / "v1" / "inventory.json").read_bytes() == log.versions[0].inventory
    assert (d / "extensions/opensheaf-witnesses/v2/signature-oxthfb6b4q3sqath.json").exists()
    assert not (d / "extensions/opensheaf-witnesses/v1").exists()
    assert not (d / "v2/content/genesis.json").exists()
    back = owners.load_key_log(d)
    assert [v.digest for v in back.versions] == [KL1, KL2] and back.check() == ([], [])
    try:
        from ocfl.validator import Validator
    except ImportError:
        Validator = None
    if Validator is not None:
        v = Validator(log_warnings=False)
        assert v.validate_object(str(d)), v.status_str()
    log.expose([R[4], R[5]], [K3.did], add=[K5], next_keys=R[7:10], next_threshold=2, user=USER_A)
    owners.write_key_log(d, log)
    assert [v.digest for v in owners.load_key_log(d).versions] == [KL1, KL2, log.versions[2].digest]
    with pytest.raises(owners.OwnerError):
        owners.write_key_log(d, forked_log())
    forked = forked_log()
    owners.write_key_log(tmp_path / "forked", forked)
    back = owners.load_key_log(tmp_path / "forked")
    assert back.versions[3].digest == KL4 and back.fork_point == 3 and back.check() == ([], [])


def test_checks_of_a_key_log_on_disk(tmp_path):
    d = tmp_path / "log"
    owners.write_key_log(d, authors_log(3))
    keys3 = d / "v3/content/keys.json"
    keys3.write_bytes(keys3.read_bytes().replace(b"\n}", b"}"))
    errors, _ = owners.load_key_log(d).check()
    assert any("digest its inventory states" in e for e in errors)
    log = authors_log(1)
    log.versions[0].witnesses["signature-oxthfb6b4q3sqath.json"] = b"{}"
    assert log.check() == ([], ["v1: a signature file of the computed first version is invalid (section 7.3)"])
    bad = owners.KeyLog(log.genesis, [owners.Version(1, dict(log.versions[0].files, **{"keys.json": b"{}"}),
                                                     log.versions[0].inventory)])
    assert "v1: not the version computed" in bad.check()[0][0]
    log = authors_log(2)
    log.versions[1].witnesses.clear()
    log._checked = None
    errors, _ = log.check()
    assert errors == ["v2: signed by 0 rotation keys of v1, which needs 2 (section 6.1)"]
    assert log.latest() is log.versions[0]
    ended = authors_log(2)
    ended.end([R[4], R[5]], user=USER_A)
    after = owners.KeyLog(ended.genesis, copy.deepcopy(ended.versions))
    after.versions.append(copy.deepcopy(authors_log(3).versions[2]))
    after.versions[-1].number = 4
    errors, warnings = after.check()
    assert any("held after an ending version" in w for w in warnings)


NID = f"sheaf:{N}:{A}"
MSG_D2 = (f"opensheaf-signature/0.2\nobject {NID}\nversion v2\ninventory {D2}\n"
          f"keylog sheaf:{A}/v2?sha512={KL2}\n").encode()
SIG_D2 = "0j2Xy5fRv+1ajlCCkmCXAOZj1U8CUeiYA1jP08kJevQH27QnXHLZ7TeF+WwxzYB+ad2OepksXgSCzP1KoCEYCg=="


def paper_signature(key, version, digest, key_log, signer=A, object_id=NID):
    return sign.signature_file(key, object_id, version, digest, signer, key_log)


def test_signature_of_appendix_c():
    log = authors_log(2)
    assert sign.message(NID, "v2", D2, log.pin(2)) == MSG_D2
    data = paper_signature(K3, "v2", D2, log.pin(2))
    d = json.loads(data)
    assert d["signature"] == SIG_D2 and list(d) == ["format", "object", "version", "inventorySha512",
                                                    "signer", "key", "keyLog", "signature"]
    assert sign.file_name(K3.did) == "signature-4hz7zgsiazl6hx7i.json"
    assert sign.verify(K3.did, MSG_D2, base64.b64decode(SIG_D2))
    j = sign.judge(data, "signature-4hz7zgsiazl6hx7i.json", object_id=NID, version="v2", inventory=D2,
                   owner=A, lookup=log.lookup)
    assert (j.status, j.key, j.key_log, j.threshold) == (sign.GOOD, K3.did, (2, KL2), 1)


EDDSA_VECTORS = [   # (message, public key, signature), from ed25519-speccheck's cases.json
    ("8c93255d71dcab10e8f379c26200f3c7bd5f09d9bc3068d3ef4edeb4853022b6",
     "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa",
     "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a"
     "0000000000000000000000000000000000000000000000000000000000000000"),
    ("9bd9f44f4dcc75bd531b56b2cd280b0bb38fc1cd6d1230e14861d861de092e79",
     "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa",
     "f7badec5b8abeaf699583992219b7b223f1df3fbbea919844e3f7c554a43dd43"
     "a5bb704786be79fc476f91d3f3f89b03984d8068dcf1bb7dfc6637b45450ac04"),
    ("aebf3f2601a0c8c5d39cc7d8911642f740b78168218da8471772b35f9d35b9ab",
     "f7badec5b8abeaf699583992219b7b223f1df3fbbea919844e3f7c554a43dd43",
     "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa"
     "8c4bd45aecaca5b24fb97bc10ac27ac8751a7dfe1baff8b953ec9f5833ca260e"),
    ("9bd9f44f4dcc75bd531b56b2cd280b0bb38fc1cd6d1230e14861d861de092e79",
     "cdb267ce40c5cd45306fa5d2f29731459387dbf9eb933b7bd5aed9a765b88d4d",
     "9046a64750444938de19f227bb80485e92b83fdb4b6506c160484c016cc1852f"
     "87909e14428a7a1d62e9f22f3d3ad7802db02eb2e688b6c52fcd6648a98bd009"),
    ("e47d62c63f830dc7a6851a0b1f33ae4bb2f507fb6cffec4011eaccd55b53f56c",
     "cdb267ce40c5cd45306fa5d2f29731459387dbf9eb933b7bd5aed9a765b88d4d",
     "160a1cb0dc9c0258cd0a7d23e94d8fa878bcb1925f2c64246b2dee1796bed512"
     "5ec6bc982a269b723e0668e540911a9a6a58921d6925e434ab10aa7940551a09"),
    ("e47d62c63f830dc7a6851a0b1f33ae4bb2f507fb6cffec4011eaccd55b53f56c",
     "cdb267ce40c5cd45306fa5d2f29731459387dbf9eb933b7bd5aed9a765b88d4d",
     "21122a84e0b5fca4052f5b1235c80a537878b38f3142356b2c2384ebad4668b7"
     "e40bc836dac0f71076f9abe3a53f9c03c1ceeeddb658d0030494ace586687405"),
    ("85e241a07d148b41e47d62c63f830dc7a6851a0b1f33ae4bb2f507fb6cffec40",
     "442aad9f089ad9e14647b1ef9099a1ff4798d78589e66f28eca69c11f582a623",
     "e96f66be976d82e60150baecff9906684aebb1ef181f67a7189ac78ea23b6c0e"
     "547f7690a0e2ddcd04d87dbc3490dc19b3b3052f7ff0538cb68afb369ba3a514"),
    ("85e241a07d148b41e47d62c63f830dc7a6851a0b1f33ae4bb2f507fb6cffec40",
     "442aad9f089ad9e14647b1ef9099a1ff4798d78589e66f28eca69c11f582a623",
     "8ce5b96c8f26d0ab6c47958c9e68b937104cd36e13c33566acd2fe8d38aa1942"
     "7e71f98a473474f2f13f06f97c20d58cc3f54b8bd0d272f42b695dd7e89a8c22"),
    ("9bedc267423725d473888631ebf45988bad3db83851ee85c85e241a07d148b41",
     "f7badec5b8abeaf699583992219b7b223f1df3fbbea919844e3f7c554a43dd43",
     "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
     "03be9678ac102edcd92b0210bb34d7428d12ffc5df5f37e359941266a4e35f0f"),
    ("9bedc267423725d473888631ebf45988bad3db83851ee85c85e241a07d148b41",
     "f7badec5b8abeaf699583992219b7b223f1df3fbbea919844e3f7c554a43dd43",
     "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
     "ca8c5b64cd208982aa38d4936621a4775aa233aa0505711d8fdcfdaa943d4908"),
    ("e96b7021eb39c1a163b6da4e3093dcd3f21387da4cc4572be588fafae23c155b",
     "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "a9d55260f765261eb9b84e106f665e00b867287a761990d7135963ee0a7d59dc"
     "a5bb704786be79fc476f91d3f3f89b03984d8068dcf1bb7dfc6637b45450ac04"),
    ("39a591f5321bbe07fd5a23dc2f39d025d74526615746727ceefd6e82ae65c06f",
     "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "a9d55260f765261eb9b84e106f665e00b867287a761990d7135963ee0a7d59dc"
     "a5bb704786be79fc476f91d3f3f89b03984d8068dcf1bb7dfc6637b45450ac04"),
]


def test_eddsa_edge_cases():
    def libsodium(pub, msg, sig):
        try:
            VerifyKey(pub).verify(msg, sig)
            return True
        except Exception:
            return False

    results = []
    for msg, pub, sig in EDDSA_VECTORS:
        msg, pub, sig = bytes.fromhex(msg), bytes.fromhex(pub), bytes.fromhex(sig)
        ours = sign.verify(names.did_key(pub), msg, sig)
        assert ours == libsodium(pub, msg, sig)
        results.append(ours)
    assert results == [i == 3 for i in range(12)]
    assert not sign.verify(K3.did, MSG_D2, base64.b64decode(SIG_D2)[:63])
    assert not sign.verify(K1.did, MSG_D2, base64.b64decode(SIG_D2))


def test_invalid_and_unchecked_signature_files():
    log = forked_log()
    def status(data, file=None, **context):
        ctx = dict(object_id=NID, version="v2", inventory=D2, owner=A, lookup=log.lookup)
        ctx.update(context)
        d = json.loads(data) if data.startswith(b"{") else {}
        j = sign.judge(data, file or (sign.file_name(d["key"]) if "key" in d else "signature-x.json"), **ctx)
        return j.status, j.reason

    good = paper_signature(K3, "v2", D2, log.pin(2))
    assert status(good) == (sign.GOOD, "")
    d = json.loads(good)
    assert status(b"not json")[0] == sign.INVALID
    assert status(json.dumps(dict(d, extra=1)).encode())[0] == sign.INVALID
    assert status(good, "signature-aaaaaaaaaaaaaaaa.json")[1].startswith("its name")
    forged = dict(d, signature=base64.b64encode(bytes(64)).decode())
    assert "does not verify" in status(json.dumps(forged).encode())[1]
    assert "another version" in status(good, inventory=D1)[1]
    assert "another version" in status(good, version="v3")[1]
    other = paper_signature(K3, "v2", D2, f"sheaf:{J}/v1?sha512={JL1}", signer=J)
    assert "signer" in status(other)[1]
    mixed = dict(d, keyLog=f"sheaf:{J}/v2?sha512={KL2}")
    assert "malformed" in status(json.dumps(mixed).encode())[1]
    assert "not a current key" in status(paper_signature(K1, "v2", D2, log.pin(2)))[1]
    assert "fork record" in status(paper_signature(K5, "v2", D2, log.pin(4)))[1]
    assert status(paper_signature(K3, "v2", D2, f"sheaf:{A}/v2?sha512={D1}"))[0] == sign.UNCHECKED
    assert status(paper_signature(K3, "v2", D2, f"sheaf:{A}/v9?sha512={KL2}"))[0] == sign.UNCHECKED
    assert status(paper_signature(K3, "v2", D2, log.pin(2)), lookup=lambda n, d: None)[0] == sign.UNCHECKED
    kl = dict(object_id=f"sheaf:{A}:{A}", owner=A, key_log=True)
    v1sig = sign.signature_file(R[1], f"sheaf:{A}:{A}", "v1", KL1, A, log.pin(1))
    assert "never the first" in status(v1sig, version="v1", inventory=KL1, **kl)[1]
    v3sig = sign.signature_file(R[4], f"sheaf:{A}:{A}", "v3", KL3, A, log.pin(1))
    assert "never the first" in status(v3sig, version="v3", inventory=KL3, **kl)[1]
    v3sig = sign.signature_file(R[7], f"sheaf:{A}:{A}", "v3", KL3, A, log.pin(2))
    assert "not a rotation key" in status(v3sig, version="v3", inventory=KL3, **kl)[1]
    v3sig = sign.signature_file(R[4], f"sheaf:{A}:{A}", "v3", KL3, A, log.pin(2))
    assert status(v3sig, version="v3", inventory=KL3, **kl)[0] == sign.GOOD


def paper(log, *extra):
    """The paper's versions as (version, digest, witnesses), each signature given as (key, key-log version)."""
    def signed(version, digest, *signers):
        return (version, digest, {sign.file_name(k.did): paper_signature(k, version, digest, log.pin(n))
                                  for k, n in signers})
    versions = [signed("v1", D1, (K1, 1)), signed("v2", D2, (K3, 2))]
    return versions + [signed(f"v{3 + i}", hashlib.sha512(f"{i}".encode()).hexdigest(), *s)
                       for i, s in enumerate(extra)]


def statuses(log, versions, trusted=None):
    return sign.line_statuses_of(NID, A, versions, log, trusted)[1]


def test_statuses_of_a_line():
    log = authors_log(2)
    assert statuses(log, paper(log)) == [sign.SIGNED, sign.SIGNED]
    assert sign.latest_signed(statuses(log, paper(log))) == 2
    versions = paper(log)
    versions[0] = ("v1", D1, {})
    assert statuses(log, versions) == [sign.VOUCHED, sign.SIGNED]
    versions = paper(log)
    versions[1] = ("v2", D2, {})
    assert statuses(log, versions) == [sign.SIGNED, sign.UNSIGNED]
    versions[1] = ("v2", D2, {sign.file_name(K1.did): paper_signature(K1, "v2", D2, log.pin(2))})
    assert statuses(log, versions) == [sign.SIGNED, sign.INVALID]
    versions[1] = ("v2", D2, {sign.file_name(K5.did): paper_signature(K5, "v2", D2, f"sheaf:{A}/v3?sha512={KL3}")})
    assert statuses(log, versions) == [sign.SIGNED, sign.UNCHECKED]
    assert statuses(authors_log(3), versions) == [sign.SIGNED, sign.SIGNED]
    assert sign.latest_signed([sign.SIGNED, sign.CONTESTED]) == 1 and sign.latest_signed([sign.UNSIGNED]) is None


def test_contested_by_exposure_and_fork():
    log = authors_log(3)
    assert statuses(log, paper(log)) == [sign.SIGNED, sign.CONTESTED]
    assert sign.latest_signed(statuses(log, paper(log))) == 1
    assert statuses(log, paper(log, [(K3, 2)])) == [sign.SIGNED, sign.CONTESTED, sign.CONTESTED]
    assert statuses(log, paper(log), trusted=lambda j: j.key == K3.did) == [sign.SIGNED, sign.SIGNED]
    again = paper(log)
    again[1][2][sign.file_name(K5.did)] = paper_signature(K5, "v2", D2, log.pin(3))
    assert statuses(log, again) == [sign.SIGNED, sign.SIGNED]
    assert statuses(log, paper(log, [(K5, 3)])) == [sign.SIGNED, sign.SIGNED, sign.SIGNED]
    forked = forked_log()
    assert statuses(forked, again) == [sign.SIGNED, sign.CONTESTED]
    assert statuses(forked, paper(forked, [(K5, 3)])) == [sign.SIGNED, sign.CONTESTED, sign.CONTESTED]
    assert statuses(forked, paper(forked, [(T, 3)])) == [sign.SIGNED, sign.CONTESTED, sign.INVALID]


def test_exposure_on_the_other_side_of_a_fork():
    log = authors_log(3)
    log.record_fork([thief_v3(exposed=[K1.did])], user={"name": "An archive"}, created="2026-11-05T12:00:00Z")
    assert log.check() == ([], []) and log.exposed_keys() == {K1.did, K3.did}
    assert statuses(log, paper(log)) == [sign.CONTESTED, sign.CONTESTED]
    assert statuses(forked_log(), paper(forked_log())) == [sign.SIGNED, sign.CONTESTED]


def test_new_keys_and_the_test_hook(monkeypatch):
    monkeypatch.delenv(keys.TEST_KEYS, raising=False)
    assert keys.new_key().did != keys.new_key().did
    monkeypatch.setenv(keys.TEST_KEYS, "authors laptop, authors rotation 1")
    assert keys.new_key().did == K1.did and keys.new_key().did == R[1].did
    with pytest.raises(keys.KeyStoreError):
        keys.new_key()
    monkeypatch.setenv(keys.TEST_KEYS, "thief")
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    with pytest.raises(keys.KeyStoreError, match="outside the tests"):
        keys.new_key()


def test_current_keys_in_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv(keys.KEY_STORE, "file")
    monkeypatch.delenv(keys.SIGNING_KEY, raising=False)
    assert keys.store_current_key(A, K3) == "file"
    path = tmp_path / "opensheaf" / "keys" / A / f"{K3.id}.key"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert capsys.readouterr().err.startswith("Warning: A current key of ")
    assert [k.did for k in keys.current_keys(A, [K1.did, K3.did])] == [K3.did]
    assert keys.current_keys(A, [K1.did]) == [] and keys.current_keys(J, [K3.did]) == []
    with pytest.raises(FileExistsError):
        keys.store_current_key(A, K3)
    path.chmod(0o644)
    keys.forget_seen()
    with pytest.raises(keys.KeyStoreError, match="other users"):
        keys.current_keys(A, [K3.did])
    path.chmod(0o600)
    moved = tmp_path / "elsewhere.key"
    path.rename(moved)
    path.symlink_to(moved)
    keys.forget_seen()
    with pytest.raises(keys.KeyStoreError, match="symbolic link"):
        keys.current_keys(A, [K3.did])
    path.unlink()
    moved.rename(path)
    keys.forget_seen()
    monkeypatch.setenv(keys.SIGNING_KEY, base64.b64encode(K5.seed).decode())
    assert [k.did for k in keys.current_keys(A, [K5.did])] == [K5.did]
    with pytest.raises(keys.KeyStoreError):
        keys.current_keys(A, [K3.did])
    monkeypatch.setenv(keys.SIGNING_KEY, "not a seed")
    with pytest.raises(keys.KeyStoreError):
        keys.current_keys(A, [K3.did])
    monkeypatch.delenv(keys.SIGNING_KEY)
    keys.forget_current_key(A, K3.did)
    assert not path.exists()
    monkeypatch.setenv(keys.KEY_STORE, "elsewhere")
    with pytest.raises(keys.KeyStoreError):
        keys.current_keys(A, [K3.did])


@pytest.mark.skipif(sys.platform != "darwin", reason="the security store is macOS only")
def test_keys_in_the_keychain_are_read_back(tmp_path, monkeypatch):
    folder = tmp_path / "keychain"
    folder.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    fake = bin_ / "security"
    fake.write_text(f"""#!/bin/sh
if [ "$1" = "-i" ]; then read -r cmd; set -- $cmd
  while [ $# -gt 1 ]; do [ "$1" = "-a" ] && a=$2; [ "$1" = "-w" ] && w=$2; shift; done
  [ -e '{folder}/forget' ] || printf '%s' "$w" > '{folder}'/"$a"; exit 0; fi
while [ $# -gt 1 ]; do [ "$1" = "-a" ] && a=$2; shift; done
[ -f '{folder}'/"$a" ] || exit 44; cat '{folder}'/"$a"
""")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    monkeypatch.setenv(keys.KEY_STORE, "security")
    monkeypatch.delenv(keys.SIGNING_KEY, raising=False)
    keys.forget_seen()
    assert keys.store_current_key(A, K3) == "security"
    keys.forget_seen()
    assert [k.did for k in keys.current_keys(A, [K3.did])] == [K3.did]
    (folder / "forget").write_text("")
    with pytest.raises(keys.KeyStoreError, match="no store kept"):
        keys.store_current_key(A, K5)
    keys.forget_seen()


FAST = dict(opslimit=pwhash.argon2id.OPSLIMIT_MIN, memlimit=pwhash.argon2id.MEMLIMIT_MIN)


def test_rotation_keys_exported_and_read_back(tmp_path):
    paths = keys.export_rotation_keys(R[1:4], A, 1, tmp_path / "usb", passphrase="correct horse", **FAST)
    assert [p.name for p in paths] == [f"rotation-{A[:16]}-{r.id}.txt" for r in R[1:4]]
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in paths)
    text = paths[0].read_text()
    assert text.startswith(f"opensheaf-rotation-key/0.2\nowner {A}\nversion v1\nkey {R[1].did}\ndigest {R[1].digest}\n")
    assert base64.b64encode(R[1].seed).decode() not in text
    back = keys.read_rotation_key(paths[0], "correct horse")
    assert (back.key.did, back.owner, back.version) == (R[1].did, A, 1)
    for wrong in (None, "wrong horse"):
        with pytest.raises(keys.KeyStoreError):
            keys.read_rotation_key(paths[0], wrong)
    with pytest.raises(FileExistsError):
        keys.export_rotation_keys([R[1]], A, 1, tmp_path / "usb", **FAST)
    plain = keys.export_rotation_keys([R[4]], A, 2, tmp_path / "plain")[0]
    assert "encryption none" in plain.read_text()
    assert keys.read_rotation_key(plain).key.did == R[4].did
    damaged = plain.read_text().replace(R[4].did, R[5].did)
    with pytest.raises(keys.KeyStoreError):
        keys.read_rotation_key(damaged)


def test_rotation_key_sheet():
    sheet = keys.rotation_key_sheet(R[1], A, 1)
    seed_line = next(line for line in sheet.splitlines() if line.startswith("seed"))
    groups = seed_line.split()[1:]
    assert len(groups) == 13 and all(len(g) == 4 and g.isupper() for g in groups)
    assert keys.read_rotation_key(sheet).key.did == R[1].did
    check = next(line for line in sheet.splitlines() if line.startswith("check")).split()[1]
    typed = f"seed {' '.join(groups).lower()}\ncheck {check}\n"
    assert keys.read_rotation_key(typed).key.did == R[1].did
    wrong = groups[0][:-1] + ("A" if groups[0][-1] != "A" else "B")
    with pytest.raises(keys.KeyStoreError, match="mistyped"):
        keys.read_rotation_key(typed.replace(groups[0].lower(), wrong.lower(), 1))


def test_rotation_keys_refused_inside_an_archive(tmp_path):
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "osheaf.json").write_text("{}")
    with pytest.raises(keys.KeyStoreError, match="inside the archive"):
        keys.export_rotation_keys([R[1]], A, 1, tmp_path / "archive" / "keys", **FAST)
    (tmp_path / "other").mkdir()
    with pytest.raises(keys.KeyStoreError, match="inside the archive"):
        keys.export_rotation_keys([R[1]], A, 1, tmp_path / "other" / "keys", archive_root=tmp_path / "other", **FAST)
    assert not (tmp_path / "archive" / "keys").exists() and not (tmp_path / "other" / "keys").exists()


def test_files_validate_against_the_schemas():
    jsonschema = pytest.importorskip("jsonschema")
    folder = Path(owners.__file__).parent / "schemas"
    def validator(name):
        return jsonschema.Draft202012Validator(json.loads((folder / f"opensheaf-{name}-0.2.schema.json").read_text()))

    log = forked_log()
    ended = authors_log(2)
    ended.end([R[4], R[5]], successor=J, exposed=[K3.did], user=USER_A)
    files = {"genesis": [log.genesis, names.genesis_record("document", originator=A)],
             "keys": [v.files["keys.json"] for v in log.versions[:3] + ended.versions[1:]]
             + [thief_v3().files["keys.json"]],
             "signature": [w for v in log.versions for w in v.witnesses.values()]
             + [paper_signature(K3, "v2", D2, log.pin(2))]}
    for schema, datas in files.items():
        v = validator(schema)
        for data in datas:
            assert not list(v.iter_errors(json.loads(data))), (schema, data)
