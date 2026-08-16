from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLUORO_CDB = REPO / "assets" / "cards.cdb"
IGNIS_CDB = REPO / "assets" / "ignis" / "cards.cdb"
FLUORO_SCRIPTS = REPO.parent / "fluorohydride-ygopro-scripts"
IGNIS_SCRIPTS = REPO.parent / "projectignis-card-scripts"


def engine_paths(engine: str) -> tuple[Path, Path]:
    if engine == "fluoro":
        return FLUORO_CDB, FLUORO_SCRIPTS
    if engine == "ignis":
        return IGNIS_CDB, IGNIS_SCRIPTS
    raise ValueError(f"unknown engine: {engine}")


def fluoro_assets_ready() -> bool:
    cdb, scripts = engine_paths("fluoro")
    return cdb.is_file() and (scripts / "constant.lua").is_file()


def ignis_assets_ready() -> bool:
    cdb, scripts = engine_paths("ignis")
    return cdb.is_file() and (scripts / "constant.lua").is_file()


def make_duel(engine: str = "fluoro"):
    database, scripts = engine_paths(engine)
    if engine == "fluoro":
        from yapping._ocgcore import Duel

        return Duel(str(database), str(scripts))
    from yapping._ocgcore_ignis import Duel

    return Duel(str(database), str(scripts))
