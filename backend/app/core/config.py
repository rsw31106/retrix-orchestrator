from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # MySQL
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 13306
    mysql_user: str = "root"
    mysql_password: str = "roh8966"
    mysql_database: str = "retrix"

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: Optional[str] = None

    # API Keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    minimax_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    domain: str = "retrix.rebitgames.com"
    env: str = "production"
    secret_key: str = "change-this-to-random-string"

    # Auth (single admin user)
    admin_username: str = "admin"
    admin_password_hash: str = ""  # SHA256 hash, set via init-admin command

    # GitHub
    github_token: str = ""
    github_org: str = ""  # optional: org name for repo creation

    # Workspace (where workers operate)
    workspace_root: str = "D:\\Projects"  # default root for project workspaces

    # Budget
    daily_budget_limit: float = 5.0
    project_budget_limit: float = 2.0

    # Notifications
    slack_webhook_url: str = ""

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def async_mysql_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
