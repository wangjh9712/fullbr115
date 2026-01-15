from fastapi import APIRouter, Query, Path, HTTPException
from typing import Optional, List
from app.services.tmdb import tmdb_service
from app.models.schemas import SearchResult, MediaDetail, Season, Genre

router = APIRouter(prefix="/tmdb", tags=["Metadata"])

# --- 辅助接口 ---
@router.get("/genres/{media_type}", response_model=List[Genre])
async def get_genre_list(media_type: str = Path(..., pattern="^(movie|tv)$")):
    """
    获取类型 ID 对照表 (供筛选使用)
    例如: 动作=28, 剧情=18
    """
    raw_list = tmdb_service.get_genres(media_type)
    return [Genre(id=g['id'], name=g['name']) for g in raw_list]

# --- 核心发现接口 ---
@router.get("/discover/{media_type}", response_model=SearchResult)
async def discover_media(
    media_type: str = Path(..., pattern="^(movie|tv)$"),
    page: int = 1,
    sort_by: str = Query("popularity.desc", description="排序方式: popularity.desc, vote_average.desc, primary_release_date.desc"),
    with_genres: Optional[str] = Query(None, description="类型ID，逗号分隔，例如 '18,28'"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    min_vote: float = Query(0, description="最低评分 (0-10)"),
    min_vote_count: int = Query(0, description="最少评分人数 (建议设置>50以过滤冷门片)")
):
    """
    探索发现影视资源 (核心功能)
    
    常见用例:
    1. **近期热门电影**: sort_by=popularity.desc & start_date=2024-01-01
    2. **高分经典**: sort_by=vote_average.desc & min_vote_count=1000
    3. **特定类型**: with_genres=18 (剧情)
    """
    return tmdb_service.discover_media(
        media_type=media_type,
        page=page,
        sort_by=sort_by,
        with_genres=with_genres,
        start_date=start_date,
        end_date=end_date,
        min_vote=min_vote,
        min_vote_count=min_vote_count
    )

# --- 搜索 Search ---
@router.get("/search", response_model=SearchResult)
async def search_media(
    query: str, 
    page: int = 1,
):
    """
    搜索影视剧，支持评分区间筛选
    """
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    return tmdb_service.search_media(query, page)

# --- 详情 Details ---
@router.get("/details/{media_type}/{tmdb_id}", response_model=MediaDetail)
async def get_media_details(
    media_type: str = Path(..., pattern="^(movie|tv)$"),
    tmdb_id: int = Path(...)
):
    """
    获取超级详细信息：包含导演、演员、类型、推荐、相似
    如果是电视剧，会列出所有季的基础信息
    """
    try:
        return tmdb_service.get_details_full(media_type, tmdb_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Media not found or TMDB error: {str(e)}")

# --- 剧集特有 TV Specific ---
@router.get("/details/tv/{tmdb_id}/season/{season_number}", response_model=Season)
async def get_season_details(tmdb_id: int, season_number: int):
    """
    获取某季的具体分集信息
    """
    try:
        return tmdb_service.get_season_details(tmdb_id, season_number)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))