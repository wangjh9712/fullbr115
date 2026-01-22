from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    TMDB_API_KEY: str
    TMDB_LANGUAGE: str = "zh-CN"
    NULLBR_APP_ID: str = ""
    NULLBR_API_KEY: str = ""
    PROXY_URL: Optional[str] = None
    P115_COOKIE: str = ""
    P115_SAVE_PATH: str = ""
    P115_DOWNLOAD_PATH: str = ""
    MOVIEPILOT_URL: Optional[str] = None
    MOVIEPILOT_APIKEY: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()