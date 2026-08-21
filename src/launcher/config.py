from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get(
                "LAUNCHER_DATABASE_URL", "sqlite:///./launcher.db"
            ),
            llm_api_key=os.environ.get("LAUNCHER_LLM_API_KEY"),
            llm_base_url=os.environ.get(
                "LAUNCHER_LLM_BASE_URL", "https://api.openai.com/v1"
            ),
            llm_model=os.environ.get("LAUNCHER_LLM_MODEL", "gpt-4o-mini"),
        )
