from pathlib import Path

import pytest

from yapping.ocg import (
    engine_paths,
    fluoro_assets_ready,
    ignis_assets_ready,
    make_duel,
)

REPO = Path(__file__).resolve().parents[1]


def test_engine_paths_do_not_cross_stacks():
    fluoro_cdb, fluoro_scripts = engine_paths("fluoro")
    ignis_cdb, ignis_scripts = engine_paths("ignis")
    assert fluoro_cdb == REPO / "assets" / "cards.cdb"
    assert ignis_cdb == REPO / "assets" / "ignis" / "cards.cdb"
    assert fluoro_scripts.name == "fluorohydride-ygopro-scripts"
    assert ignis_scripts.name == "projectignis-card-scripts"
    assert fluoro_cdb != ignis_cdb
    assert fluoro_scripts != ignis_scripts


def test_make_duel_rejects_unknown_engine():
    with pytest.raises(ValueError, match="engine"):
        make_duel("edo")


@pytest.mark.skipif(not fluoro_assets_ready(), reason="Fluoro cdb/scripts missing")
def test_make_duel_fluoro_returns_existing_adapter():
    duel = make_duel("fluoro")
    assert type(duel).__module__ == "yapping._ocgcore"
