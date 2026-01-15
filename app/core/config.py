from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    TMDB_API_KEY: str
    TMDB_LANGUAGE: str = "zh-CN"
    NULLBR_API_KEY: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()