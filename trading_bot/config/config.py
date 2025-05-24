from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # два уровня вверх
ENV_PATH = BASE_DIR / ".env"
print(ENV_PATH)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, env_file_encoding="utf-8")
    TOKEN: str = Field(alias="token")
    account_id: str = Field(alias="account_id")

if __name__ == '__main__':
    print(Config().TOKEN)
