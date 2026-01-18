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
            # 匹配数字和单位 (e.g., "1.5 GB", "300MB")
            match = re.search(r'([\d.]+)\s*([a-zA-Z]+)', str(size_str), re.IGNORECASE)
            if not match:
                return 0.0
            
            num = float(match.group(1))
            unit = match.group(2).upper()
            
            units = {
                'B': 1,
                'KB': 1024,
                'MB': 1024**2, 
                'GB': 1024**3, 
                'TB': 1024**4
            }
            return num * units.get(unit, 1)
        except Exception:
            return 0.0

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
            # 1. 初始化元数据 (TMDB)
            if req.media_type == 'movie':
                # 放入线程运行，避免阻塞
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

                # 2. 剧集专属文件夹逻辑 (P115)
                # 规则：P115_DOWNLOAD_PATH / 剧集标题
                # 如果没有配置下载路径，默认为根目录
                base_path = settings.P115_DOWNLOAD_PATH or ""
                # 拼接路径，去除多余斜杠
                target_path = f"{base_path}/{req.title}".replace("//", "/")
                
                # 获取或创建该目录的CID
                try:
                    cid = await asyncio.to_thread(p115_service.get_target_cid, target_path)
                    new_sub.save_cid = str(cid)
                    print(f"Created/Resolved folder for {req.title}: CID {cid}， Path: {target_path}")
                except Exception as e:
                    print(f"Failed to create folder for {req.title}: {e}")
                    # 失败不阻断订阅，但在消息中提示
                    new_sub.message += " (注意: 专属文件夹创建失败，将下载到默认目录)"

        except Exception as e:
            return {"success": False, "message": f"初始化失败: {str(e)}"}

        self.subscriptions.append(new_sub)
        self._save_data()
        return {"success": True, "message": "订阅成功"}

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
        print("Starting Subscription Scheduler (Magnet/Ed2k Only)...")
        while True:
            try:
                await self.check_all_subscriptions()
            except Exception as e:
                print(f"Scheduler Error: {e}")
            
            # 每 1 小时轮询一次
            await asyncio.sleep(3600)

    async def check_all_subscriptions(self):
        now = datetime.now()
        updated = False
        
        for sub in self.subscriptions:
            if sub.status == 'completed': continue
            
            # 检查时间间隔 (CD)
            if sub.next_check_time:
                try:
                    check_time = datetime.strptime(sub.next_check_time, "%Y-%m-%d %H:%M:%S")
                    if now < check_time:
                        continue
                except:
                    pass

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

        # 获取资源 (线程中运行)
        resources = await asyncio.to_thread(nullbr_service.fetch_movie, sub.tmdb_id)
        
        # 筛选：仅 Magnet 和 Ed2k
        valid_res = [r for r in resources if r.link and r.link_type in ['magnet', 'ed2k']]
        
        if valid_res:
            # 排序：按文件大小降序 (取最大文件)
            valid_res.sort(key=lambda x: self._parse_size(x.size), reverse=True)
            target = valid_res[0]
            
            # 电影通常不需要专属文件夹，或者使用 sub.save_cid (如果我们在电影订阅时也设定了的话)
            # 这里电影暂时使用默认下载路径，或者如果以后需要电影也单独文件夹，可以修改 add_subscription 逻辑
            success = await self._perform_download(target, to_cid=sub.save_cid)
            
            if success:
                sub.status = 'completed'
                sub.message = f"已获取资源: {target.title} ({target.size})"
            else:
                self._defer_check(sub, hours=8, msg="下载任务添加失败，稍后重试")
        else:
            self._defer_check(sub, hours=8, msg="暂无磁力/Ed2k资源")

    async def _process_tv(self, sub: Subscription):
        target_ep = sub.current_episode + 1
        
        if sub.total_episodes > 0 and target_ep > sub.total_episodes:
            sub.status = 'completed'
            sub.message = "本季已完结"
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        air_date = sub.episode_air_dates.get(str(target_ep))
        
        if air_date and air_date > today_str:
            sub.message = f"等待第 {target_ep} 集上映 ({air_date})"
            sub.next_check_time = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            return

        # 获取单集资源
        resources = await asyncio.to_thread(
            nullbr_service.fetch_tv_episode, sub.tmdb_id, sub.season_number, target_ep
        )
        
        # 筛选：仅 Magnet 和 Ed2k
        valid_res = [r for r in resources if r.link and r.link_type in ['magnet', 'ed2k']]

        if valid_res:
            # 排序：按文件大小降序
            valid_res.sort(key=lambda x: self._parse_size(x.size), reverse=True)
            target = valid_res[0]

            # 关键：使用预设的 save_cid 下载到对应文件夹
            success = await self._perform_download(target, to_cid=sub.save_cid)
            
            if success:
                sub.current_episode = target_ep
                sub.message = f"已添加第 {target_ep} 集 ({target.size})"
                sub.next_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                self._defer_check(sub, hours=4, msg=f"E{target_ep} 下载失败")
        else:
            self._defer_check(sub, hours=8, msg=f"第 {target_ep} 集暂无资源")

    def _defer_check(self, sub: Subscription, hours: int, msg: str):
        sub.message = msg
        sub.next_check_time = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    async def _perform_download(self, resource, to_cid: Optional[str] = None) -> bool:
        """执行离线下载"""
        try:
            # 再次确认只处理 magnet/ed2k
            if resource.link_type not in ['magnet', 'ed2k']:
                return False
                
            res = await asyncio.to_thread(
                p115_service.add_offline_tasks, [resource.link], to_cid=to_cid
            )
            return res.get('success', False)
        except Exception as e:
            print(f"Download failed: {e}")
            return False

subscription_service = SubscriptionService()