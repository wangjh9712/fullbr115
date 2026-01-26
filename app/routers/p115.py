from fastapi import APIRouter, HTTPException, Body
from app.models.schemas import (
    P115ShareListRequest, P115ShareSaveRequest, P115OfflineAddRequest, 
    P115FileListRequest, P115Response, P115ShareFile
)
from app.services.p115 import p115_service
from typing import List

router = APIRouter(prefix="/p115", tags=["115"])

@router.post("/share/list", response_model=P115Response)
async def list_share_files(request: P115ShareListRequest):
    """
    获取分享链接的文件列表。
    """
    try:
        result = p115_service.get_share_file_list(
            share_link=request.share_link,
            cid=request.cid,
            password=request.password
        )
        return P115Response(state=True, data=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/share/save", response_model=P115Response)
async def save_share_files(request: P115ShareSaveRequest):
    """
    转存分享链接中的选定文件。
    如果不指定 to_cid，将尝试保存到 env 配置的 P115_SAVE_PATH (并自动创建)。
    """
    try:
        result = p115_service.save_share_files(
            share_link=request.share_link,
            file_ids=request.file_ids,
            password=request.password,
            to_cid=request.to_cid, # 传递 manual CID
            new_directory_name=request.new_directory_name
        )
        if not result["success"]:
            return P115Response(state=False, message=result["message"], data=result.get("raw"))
        return P115Response(state=True, message="转存任务提交成功", data=result.get("raw"))
    except Exception as e:
        # 这里会捕获 ValueError 并返回给客户端，方便调试
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/offline/add", response_model=P115Response)
async def add_offline_tasks(request: P115OfflineAddRequest):
    """
    添加离线下载任务 (Magnet, HTTP, FTP, ED2K)。
    如果不指定 to_cid，将尝试保存到 env 配置的 P115_DOWNLOAD_PATH (并自动创建)。
    """
    try:
        result = p115_service.add_offline_tasks(request.urls, to_cid=request.to_cid)
        if not result["success"]:
             return P115Response(state=False, message=result["message"], data=result.get("raw"))
        return P115Response(state=True, message="离线任务添加成功", data=result.get("raw"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/files/list", response_model=P115Response)
async def list_user_files(request: P115FileListRequest):
    """
    浏览 Cookie 账号下的文件目录。
    返回数据中包含 'path' 字段，显示当前路径结构，方便获取 CID。
    """
    try:
        result = p115_service.list_files(
            cid=request.cid,
            limit=request.limit,
            offset=request.offset
        )
        return P115Response(state=True, data=result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))