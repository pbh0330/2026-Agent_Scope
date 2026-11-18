"""Skill의 설치 명세(의존성)와 설치 출처 기록(.clawhub/origin.json) 수집 테스트 (가상 자료).

근거: OpenClaw 2026.9.6 `docs/tools/skills.md` "Installer specs"(`id`·`kind`(brew/node/go/uv/download)·`formula`·`bins`·`label`·`os`, download의
`url`·`sha256`·`archive`·`extract`·`stripComponents`·`targetDir`), "Verification and security scanning"(설치 기록은 `.clawhub/origin.json`),
그리고 고정 패키지 번들 코드의 `normalizeClawHubSkillOrigin`(필수: `version: 1`·`registry`·`slug`·`installedVersion`·`installedAt`(숫자),
선택: `sourceUrl`·`ownerHandle`·`requestedReference`·`trustState`). 선언·기록된 값만 옮기며 다운로드·검증·실행은 하지 않는다.
"""

import json

from asset_scanner.plugin_skill_assets import build_report, collect_assets
from test_plugin_skill_assets import make_skill

META = json.dumps({"openclaw": {"requires": {"bins": ["gemini"]}, "install": [
    {"id": "brew", "kind": "brew", "formula": "gemini-cli", "bins": ["gemini"], "label": "Install Gemini CLI (brew)", "os": ["darwin", "linux"]},
    {"id": "dl", "kind": "download", "url": "https://user:FAKEPW123@example.com/a.tar.gz?token=FAKEQUERYSECRET", "sha256": "a" * 64, "archive": "tar.gz",
     "extract": True, "stripComponents": 1, "targetDir": "~/.openclaw/tools/gemini", "future": 1},
    {"id": "odd", "kind": "mystery"},
]}}, indent=1)


def skill(tmp_path, name="s", meta=META, origin=None):
    d = make_skill(tmp_path, name, f"---\nname: {name}\ndescription: d\nmetadata:\n  {meta.replace(chr(10), chr(10) + '  ')}\n---\nbody")
    if origin is not None:
        o = d / ".clawhub"
        o.mkdir()
        (o / "origin.json").write_text(origin if isinstance(origin, str) else json.dumps(origin), encoding="utf-8")
    return d


def rep(tmp_path, **kw):
    return build_report(collect_assets([], [skill(tmp_path, **kw)], None, None, None))["skills"][0]


def test_installer_specs_are_recorded_with_documented_fields_only(tmp_path):
    m = rep(tmp_path)["metadata_openclaw"]
    specs = m["install_specs"]
    assert m["install_spec_count"] == 3 and len(specs) == 3
    assert specs[0] == {"id": "brew", "kind": "brew", "kind_documented": True, "formula": "gemini-cli", "bins": ["gemini"], "label": "Install Gemini CLI (brew)", "os": ["darwin", "linux"], "other_keys": []}
    dl = specs[1]
    assert dl["kind"] == "download" and dl["archive"] == "tar.gz" and dl["extract"] is True and dl["stripComponents"] == 1 and dl["targetDir"] == "~/.openclaw/tools/gemini"
    assert dl["sha256_declared"] is True and "sha256" not in dl and dl["other_keys"] == ["future"]
    assert specs[2]["kind_documented"] is False


def test_download_spec_digest_and_url_credentials_are_not_stored(tmp_path):
    s = rep(tmp_path)
    text = json.dumps(s)
    assert "a" * 64 not in text and "FAKEPW123" not in text and "FAKEQUERYSECRET" not in text
    assert s["metadata_openclaw"]["install_specs"][1]["url"].startswith("https://") and s["redactions"]


def test_download_without_a_digest_is_reported_as_not_declared_without_claiming_verification(tmp_path):
    meta = json.dumps({"openclaw": {"install": [{"id": "d", "kind": "download", "url": "https://example.com/x.zip"}]}}, indent=1)
    sp = rep(tmp_path, meta=meta)["metadata_openclaw"]["install_specs"][0]
    assert sp["sha256_declared"] is False and "verified" not in json.dumps(sp)


# ---- 설치 출처 기록 ---------------------------------------------------------------------------------------

ORIGIN = {"version": 1, "registry": "https://clawhub.example/api", "slug": "gemini", "installedVersion": "1.2.3", "installedAt": 1737150000000,
          "sourceUrl": "https://user:FAKEPW456@example.com/skill?token=FAKEQ2", "ownerHandle": "acme", "newField": {"x": 1}}


def test_clawhub_origin_record_is_collected_as_a_recorded_value_not_a_verification(tmp_path):
    s = rep(tmp_path, origin=ORIGIN)
    o = s["install_origin"]
    assert o["status"] == "recorded" and o["source"] == "clawhub_origin_json" and o["file"] == ".clawhub/origin.json"
    assert (o["registry"], o["slug"], o["installed_version"], o["installed_at_ms"], o["owner_handle"]) == ("https://clawhub.example/api", "gemini", "1.2.3", 1737150000000, "acme")
    assert o["unknown_keys"] == ["newField"] and o["verified_by_scanner"] is False and o["verification"] == "not_performed"
    text = json.dumps(s)
    assert "FAKEPW456" not in text and "FAKEQ2" not in text


def test_skills_sh_reference_and_trust_state_are_kept_as_recorded(tmp_path):
    rec = dict(ORIGIN, requestedReference="skills-sh:owner/repo/gemini", trustState="not-scanned-by-clawhub")
    o = rep(tmp_path, origin=rec)["install_origin"]
    assert o["requested_reference"] == "skills-sh:owner/repo/gemini" and o["trust_state"] == "not-scanned-by-clawhub"


def test_missing_origin_means_the_source_was_not_provided_and_nothing_is_invented(tmp_path):
    s = rep(tmp_path)
    assert "install_origin" not in s                                                        # 로컬·Git 설치에는 기록이 없다


def test_malformed_origin_is_reported_without_values(tmp_path):
    for bad in ({"version": 2, "registry": "r", "slug": "s", "installedVersion": "1", "installedAt": 1}, {"version": 1, "registry": "r"}, "{ not json", "[1]"):
        s = rep(tmp_path / str(abs(hash(str(bad)))), origin=bad)
        assert s["install_origin"]["status"] == "malformed" and "registry" not in s["install_origin"]
        assert any(i["code"] == "skill_origin_malformed" for i in s["issues"])


# ---- sha256: 선언(키 존재)과 값 유효성의 분리 ------------------------------------------------------------------

import pytest

from asset_scanner.plugin_skill_assets import _install_spec

GOOD = "0123456789abcdef" * 4


@pytest.mark.parametrize("spec_extra, declared, state", [
    ({}, False, "absent"),                                            # 누락
    ({"sha256": GOOD}, True, "valid_format"),                         # 정상 문자열
    ({"sha256": GOOD.upper()}, True, "valid_format"),                 # 대소문자 무관한 16진
    ({"sha256": 12345}, True, "invalid_type"),                        # 숫자: 문자열로 바꿔 인정하지 않는다
    ({"sha256": 0}, True, "invalid_type"),
    ({"sha256": None}, True, "null"),                                 # 키는 있고 값이 null
    ({"sha256": ""}, True, "empty"),
    ({"sha256": "abc"}, True, "invalid_format"),                      # 너무 짧음
    ({"sha256": "g" * 64}, True, "invalid_format"),                   # 16진이 아님
    ({"sha256": GOOD + "0"}, True, "invalid_format"),                 # 길이 초과
    ({"sha256": True}, True, "invalid_type"),
    ({"sha256": [GOOD]}, True, "invalid_type"),
])
def test_sha256_declaration_and_value_validity_are_separate(spec_extra, declared, state):
    sp = _install_spec({"id": "d", "kind": "download", "url": "https://example.com/x.zip", **spec_extra})
    assert sp["sha256_declared"] is declared and sp["sha256_state"] == state
    assert "sha256" not in sp and GOOD not in json.dumps(sp)                      # 값은 저장하지 않는다


def test_an_unquoted_all_digit_digest_is_reported_as_a_number_not_accepted_as_a_hash(tmp_path):
    meta = '{"openclaw": {"install": [{"id": "d", "kind": "download", "url": "https://example.com/x.zip", "sha256": ' + "1" * 64 + "}]}}"
    s = rep(tmp_path, meta=meta)
    sp = s["metadata_openclaw"]["install_specs"][0]
    assert sp["sha256_declared"] is True and sp["sha256_state"] == "invalid_type"
    bad = [i for i in s["issues"] if i["code"] == "skill_install_sha256_invalid"]
    assert bad and bad[0]["specs"] == [{"index": 0, "state": "invalid_type"}] and "1" * 64 not in json.dumps(s)


def test_yaml_frontmatter_unquoted_digits_become_an_integer_and_are_not_coerced(tmp_path):
    d = make_skill(tmp_path, "y", "---\nname: y\ndescription: d\nmetadata:\n  openclaw:\n    install:\n      - id: d\n        kind: download\n        url: https://example.com/x.zip\n        sha256: " + "7" * 64 + "\n---\nb")
    s = build_report(collect_assets([], [d], None, None, None))["skills"][0]
    sp = s["metadata_openclaw"]["install_specs"][0]
    assert sp["sha256_declared"] is True and sp["sha256_state"] == "invalid_type"


def test_valid_and_absent_digests_do_not_raise_the_issue(tmp_path):
    for i, sha in enumerate(({"sha256": GOOD}, {})):
        meta = json.dumps({"openclaw": {"install": [{"id": "d", "kind": "download", "url": "https://example.com/x.zip", **sha}]}})
        assert not [x for x in rep(tmp_path / str(i), meta=meta)["issues"] if x["code"] == "skill_install_sha256_invalid"]
