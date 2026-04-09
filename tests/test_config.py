# tests/test_config.py
import os
import tempfile
import pytest
from cwmcp.config import load_config, ConfigError

def test_load_config_reads_properties(tmp_path):
    config_file = tmp_path / "config.properties"
    config_file.write_text(
        "cwbe_user=test@example.com\n"
        "cwbe_password=secret123\n"
        "content_path=/tmp/audio\n"
        "cwtts_url=http://localhost:8100\n"
    )
    config = load_config(str(config_file))
    assert config.cwbe_user == "test@example.com"
    assert config.cwbe_password == "secret123"
    assert config.content_path == "/tmp/audio"
    assert config.cwtts_url == "http://localhost:8100"

def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/config.properties")

def test_load_config_missing_required_field(tmp_path):
    config_file = tmp_path / "config.properties"
    config_file.write_text("cwbe_user=test@example.com\n")
    with pytest.raises(ConfigError, match="cwbe_password"):
        load_config(str(config_file))

def test_load_config_ignores_comments_and_blank_lines(tmp_path):
    config_file = tmp_path / "config.properties"
    config_file.write_text(
        "# This is a comment\n"
        "\n"
        "cwbe_user=test@example.com\n"
        "cwbe_password=secret123\n"
        "content_path=/tmp/audio\n"
    )
    config = load_config(str(config_file))
    assert config.cwbe_user == "test@example.com"

def test_load_config_defaults(tmp_path):
    config_file = tmp_path / "config.properties"
    config_file.write_text(
        "cwbe_user=test@example.com\n"
        "cwbe_password=secret123\n"
        "content_path=/tmp/audio\n"
    )
    config = load_config(str(config_file))
    assert config.cwtts_url == "http://localhost:8100"
    assert config.elevenlabs_api_key == ""
