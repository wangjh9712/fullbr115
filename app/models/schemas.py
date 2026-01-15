from pydantic import BaseModel, Field
from typing import Optional, List

# --- 基础组件 ---
class Genre(BaseModel):
    id: int
    name: str

class Person(BaseModel):
    id: int
    name: str
    character: Optional[str] = None # 饰演角色 (演员用)
    job: Optional[str] = None       # 职位 (导演/编剧用)
    profile_path: Optional[str] = None

# --- 基础媒体信息 (列表页用) ---
class MediaMeta(BaseModel):
    tmdb_id: int
    title: str
    original_title: str
    media_type: str  # 'movie' or 'tv'
    release_date: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    overview: Optional[str] = None
    vote_average: float = 0.0
    genre_ids: List[int] = [] # 列表页通常只有ID

# --- 剧集特有结构 ---
class Episode(BaseModel):
    id: int
    episode_number: int
    season_number: int
    name: str
    overview: Optional[str] = None
    still_path: Optional[str] = None
    air_date: Optional[str] = None
    vote_average: float = 0.0

class Season(BaseModel):
    id: int
    season_number: int
    name: str
    poster_path: Optional[str] = None
    episode_count: int
    air_date: Optional[str] = None
    episodes: List[Episode] = [] # 获取特定季详情时填充

# --- 详细信息 (详情页用) ---
class MediaDetail(MediaMeta):
    genres: List[Genre] = []
    tagline: Optional[str] = None
    status: Optional[str] = None
    # 演职员
    directors: List[Person] = []
    cast: List[Person] = [] # 通常取前10-20位
    # 关联推荐
    recommendations: List[MediaMeta] = []
    similar: List[MediaMeta] = []
    # 电视剧特有
    seasons: List[Season] = [] 

class SearchResult(BaseModel):
    total_results: int
    page: int
    results: List[MediaMeta]