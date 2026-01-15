from nullbr import NullbrSDK
from app.core.config import settings
from app.models.schemas import MediaResource
from typing import List

class NullbrService:
    def __init__(self):
        # 初始化 SDK
        if settings.NULLBR_API_KEY and settings.NULLBR_APP_ID:
            self.client = NullbrSDK(
                app_id=settings.NULLBR_APP_ID, 
                api_key=settings.NULLBR_API_KEY,
                user_agent='fullbr115/development'
            )
        else:
            self.client = None
            print("Warning: Nullbr API Key or App ID not set.")

    def _parse_sdk_item(self, item, link_type: str) -> MediaResource:
        """
        将 SDK 的各种 Item 对象统一转换为 MediaResource 模型
        """
        # SDK中，电影/剧集本身用 title，单集/文件用 name
        title = getattr(item, 'title', getattr(item, 'name', 'Unknown'))
        
        # 提取链接
        link = ""
        if link_type == '115_share':
            link = getattr(item, 'share_link', '')
        elif link_type == 'ed2k':
            link = getattr(item, 'ed2k', '')
        elif link_type == 'magnet':
            link = getattr(item, 'magnet', '')

        # 提取中文字幕 (仅 Ed2k/Magnet 对象有 zh_sub 属性)
        has_zh = False
        if hasattr(item, 'zh_sub'):
            has_zh = bool(getattr(item, 'zh_sub'))

        return MediaResource(
            title=title,
            size=getattr(item, 'size', ''),
            link=link,
            link_type=link_type,
            resolution=getattr(item, 'resolution', None),
            quality=getattr(item, 'quality', None),
            source=getattr(item, 'source', None),
            has_chinese_subtitle=has_zh,
            season_list=getattr(item, 'season_list', None)
        )

    def fetch_movie(self, tmdb_id: int) -> List[MediaResource]:
        """获取电影的所有资源 (115 + Magnet + Ed2k)"""
        if not self.client: return []
        resources = []
        
        try:
            # 1. 115 Share
            r1 = self.client.get_movie_115(tmdb_id)
            if r1 and r1.items: resources.extend([self._parse_sdk_item(i, '115_share') for i in r1.items])
            
            # 2. Magnet
            r2 = self.client.get_movie_magnet(tmdb_id)
            if r2 and r2.magnet: resources.extend([self._parse_sdk_item(i, 'magnet') for i in r2.magnet])
            
            # 3. Ed2k
            r3 = self.client.get_movie_ed2k(tmdb_id)
            if r3 and r3.ed2k: resources.extend([self._parse_sdk_item(i, 'ed2k') for i in r3.ed2k])
        except Exception as e:
            print(f"Error fetching movie resources for {tmdb_id}: {e}")
            
        return resources

    def fetch_tv_packs(self, tmdb_id: int) -> List[MediaResource]:
        """仅获取剧集的 115 整合包 (通常包含全季)"""
        if not self.client: return []
        try:
            #
            r = self.client.get_tv_115(tmdb_id)
            if r and r.items:
                return [self._parse_sdk_item(i, '115_share') for i in r.items]
        except Exception as e:
            print(f"Error fetching TV packs for {tmdb_id}: {e}")
        return []

    def fetch_tv_season(self, tmdb_id: int, season_number: int) -> List[MediaResource]:
        """获取特定季度的资源 (目前SDK文档仅显示支持 Season Magnet)"""
        if not self.client: return []
        resources = []
        try:
            # - get_tv_season_magnet
            r = self.client.get_tv_season_magnet(tmdb_id, season_number)
            if r and r.magnet:
                resources.extend([self._parse_sdk_item(i, 'magnet') for i in r.magnet])
        except Exception as e:
            print(f"Error fetching TV Season {season_number}: {e}")
        return resources

    def fetch_tv_episode(self, tmdb_id: int, season_number: int, episode_number: int) -> List[MediaResource]:
        """获取特定集数的资源 (Magnet + Ed2k)"""
        if not self.client: return []
        resources = []
        try:
            # 1. Episode Magnet
            r_mag = self.client.get_tv_episode_magnet(tmdb_id, season_number, episode_number)
            if r_mag and r_mag.magnet:
                resources.extend([self._parse_sdk_item(i, 'magnet') for i in r_mag.magnet])

            # 2. Episode Ed2k
            r_ed2k = self.client.get_tv_episode_ed2k(tmdb_id, season_number, episode_number)
            if r_ed2k and r_ed2k.ed2k:
                resources.extend([self._parse_sdk_item(i, 'ed2k') for i in r_ed2k.ed2k])
        except Exception as e:
            print(f"Error fetching TV Episode S{season_number}E{episode_number}: {e}")
        return resources

nullbr_service = NullbrService()