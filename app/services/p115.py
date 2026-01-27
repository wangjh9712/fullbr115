import os
from functools import lru_cache
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from p115client import P115Client
from p115client.util import share_extract_payload
from app.core.config import settings
from app.services.strm import strm_service

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
        获取目标目录 CID。
        """
        if manual_cid:
            return int(manual_cid)
        
        path_str = path_config
        # 如果配置明确是根目录，直接返回 0
        if not path_str or path_str == "/" or path_str == "\\":
            return 0
            
        # 规范化路径
        path_obj = Path(path_str)
        path = path_obj.as_posix()
        if not path.startswith("/"):
            path = "/" + path

        # 1. 尝试直接获取 ID
        resp = self.client.fs_dir_getid(path)
        
        pid = -1
        if resp.get("state"):
             # 尝试提取 ID 并转换为 int
             try:
                 val = resp.get("id")
                 if val is None and "data" in resp:
                     data = resp["data"]
                     if isinstance(data, dict):
                         val = data.get("id")
                 
                 # 确保转换为整数
                 if val is not None:
                     pid = int(val)
             except (ValueError, TypeError):
                 pid = -1

        # 如果 pid == 0，说明 api 可能返回了根目录，但我们明确请求的是子目录
        if pid > 0:
            return pid

        # 2. 如果不存在，则尝试创建
        # 注意：fs_makedirs_app 的 pid=0 表示在根目录下创建
        create_path = path_str.strip("/")
        if not create_path: # 防止为空字符串
            return 0
            
        resp = self.client.fs_makedirs_app(create_path, pid=0)
        
        if not resp.get("state"):
             raise ValueError(f"Failed to create path '{create_path}': {resp.get('error')}")

        # 解析创建后的 CID
        cid = None
        # 尝试提取 CID 并转换为 int
        try:
            cid_val = resp.get("cid")
            if cid_val is None and "data" in resp:
                 data = resp["data"]
                 if isinstance(data, dict):
                     cid_val = data.get("id") or data.get("file_id")
                 elif isinstance(data, list) and len(data) > 0:
                     cid_val = data[-1].get("id")
            
            if cid_val is not None:
                cid = int(cid_val)
        except (ValueError, TypeError):
            pass
        
        if cid is not None:
            return cid

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
            # 解析 115 Share 列表项
            # 文件夹: 通常没有 fid, cid 为文件夹ID, pid 为父ID, fo=1
            # 文件: fid 为文件ID, cid 为父ID, fo=0 或不存在
            
            fid = item.get("fid")
            cid_val = item.get("cid")
            pid_val = item.get("pid")
            name = item.get("n", "")
            
            # 逻辑修正：
            # 1. 如果文件名以 .iso 结尾，强制视为文件 (is_dir=False)
            # 2. 否则，如果 fo=1 或没有 fid，视为目录
            
            is_iso = name.lower().endswith('.iso')
            
            if is_iso:
                is_dir = False
            else:
                is_dir = (item.get("fo") == 1) or (not fid)

            # ID 分配逻辑
            if is_dir:
                item_id = cid_val
                parent_id = pid_val
            else:
                item_id = fid
                parent_id = cid_val

            results.append({
                "id": str(item_id),
                "parent_id": str(parent_id),
                "name": name,
                "size": str(item.get("s")),
                "is_dir": is_dir,
                "pick_code": item.get("pc"),
                "sha1": item.get("sha"),
            })
        
        return {
            "count": data.get("count"),
            "list": results,
            "share_info": data.get("share_info")
        }

    def save_share_files(self, share_link: str, file_ids: List[str], password: Optional[str] = None, to_cid: Optional[str] = None, save_path_str: Optional[str] = None, new_directory_name: Optional[str] = None) -> Dict[str, Any]:
        """
        转存文件。
        :param save_path_str: 明确的目标路径字符串（用于 STRM 生成通知）。如果未提供且 to_cid 为空，则使用默认配置路径。
        """
        save_cid = self.get_target_cid(settings.P115_SAVE_PATH, to_cid)
        notify_path = save_path_str if save_path_str else settings.P115_SAVE_PATH
        payload_info = share_extract_payload(share_link)
        share_code = payload_info["share_code"]
        receive_code = password if password else payload_info.get("receive_code", "")

        file_id_str = ",".join(file_ids) if file_ids else "0" 

        if new_directory_name:
            try:
                # 在当前 save_cid 下创建新文件夹
                resp = self.client.fs_makedirs_app(new_directory_name, pid=save_cid)
                if not resp.get("state"):
                     raise ValueError(f"Failed to create subdir '{new_directory_name}': {resp.get('error')}")
                
                # 增强 CID 提取逻辑，防止漏掉 ID 导致存错位置
                new_cid = None
                
                # 1. 优先尝试从根层级获取 (部分 115 接口会直接在根级返回 cid 或 file_id)
                new_cid = resp.get("cid") or resp.get("file_id")

                # 2. 如果根层级没有，再尝试从 data 字段获取
                if new_cid is None and "data" in resp:
                    data = resp.get("data")
                    if isinstance(data, dict):
                        new_cid = data.get("id") or data.get("file_id") or data.get("cid")
                    elif isinstance(data, list) and data:
                        # fs_makedirs_app 如果递归创建，可能返回列表，通常最后一个是目标文件夹
                        last_item = data[-1]
                        new_cid = last_item.get("id") or last_item.get("file_id") or last_item.get("cid")
                
                if new_cid:
                    save_cid = int(new_cid) # 更新目标 CID 为新建的文件夹
                    # 更新通知路径 (辅助功能)
                    if notify_path:
                        notify_path = os.path.join(notify_path, new_directory_name)
                else:
                    # 如果创建成功但无法获取 ID，打印警告，文件将被存入父目录
                    print(f"Warning: Created folder '{new_directory_name}' but failed to extract CID. Response: {resp}")

            except Exception as e:
                return {"success": False, "message": f"创建整理文件夹失败: {str(e)}", "raw": {}}

        payload = {
            "share_code": share_code,
            "receive_code": receive_code,
            "file_id": file_id_str,
            "cid": save_cid,
            "is_check": 0,
        }

        resp = self.client.share_receive(payload)
        
        if not resp.get("state"):
            return {"success": False, "message": resp.get("error"), "raw": resp}
        
        return {"success": True, "message": "Saved successfully", "raw": resp}

    def add_offline_tasks(self, urls: List[str], to_cid: Optional[str] = None, save_path_str: Optional[str] = None) -> Dict[str, Any]:
        """
        离线下载。
        :param save_path_str: 明确的目标路径字符串（用于 STRM 生成通知）。
        """
        if not urls:
            return {"success": False, "message": "No URLs provided"}

        save_cid = self.get_target_cid(settings.P115_DOWNLOAD_PATH, to_cid)

        payload = {
            "savepath": "", 
            "wp_path_id": save_cid
        }
        
        for i, url in enumerate(urls):
            payload[f"url[{i}]"] = url.strip()

        resp = self.client.offline_add_urls(payload)

        if not resp.get("state"):
             return {"success": False, "message": resp.get("error_msg") or resp.get("error"), "raw": resp}

        # 注意：离线任务是异步的，文件此时可能并未下载完成。
        # 但 P115StrmHelper 的 api_strm_sync_create_by_path 是扫描目录。
        # 如果下载很快（如秒传），现在扫描是有效的。
        # 如果下载很慢，可能需要后续再次扫描。
        try:
            notify_path = save_path_str if save_path_str else settings.P115_DOWNLOAD_PATH
            if notify_path:
                strm_service.notify_gen_by_path(notify_path)
        except Exception as e:
             print(f"Failed to trigger STRM gen: {e}")

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