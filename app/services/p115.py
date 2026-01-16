import os
from functools import lru_cache
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from p115client import P115Client
from p115client.util import share_extract_payload
from app.core.config import settings

class P115Service:
    def __init__(self):
        self._client: Optional[P115Client] = None

    @property
    def client(self) -> P115Client:
        """懒加载获取 P115Client 实例"""
        if self._client is None:
            if not settings.P115_COOKIE:
                raise ValueError("P115_COOKIE is not configured in environment variables.")
            # check_for_relogin=True 会在 cookie 失效时尝试报错
            self._client = P115Client(settings.P115_COOKIE, check_for_relogin=True)
        return self._client

    def get_target_cid(self, path_config: str, manual_cid: Optional[str] = None) -> int:
        """
        获取目标目录 CID。参考 p115strmhelper 的 get_pid_by_path 逻辑。
        1. 如果提供了 manual_cid，直接使用。
        2. 否则使用 path_config，先查询是否存在，不存在则创建。
        """
        if manual_cid:
            return int(manual_cid)
        
        path_str = path_config
        if not path_str or path_str == "/":
            return 0
            
        # 规范化路径，确保以 / 开头 (fs_dir_getid 需要)
        # 但 fs_makedirs_app 接受相对路径或绝对路径，这里统一处理
        path_obj = Path(path_str)
        path = path_obj.as_posix()
        if not path.startswith("/"):
            path = "/" + path

        # 1. 尝试直接获取 ID
        resp = self.client.fs_dir_getid(path)
        
        # 检查响应 (参考 plugins.v2/p115strmhelper/core/p115.py)
        pid = -1
        if resp.get("state"):
             pid = resp.get("id", -1)
             # 有些情况可能返回 data 结构
             if pid == -1 and "data" in resp:
                 data = resp["data"]
                 if isinstance(data, dict):
                     pid = data.get("id", -1)

        # 如果获取到了有效的非0 ID，直接返回
        if pid != -1:
            return int(pid)

        # 2. 如果不存在 (pid 为 -1 或 0)，则尝试创建
        # 注意：fs_makedirs_app 的 pid=0 表示在根目录下创建完整路径
        # 去除开头的 /，因为 fs_makedirs_app 习惯处理 "Downloads/Share" 这种形式
        create_path = path_str.strip("/")
        
        resp = self.client.fs_makedirs_app(create_path, pid=0)
        
        if not resp.get("state"):
             raise ValueError(f"Failed to create path '{create_path}': {resp.get('error')}")

        # 解析创建后的 CID
        cid = resp.get("cid")
        if cid is None and "data" in resp:
             # 兼容不同版本的返回
             data = resp["data"]
             if isinstance(data, dict):
                 cid = data.get("id") or data.get("file_id")
             elif isinstance(data, list) and len(data) > 0:
                 cid = data[-1].get("id")
        
        if cid is not None:
            return int(cid)

        raise ValueError(f"Failed to resolve CID for path '{path}'. Response: {resp}")

    def get_share_file_list(self, share_link: str, cid: str = "0", password: Optional[str] = None) -> Dict[str, Any]:
        """
        获取分享链接的文件列表。
        """
        payload = share_extract_payload(share_link)
        share_code = payload["share_code"]
        receive_code = password if password else payload.get("receive_code", "")

        resp = self.client.share_snap({
            "share_code": share_code,
            "receive_code": receive_code,
            "cid": cid,
            "limit": 1000
        })

        if not resp.get("state"):
            raise ValueError(f"Failed to list share files: {resp.get('error')}")

        data = resp.get("data", {})
        file_list = data.get("list", [])
        
        results = []
        for item in file_list:
            results.append({
                "id": str(item.get("fid")),
                "parent_id": str(item.get("cid")),
                "name": item.get("n"),
                "size": str(item.get("s")),
                "is_dir": bool(item.get("fo")), # fo=1 is folder
                "pick_code": item.get("pc"),
                "sha1": item.get("sha"),
            })
        
        return {
            "count": data.get("count"),
            "list": results,
            "share_info": data.get("share_info")
        }

    def save_share_files(self, share_link: str, file_ids: List[str], password: Optional[str] = None, to_cid: Optional[str] = None) -> Dict[str, Any]:
        """
        转存分享链接中的文件。参考 ShareTransferHelper.add_share_115
        """
        # 1. 获取目标 CID
        save_cid = self.get_target_cid(settings.P115_SAVE_PATH, to_cid)

        # 2. 解析分享信息
        payload_info = share_extract_payload(share_link)
        share_code = payload_info["share_code"]
        receive_code = password if password else payload_info.get("receive_code", "")

        # 3. 构造请求参数
        # 如果 file_ids 为空或者包含 "0"，通常意味着转存全部 (视业务逻辑而定，这里假设必须传入 file_ids)
        # 115 接口: file_id 为逗号分隔的字符串
        file_id_str = ",".join(file_ids) if file_ids else "0" 

        payload = {
            "share_code": share_code,
            "receive_code": receive_code,
            "file_id": file_id_str,
            "cid": save_cid,
            "is_check": 0, # 参考 reference 设为 0
        }

        # 4. 执行转存
        resp = self.client.share_receive(payload)

        if not resp.get("state"):
            return {"success": False, "message": resp.get("error"), "raw": resp}
        
        return {"success": True, "message": "Saved successfully", "raw": resp}

    def add_offline_tasks(self, urls: List[str], to_cid: Optional[str] = None) -> Dict[str, Any]:
        """
        添加离线下载任务。参考 OfflineDownloadHelper.build_offline_urls_payload
        """
        if not urls:
            return {"success": False, "message": "No URLs provided"}

        # 1. 获取目标 CID
        # 离线下载使用的是 wp_path_id
        save_cid = self.get_target_cid(settings.P115_DOWNLOAD_PATH, to_cid)

        # 2. 构造参数
        # 参考 reference: payload[f"url[{i}]"] = url.strip()
        # p115client.tool.offline.offline_add_urls 实际上封装了这个过程，
        # 如果直接用 client.offline_add_urls (底层 API 调用)，需要自己构造
        # 但 p115client 库通常提供了便捷方法。这里我们按照 reference 的逻辑手动构建 payload 传给 client
        
        payload = {
            "savepath": "", # 相对路径留空，直接使用 wp_path_id
            "wp_path_id": save_cid
        }
        
        # 115 API 接收 url[0]=xxx, url[1]=xxx
        for i, url in enumerate(urls):
            payload[f"url[{i}]"] = url.strip()

        # 3. 调用接口
        resp = self.client.offline_add_urls(payload)

        if not resp.get("state"):
             return {"success": False, "message": resp.get("error_msg") or resp.get("error"), "raw": resp}

        return {"success": True, "message": "Tasks added successfully", "raw": resp}

    def list_files(self, cid: str = "0", limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        列出个人网盘文件 (fs_files)。
        """
        resp = self.client.fs_files({
            "cid": cid,
            "limit": limit,
            "offset": offset,
            "show_dir": 1, # 同时显示目录
            "asc": 0,      # 降序
            "o": "user_ptime" # 按修改时间排序
        })

        if not resp.get("state"):
            raise ValueError(f"Failed to list files: {resp.get('error')}")

        # 解析数据结构
        # fs_files 的 data 字段有时是列表，有时包含 count/path/data 的字典
        raw_data = resp.get("data")
        file_list = []
        path_list = []
        count = 0
        
        if isinstance(raw_data, list):
            file_list = raw_data
            count = len(raw_data)
        elif isinstance(raw_data, dict):
            file_list = raw_data.get("data", [])
            path_list = raw_data.get("path", [])
            count = raw_data.get("count", 0)
        
        results = []
        for item in file_list:
            # 判断是否为目录：通常目录没有 'fid'，或者有 'cid' 作为它的ID
            # 115 API: 
            #   文件: { "fid": "...", "cid": "父目录ID", "n": "name" ... }
            #   目录: { "cid": "目录ID", "pid": "父目录ID", "n": "name" ... }
            
            is_dir = "fid" not in item
            
            # 提取 ID
            item_id = item.get("cid") if is_dir else item.get("fid")
            parent_id = item.get("pid") if is_dir else item.get("cid")
            
            results.append({
                "id": str(item_id),
                "parent_id": str(parent_id),
                "name": item.get("n", "Unknown"),
                "size": str(item.get("s", 0)),
                "is_dir": is_dir,
                "pick_code": item.get("pc", ""),
                "time": item.get("t", "") or item.get("upt", ""), # 修改时间
            })
            
        return {
            "count": count,
            "path": path_list, # 面包屑，前端可用于展示 "根目录 > 电影 > 2024"
            "list": results
        }
        
p115_service = P115Service()    