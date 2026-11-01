"""Private DeepSeek settings. Public responses never include the API key."""

import os

from pydantic import Field, SecretStr

from .models import Contract
from .storage import Problem

BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"


class APISettings(Contract):
    model: str = Field(default=DEFAULT_MODEL, pattern=r"^[a-zA-Z0-9._/-]{1,120}$")
    api_key: SecretStr | None = None
    remove_key: bool = False


class ProviderSettings:
    def __init__(self, store):
        self.store = store

    def private(self):
        try:
            return self.store.read("settings", "deepseek")
        except Problem as exc:
            if exc.status != 404:
                raise
            return {"model": os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
                    "api_key": os.environ.get("DEEPSEEK_API_KEY", "")}

    def public(self):
        settings = self.private()
        return {"provider": "deepseek", "base_url": BASE_URL, "model": settings["model"],
                "has_key": bool(settings.get("api_key")), "thinking": "disabled",
                "key_storage": "server_private_file_or_environment"}

    def update(self, request):
        with self.store.lock:
            current = self.private()
            key = request.api_key.get_secret_value().strip() if request.api_key else ""
            if key and (len(key) > 512 or any(c.isspace() for c in key)):
                raise Problem(422, "密钥格式不正确（不包含空白，长度不超过 512）")
            current["model"] = request.model
            if request.remove_key:
                current["api_key"] = ""
            elif key:
                current["api_key"] = key
            self.store.write("settings", "deepseek", current)
        return self.public()
