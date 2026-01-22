import requests
import json
from app.core.config import settings

class StrmService:
    def __init__(self):
        pass

    def _get_api_url(self):
        if not settings.MOVIEPILOT_URL:
            return None
        base = settings.MOVIEPILOT_URL.rstrip('/')
        return f"{base}/api/v1/plugin/P115StrmHelper/api_strm_sync_create_by_path"

    def notify_gen_by_path(self, pan_path: str):
        """
        通知 MoviePilot 根据网盘路径生成 STRM
        """
        api_url = self._get_api_url()
        api_key = settings.MOVIEPILOT_APIKEY
        
        if not api_url or not api_key or not pan_path:
            # 如果没配置，则静默跳过
            return

        # 构造文档中要求的 payload
        # 只需要 pan_media_path，local_path 留空让插件自动匹配
        payload = {
            "data": [
                {
                    "pan_media_path": pan_path
                }
            ],
            # 设为 True 以便生成后立即刮削和刷新
            "scrape_metadata": True,
            "media_server_refresh": True
        }

        try:
            print(f"[STRM] Triggering generation for path: {pan_path}")
            resp = requests.post(
                api_url,
                params={"apikey": api_key},
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10 # 设置超时防止阻塞太久
            )
            
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("code") == 10200:
                    data = res_json.get("data", {})
                    print(f"[STRM] Success: Generated {data.get('success_count', 0)} files.")
                else:
                    print(f"[STRM] Plugin Error: {res_json.get('msg')}")
            else:
                print(f"[STRM] HTTP Error: {resp.status_code} - {resp.text}")

        except Exception as e:
            print(f"[STRM] Request Failed: {e}")

strm_service = StrmService()