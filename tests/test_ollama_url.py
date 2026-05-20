import os
from unittest.mock import patch

import termmon.scanner.ollama as ollama_mod


def test_ollama_url_defaults_to_localhost():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OLLAMA_URL", None)
        assert ollama_mod._ollama_url() == "http://localhost:11434"


def test_ollama_url_reads_env_var():
    with patch.dict(os.environ, {"OLLAMA_URL": "http://host.docker.internal:11434"}):
        assert ollama_mod._ollama_url() == "http://host.docker.internal:11434"
