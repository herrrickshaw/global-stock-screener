# Tests for the decision register parser + validation + dashboard card.
import decisions
import repo_dashboard as rd


def test_register_parses_and_is_valid():
    recs = decisions.load()
    assert len(recs) >= 10  # the seeded ADRs
    ids = [r.id for r in recs]
    assert "ADR-01" in ids and len(ids) == len(set(ids))  # unique
    assert decisions.validate() == []  # structurally valid


def test_records_have_impact():
    for r in decisions.load():
        assert r.impact, f"{r.id} missing Impact"
        assert r.status in decisions.VALID_STATUS


def test_by_status_filter():
    accepted = decisions.by_status("accepted")
    assert accepted and all(d.status == "accepted" for d in accepted)


def test_validate_flags_bad_status(tmp_path):
    bad = tmp_path / "DECISIONS.md"
    bad.write_text(
        "- **ADR-01 — Thing** `banana` (2026-01-01)\n"
        "  - **Context** — c\n  - **Decision** — d\n  - **Impact** — i\n"
    )
    probs = decisions.validate(bad)
    assert any("invalid status" in p for p in probs)


def test_validate_flags_missing_field(tmp_path):
    bad = tmp_path / "DECISIONS.md"
    bad.write_text("- **ADR-01 — Thing** `accepted` (2026-01-01)\n  - **Context** — c\n")
    probs = decisions.validate(bad)
    assert any("missing Decision" in p for p in probs) and any("missing Impact" in p for p in probs)


def test_dashboard_card_renders():
    html = rd._decision_register(5)
    assert "ADR-" in html and "decisions logged" in html
    assert "Impact" in html
