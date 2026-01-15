from fastapi import APIRouter, HTTPException, Query, Path
from typing import List, Optional
from app.services.nullbr import nullbr_service
from app.models.schemas import MediaResource

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
        # 类型筛选 (e.g. 只看 115_share)
        if source_type and res.link_type != source_type:
            continue
        # 字幕筛选 (仅 Magnet/Ed2k 支持检测)
        if require_zh and res.link_type in ['magnet', 'ed2k'] and not res.has_chinese_subtitle:
            continue
        # 分辨率筛选
        if min_resolution and res.resolution:
            if min_resolution.lower() not in res.resolution.lower():
                continue
        filtered.append(res)
    return filtered

# --- 电影接口 ---
@router.get("/movie/{tmdb_id}", response_model=List[MediaResource])
def get_movie_resources(
    tmdb_id: int,
    min_resolution: Optional[str] = Query(None),
    require_zh: bool = Query(False),
    source_type: Optional[str] = Query(None, description="'115_share', 'magnet', 'ed2k'")
):
    """获取电影资源：整合 115分享 + 磁力 + Ed2k"""
    results = nullbr_service.fetch_movie(tmdb_id)
    return _filter_results(results, min_resolution, require_zh, source_type)

# --- 电视剧接口 1: 整合包 (115) ---
@router.get("/tv/{tmdb_id}", response_model=List[MediaResource])
def get_tv_packs(
    tmdb_id: int
):
    """获取剧集整合包 (通常为115分享链接，包含全季或全集)"""
    return nullbr_service.fetch_tv_packs(tmdb_id)

# --- 电视剧接口 2: 季资源 ---
@router.get("/tv/{tmdb_id}/season/{season_number}", response_model=List[MediaResource])
def get_tv_season_resources(
    tmdb_id: int,
    season_number: int = Path(..., ge=0),
    min_resolution: Optional[str] = Query(None),
    require_zh: bool = Query(False)
):
    """
    获取某季度的资源 (Magnet)
    Nullbr SDK 目前仅支持获取季度的 Magnet 列表
    """
    results = nullbr_service.fetch_tv_season(tmdb_id, season_number)
    return _filter_results(results, min_resolution, require_zh, None)

# --- 电视剧接口 3: 集资源 ---
@router.get("/tv/{tmdb_id}/season/{season_number}/episode/{episode_number}", response_model=List[MediaResource])
def get_tv_episode_resources(
    tmdb_id: int,
    season_number: int = Path(..., ge=0),
    episode_number: int = Path(..., ge=1),
    min_resolution: Optional[str] = Query(None),
    require_zh: bool = Query(False)
):
    """
    获取单集的资源 (Magnet + Ed2k)
    """
    results = nullbr_service.fetch_tv_episode(tmdb_id, season_number, episode_number)
    return _filter_results(results, min_resolution, require_zh, None)