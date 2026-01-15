from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Union, Any

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

# --- NULLBR 资源 ---
class MediaResource(BaseModel):
    """
    统一资源模型
    适配 Nullbr SDK 的三种资源类型: 115, Magnet, Ed2k
    """
    title: str              # 资源名称 (name or title)
    size: str               # 文件大小
    link: str               # 链接内容 (magnet, ed2k, or share_link)
    link_type: str          # '115_share', 'magnet', 'ed2k'
    
    # --- 详细元数据 ---
    resolution: Optional[str] = None    # e.g. "4K", "1080p"
    quality: Optional[str] = None       # e.g. "HDR10", "Remux"
    source: Optional[str] = None        # e.g. "Blu-ray"
    has_chinese_subtitle: bool = False  # zh_sub (1=True, 0=False)
    
    # --- 115特有 ---
    season_list: Optional[List[str]] = None # 仅 115 分享链接可能有此字段

    @field_validator('quality', mode='before')
    def parse_quality(cls, v):
        """处理 quality 字段可能是列表的情况"""
        if isinstance(v, list):
            return ", ".join(v)
        return v

    @field_validator('has_chinese_subtitle', mode='before')
    def parse_zh_sub(cls, v):
        """处理 int 类型的 bool"""
        if isinstance(v, int):
            return bool(v)
        return v