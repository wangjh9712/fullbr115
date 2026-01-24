from fastapi import APIRouter, HTTPException, Query, Path
from typing import List, Optional
from app.services.nullbr import nullbr_service
from app.models.schemas import MediaResource, ResourceAvailability

router = APIRouter(prefix="/resources", tags=["Resources (Nullbr)"])

# --- 辅助过滤函数 ---
def _filter_results(
    resources: List[MediaResource], 
    min_resolution: Optional[str], 
    require_zh: bool,
    source_type: Optional[str]
) -> List[MediaResource]:
    filtered = []
    for res in resources:
        if source_type and res.link_type != source_type:
            continue
        if require_zh and res.link_type in ['magnet', 'ed2k'] and not res.has_chinese_subtitle:
            continue
        if min_resolution and res.resolution:
            if min_resolution.lower() not in res.resolution.lower():
                continue
        filtered.append(res)
    return filtered

# --- Availability Checks (New) ---

@router.get("/availability/tv/{tmdb_id}/season/{season_number}", response_model=ResourceAvailability)
def check_season_availability(
    tmdb_id: int,
    season_number: int
):
    """Check if resources exist for a specific TV season"""
    return nullbr_service.get_season_availability(tmdb_id, season_number)

@router.get("/availability/tv/{tmdb_id}/season/{season_number}/episode/{episode_number}", response_model=ResourceAvailability)
def check_episode_availability(
    tmdb_id: int,
    season_number: int,
    episode_number: int
):
    """Check if resources exist for a specific TV episode"""
    return nullbr_service.get_episode_availability(tmdb_id, season_number, episode_number)

# --- 电影接口 ---
@router.get("/movie/{tmdb_id}", response_model=List[MediaResource])
def get_movie_resources(
    tmdb_id: int,
    min_resolution: Optional[str] = Query(None),
    require_zh: bool = Query(False),
    source_type: Optional[str] = Query(None, description="'115_share', 'magnet', 'ed2k'")
):
    """获取电影资源：整合 115分享 + 磁力 + Ed2k"""
    try:
        results = nullbr_service.fetch_movie(tmdb_id)
        return _filter_results(results, min_resolution, require_zh, source_type)
    except Exception as e:
        if "429" in str(e):
            # 返回 429 状态码给前端
            raise HTTPException(
                status_code=429, 
                detail="Nullbr API 速率限制，请稍后再试。"
            )
        # 其他错误返回 500 或保持原样
        raise HTTPException(status_code=500, detail=str(e))

# --- 电视剧接口 ---
@router.get("/tv/{tmdb_id}", response_model=List[MediaResource])
def get_tv_packs(tmdb_id: int):
    try:
        return nullbr_service.fetch_tv_packs(tmdb_id)
    except Exception as e:
        if "429" in str(e):
            # 返回 429 状态码给前端
            raise HTTPException(
                status_code=429, 
                detail="Nullbr API 速率限制，请稍后再试。"
            )
        # 其他错误返回 500 或保持原样
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tv/{tmdb_id}/season/{season_number}", response_model=List[MediaResource])
def get_tv_season_resources(
    tmdb_id: int,
    season_number: int = Path(..., ge=0),
    min_resolution: Optional[str] = Query(None),
    require_zh: bool = Query(False)
):
    results = nullbr_service.fetch_tv_season(tmdb_id, season_number)
    try:
        return _filter_results(results, min_resolution, require_zh, None)
    except Exception as e:
        if "429" in str(e):
            # 返回 429 状态码给前端
            raise HTTPException(
                status_code=429, 
                detail="Nullbr API 速率限制，请稍后再试。"
            )
        # 其他错误返回 500 或保持原样
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tv/{tmdb_id}/season/{season_number}/episode/{episode_number}", response_model=List[MediaResource])
def get_tv_episode_resources(
    tmdb_id: int,
    season_number: int = Path(..., ge=0),
    episode_number: int = Path(..., ge=1),
    min_resolution: Optional[str] = Query(None),
    require_zh: bool = Query(False)
):
    results = nullbr_service.fetch_tv_episode(tmdb_id, season_number, episode_number)
    try:
        return _filter_results(results, min_resolution, require_zh, None)
    except Exception as e:
        if "429" in str(e):
            # 返回 429 状态码给前端
            raise HTTPException(
                status_code=429, 
                detail="Nullbr API 速率限制，请稍后再试。"
            )
        # 其他错误返回 500 或保持原样
        raise HTTPException(status_code=500, detail=str(e))