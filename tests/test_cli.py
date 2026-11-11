from pathlib import Path

from notes_repo.cli import main

SEED = Path(__file__).resolve().parent.parent / "seed" / "notes"


def run(tmp_path, *args):
    return main(["--db", str(tmp_path / "cli.db"), *args])


def test_full_workflow_from_the_command_line(tmp_path, capsys):
    assert run(tmp_path, "import", str(SEED)) == 0
    assert run(tmp_path, "search", "gowning") == 0
    assert "Technician B: gowning and safety" in capsys.readouterr().out

    assert run(tmp_path, "draft", "graphene-coating-study") == 0
    assert run(tmp_path, "approve", "1", "--drop-flagged") == 0
    assert run(tmp_path, "index", "graphene-coating-study", "--out", str(tmp_path / "site")) == 0
    assert (tmp_path / "site" / "graphene-coating-study" / "index.html").exists()
    assert run(tmp_path, "export-xlsx", str(tmp_path / "t.xlsx")) == 0
    assert (tmp_path / "t.xlsx").exists()


def test_ollama_drafter_needs_a_model_name(tmp_path, capsys):
    run(tmp_path, "import", str(SEED))
    assert run(tmp_path, "draft", "cleanroom-interviews", "--drafter", "ollama", "--model", "") == 2
    assert "--model is required" in capsys.readouterr().err


def test_approving_twice_is_reported_as_an_error(tmp_path, capsys):
    run(tmp_path, "import", str(SEED))
    run(tmp_path, "draft", "cleanroom-interviews")
    assert run(tmp_path, "approve", "1") == 0
    assert run(tmp_path, "approve", "1") == 1
    assert "already approved" in capsys.readouterr().err
