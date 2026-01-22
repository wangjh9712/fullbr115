import json
import os
import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.models.schemas import Subscription, SubscriptionRequest
from app.services.tmdb import tmdb_service
from app.services.nullbr import nullbr_service
from app.services.p115 import p115_service
from app.core.config import settings

DATA_FILE = "data/subscriptions.json"

class SubscriptionService:
    def __init__(self):
        self._ensure_data_file()
        self.subscriptions: List[Subscription] = self._load_data()
        self.is_running = False

    def _ensure_data_file(self):
        if not os.path.exists("data"):
            os.makedirs("data")
        if not os.path.exists(DATA_FILE):
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _load_data(self) -> List[Subscription]:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Subscription(**item) for item in data]
        except Exception:
            return []

    def _save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([s.dict() for s in self.subscriptions], f, ensure_ascii=False, indent=2)

    def _parse_size(self, size_str: str) -> float:
        """解析文件大小字符串为字节数值，用于比较大小"""
        if not size_str: return 0.0
        try:
            match = re.search(r'([\d.]+)\s*([a-zA-Z]+)', str(size_str), re.IGNORECASE)
            if not match: return 0.0
            num = float(match.group(1))
            unit = match.group(2).upper()
            units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
            return num * units.get(unit, 1)
        except Exception:
            return 0.0

    def _extract_max_episode(self, filename: str, default_ep: int) -> int:
        """
        [新增] 从文件名中解析覆盖的最大集数
        例如: 
        - "...[第13-16集]..." -> 返回 16
        - "...S01E13-E16..." -> 返回 16
        - "...EP14..." -> 返回 14 (或 default_ep)
        """
        try:
            name = filename.upper()
            
            # 模式1: 中文范围 [第13-16集]
            zh_range = re.search(r'第(\d+)[-~](\d+)集', name)
            if zh_range:
                end = int(zh_range.group(2))
                return max(end, default_ep)

            # 模式2: 英文范围 E13-E16, E13-16, EP13-16
            en_range = re.search(r'[E|EP](\d+)[-~][E|EP]?(\d+)', name)
            if en_range:
                end = int(en_range.group(2))
                # 简单过滤：如果解析出特别大的数字(比如年份2026)，忽略
                if end < 1900: 
                    return max(end, default_ep)

            # 模式3: 单集 E14 (用于校验，暂时只返回 default)
            return default_ep
        except Exception:
            return default_ep

    async def add_subscription(self, req: SubscriptionRequest):
        sub_id = f"{req.media_type}_{req.tmdb_id}"
        if req.media_type == 'tv':
            sub_id += f"_s{req.season_number}"

        for sub in self.subscriptions:
            if sub.id == sub_id:
                return {"success": False, "message": "已在订阅列表中"}

        new_sub = Subscription(
            id=sub_id,
            tmdb_id=req.tmdb_id,
            media_type=req.media_type,
            title=req.title,
            poster_path=req.poster_path,
            next_check_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        try:
            # 1. 初始化元数据
            if req.media_type == 'movie':
                details = await asyncio.to_thread(tmdb_service.get_details_full, 'movie', req.tmdb_id)
                new_sub.release_date = details.release_date
                new_sub.message = f"等待上映 ({new_sub.release_date})"
            else:
                new_sub.season_number = req.season_number
                season_info = await asyncio.to_thread(tmdb_service.get_season_details, req.tmdb_id, req.season_number)
                new_sub.total_episodes = season_info.episode_count
                
                air_dates = {}
                for ep in season_info.episodes:
                    if ep.air_date:
                        air_dates[str(ep.episode_number)] = ep.air_date
                new_sub.episode_air_dates = air_dates
                new_sub.current_episode = max(0, req.start_episode - 1)
                new_sub.message = f"订阅至第 {req.season_number} 季，从第 {req.start_episode} 集开始"

                # 2. 剧集专属文件夹逻辑
                base_path = settings.P115_DOWNLOAD_PATH or ""
                target_path = f"{base_path}/{req.title}".replace("//", "/")
                try:
                    cid = await asyncio.to_thread(p115_service.get_target_cid, target_path)
                    new_sub.save_cid = str(cid)
                    print(f"Created/Resolved folder for {req.title}: CID {cid}")
                except Exception as e:
                    print(f"Failed to create folder for {req.title}: {e}")
                    new_sub.message += " (注意: 文件夹创建失败，使用默认目录)"

        except Exception as e:
            return {"success": False, "message": f"初始化失败: {str(e)}"}

        self.subscriptions.append(new_sub)
        self._save_data()

        # 立即触发检查 (异步非阻塞建议，但这里为了确保逻辑简单，直接 await)
        # 注意：如果追更集数多，这里可能会让前端请求 pending 几秒钟
        try:
            if new_sub.media_type == 'movie':
                await self._process_movie(new_sub)
            else:
                await self._process_tv(new_sub)
            self._save_data()
        except Exception:
            pass

        return {"success": True, "message": "订阅成功，后台已开始搜索资源"}

    def delete_subscription(self, sub_id: str):
        self.subscriptions = [s for s in self.subscriptions if s.id != sub_id]
        self._save_data()
        return {"success": True, "message": "删除成功"}

    def get_list(self):
        return self.subscriptions

    # --- 调度器 ---
    async def start_scheduler(self):
        if self.is_running: return
        self.is_running = True
        print("Starting Subscription Scheduler...")
        while True:
            try:
                await self.check_all_subscriptions()
            except Exception as e:
                print(f"Scheduler Error: {e}")
            await asyncio.sleep(3600)

    async def check_all_subscriptions(self):
        now = datetime.now()
        updated = False
        
        for sub in self.subscriptions:
            if sub.status == 'completed': continue
            
            if sub.next_check_time:
                try:
                    check_time = datetime.strptime(sub.next_check_time, "%Y-%m-%d %H:%M:%S")
                    if now < check_time: continue
                except: pass

            print(f"Checking subscription: {sub.title} ({sub.media_type})")
            
            try:
                if sub.media_type == 'movie':
                    await self._process_movie(sub)
                else:
                    await self._process_tv(sub)
                
                updated = True
                sub.last_check_time = now.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                print(f"Error checking {sub.title}: {e}")
                sub.message = f"检查出错: {str(e)}"
        
        if updated:
            self._save_data()

    async def _process_movie(self, sub: Subscription):
        today_str = datetime.now().strftime("%Y-%m-%d")
        if sub.release_date and sub.release_date > today_str:
            sub.message = f"尚未上映，等待 {sub.release_date}"
            sub.next_check_time = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            return

        resources = await asyncio.to_thread(nullbr_service.fetch_movie, sub.tmdb_id)
        valid_res = [r for r in resources if r.link and r.link_type in ['magnet', 'ed2k']]
        
        if valid_res:
            valid_res.sort(key=lambda x: self._parse_size(x.size), reverse=True)
            target = valid_res[0]
            movie_path = settings.P115_DOWNLOAD_PATH
            success = await self._perform_download(target, to_cid=sub.save_cid, save_path_str=movie_path)

            if success:
                sub.status = 'completed'
                sub.message = f"已获取资源: {target.title} ({target.size})"
            else:
                self._defer_check(sub, hours=8, msg="下载任务添加失败，稍后重试")
        else:
            self._defer_check(sub, hours=8, msg="暂无磁力/Ed2k资源")

    async def _process_tv(self, sub: Subscription):
        # [修改] 使用循环，一次性追完所有可用集数
        max_loops = 50 # 防止死循环的安全阈值
        loops = 0

        # 逻辑必须与 add_subscription 中的 target_path 逻辑一致
        base_path = settings.P115_DOWNLOAD_PATH or ""
        # 剧集路径通常为: 基础下载路径/剧集标题
        # 注意：这里我们通知 MoviePilot 扫描整个剧集文件夹，这样它能处理新增加的集数
        tv_show_path = f"{base_path}/{sub.title}".replace("//", "/")

        while loops < max_loops:
            loops += 1
            target_ep = sub.current_episode + 1
            
            # 1. 检查是否完结
            if sub.total_episodes > 0 and target_ep > sub.total_episodes:
                sub.status = 'completed'
                sub.message = "本季已完结"
                break # 退出循环

            # 2. 检查上映时间
            today_str = datetime.now().strftime("%Y-%m-%d")
            air_date = sub.episode_air_dates.get(str(target_ep))
            
            if air_date and air_date > today_str:
                sub.message = f"等待第 {target_ep} 集上映 ({air_date})"
                sub.next_check_time = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                break # 暂时无新集，退出循环，下次调度再查

            print(f"Fetching TV Resource: {sub.title} S{sub.season_number}E{target_ep}...")
            
            # 3. 获取资源
            resources = await asyncio.to_thread(
                nullbr_service.fetch_tv_episode, sub.tmdb_id, sub.season_number, target_ep
            )
            valid_res = [r for r in resources if r.link and r.link_type in ['magnet', 'ed2k']]

            if valid_res:
                # 排序
                valid_res.sort(key=lambda x: self._parse_size(x.size), reverse=True)
                target = valid_res[0]

                success = await self._perform_download(target, to_cid=sub.save_cid, save_path_str=tv_show_path)
                
                if success:
                    # [关键修改] 解析文件名，检测是否为打包资源
                    new_current = self._extract_max_episode(target.title, target_ep)
                    
                    # 确保集数是向前推进的
                    if new_current > target_ep:
                        print(f"Pack Detected: {target.title} covers up to {new_current}")
                        sub.current_episode = new_current
                        sub.message = f"已添加打包资源 ({target_ep}-{new_current})，继续搜索下一集"
                    else:
                        sub.current_episode = target_ep
                        sub.message = f"已添加第 {target_ep} 集 ({target.size})"

                    sub.next_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 稍微等待避免请求过快
                    await asyncio.sleep(2) 
                    # 成功后 CONTINUE，继续下一轮循环，搜索下一集
                    continue 
                else:
                    self._defer_check(sub, hours=8, msg=f"E{target_ep} 下载失败")
                    break # 下载失败，暂停追更
            else:
                self._defer_check(sub, hours=8, msg=f"第 {target_ep} 集暂无资源")
                break # 没资源，暂停追更

    def _defer_check(self, sub: Subscription, hours: int, msg: str):
        sub.message = msg
        sub.next_check_time = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    async def _perform_download(self, resource, to_cid: Optional[str] = None, save_path_str: Optional[str] = None) -> bool:
        """执行离线下载"""
        try:
            if resource.link_type not in ['magnet', 'ed2k']:
                return False
            res = await asyncio.to_thread(
                p115_service.add_offline_tasks, [resource.link], to_cid=to_cid, save_path_str=save_path_str
            )
            return res.get('success', False)
        except Exception as e:
            print(f"Download failed: {e}")
            return False

subscription_service = SubscriptionService()