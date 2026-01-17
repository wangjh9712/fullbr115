from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any

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

# --- 资源可用性 (New) ---
class ResourceAvailability(BaseModel):
    has_115: bool = False
    has_magnet: bool = False
    has_ed2k: bool = False
    has_video: bool = False

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
    # 资源可用性
    availability: Optional[ResourceAvailability] = None

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

    @field_validator('quality', 'source', mode='before')
    def parse_list_fields(cls, v):
        """处理 quality, source 字段可能是列表的情况"""
        if isinstance(v, list):
            return ", ".join([str(i) for i in v])
        return v

    @field_validator('has_chinese_subtitle', mode='before')
    def parse_zh_sub(cls, v):
        """处理 int 类型的 bool"""
        if isinstance(v, int):
            return bool(v)
        return v

# --- 115转存与离线下载 ---
class P115ShareFile(BaseModel):
    id: str = Field(..., description="文件ID或目录ID")
    parent_id: str = Field(..., description="父目录ID")
    name: str = Field(..., description="文件名")
    size: Optional[str] = Field(None, description="文件大小")
    is_dir: bool = Field(False, description="是否为目录")
    pick_code: str = Field(..., description="提取码")
    sha1: Optional[str] = None

class P115ShareListRequest(BaseModel):
    share_link: str = Field(..., description="115分享链接")
    cid: Optional[str] = Field("0", description="要查看的目录ID，默认为根目录0")
    password: Optional[str] = Field(None, description="提取码/密码，如果链接中不包含则需要填写")

class P115ShareSaveRequest(BaseModel):
    share_link: str = Field(..., description="115分享链接")
    file_ids: List[str] = Field(..., description="要转存的文件/目录ID列表")
    password: Optional[str] = Field(None, description="提取码/密码")
    to_cid: Optional[str] = Field(None, description="目标目录ID，如果不填则使用配置的 P115_SAVE_PATH") 

class P115OfflineAddRequest(BaseModel):
    urls: List[str] = Field(..., description="下载链接列表 (http/ftp/magnet/ed2k)")
    to_cid: Optional[str] = Field(None, description="目标目录ID，如果不填则使用配置的 P115_DOWNLOAD_PATH")

class P115Response(BaseModel):
    state: bool
    message: str = "Success"
    data: Any = None

class P115FileListRequest(BaseModel):
    cid: str = Field("0", description="要浏览的目录ID，默认为根目录0")
    limit: int = Field(100, description="每页数量")
    offset: int = Field(0, description="偏移量")

class P115File(BaseModel):
    id: str = Field(..., description="文件ID或目录ID")
    parent_id: str = Field(..., description="父目录ID")
    name: str = Field(..., description="文件名")
    size: Optional[str] = Field(None, description="文件大小")
    is_dir: bool = Field(False, description="是否为目录")
    pick_code: str = Field(..., description="提取码")
    time: str = Field(..., description="修改时间")