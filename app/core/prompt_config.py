from pathlib import Path
from functools import lru_cache

import yaml

from app.core.settings import BASE_DIR


_PROMPTS_PATH = BASE_DIR / "config" / "prompts.yaml"


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    with _PROMPTS_PATH.open("r", encoding="utf-8") as prompts_file:
        prompts = yaml.safe_load(prompts_file)
    return prompts["prompts"][name]["system"]
