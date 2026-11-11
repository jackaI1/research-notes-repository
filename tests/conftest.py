from pathlib import Path

import pytest

from notes_repo import db
from notes_repo.importers import import_path
from notes_repo.taxonomy import Taxonomy

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed" / "notes"


@pytest.fixture
def taxonomy():
    return Taxonomy.load(ROOT / "taxonomy.json")


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn, taxonomy):
    """A database holding the synthetic seed notes."""
    report = import_path(conn, taxonomy, SEED)
    assert report.errors == []
    return conn
