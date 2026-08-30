import os

from dr.config import load_env


def test_loads_key_value_pairs(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('ANTHROPIC_API_KEY="sk-ant-ficticia"\n', encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    loaded = load_env(env_file)
    assert loaded["ANTHROPIC_API_KEY"] == "sk-ant-ficticia"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-ficticia"


def test_does_not_override_the_real_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=del-fichero\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "del-entorno")
    load_env(env_file)
    assert os.environ["ANTHROPIC_API_KEY"] == "del-entorno"


def test_ignores_comments_and_blank_lines(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# comentario\n\nFOO=bar\n", encoding="utf-8")
    monkeypatch.delenv("FOO", raising=False)
    assert load_env(env_file) == {"FOO": "bar"}


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env(tmp_path / "no-existe.env") == {}
