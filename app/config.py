from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/agent_cost_tracker"
    alert_threshold_pct: int = 80

    model_config = {"env_file": ".env"}


settings = Settings()
