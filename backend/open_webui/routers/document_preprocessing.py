"""文档预处理转发路由。

本路由不自己跑解析，只做：鉴权（get_verified_user）+ 以内网 HTTP 代理的方式
把请求转发给独立的 meteokb-preprocess 微服务（DOC_PREPROCESS_SERVICE_URL），
并把 enrich（LLM 元数据抽取）配置从管理员配置注入到转发请求中。
"""

import logging
from typing import List

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from open_webui.utils.auth import get_verified_user

log = logging.getLogger(__name__)

router = APIRouter()

# 单文件/整体上传较大 + 解析耗时，转发超时放宽
UPLOAD_TIMEOUT = httpx.Timeout(60.0, read=300.0)
POLL_TIMEOUT = httpx.Timeout(30.0)
DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, read=600.0)

SERVICE_UNAVAILABLE_DETAIL = "预处理服务不可用，请联系管理员确认 meteokb 服务是否已启动。"


def _service_base_url(request: Request) -> str:
    url = (request.app.state.config.DOC_PREPROCESS_SERVICE_URL or "").rstrip("/")
    if not url:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    return url


@router.get("/health")
async def health(request: Request, user=Depends(get_verified_user)):
    """转发到 meteokb 服务的 /health，供管理员在设置页验证服务地址连通性。"""
    base_url = _service_base_url(request)
    try:
        async with httpx.AsyncClient(timeout=POLL_TIMEOUT) as client:
            resp = await client.get(f"{base_url}/health")
    except httpx.RequestError as e:
        log.error(f"预处理服务健康检查失败: {e}")
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code, detail=_extract_detail(resp)
        )
    return resp.json()


@router.post("/jobs")
async def create_job(
    request: Request,
    files: List[UploadFile] = File(...),
    user=Depends(get_verified_user),
):
    base_url = _service_base_url(request)
    config = request.app.state.config

    data = {
        "enrich_enabled": str(bool(config.DOC_PREPROCESS_ENRICH_ENABLED)).lower(),
        "enrich_base_url": config.DOC_PREPROCESS_ENRICH_BASE_URL or "",
        "enrich_api_key": config.DOC_PREPROCESS_ENRICH_API_KEY or "",
        "enrich_model": config.DOC_PREPROCESS_ENRICH_MODEL or "gpt-4o-mini",
        "enrich_default_region": config.DOC_PREPROCESS_ENRICH_DEFAULT_REGION or "",
        "owner": user.id,
    }

    multipart_files = []
    for upload in files:
        content = await upload.read()
        multipart_files.append(
            (
                "files",
                (upload.filename, content, upload.content_type or "application/octet-stream"),
            )
        )

    if not multipart_files:
        raise HTTPException(status_code=400, detail="未上传任何文件")

    try:
        async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
            resp = await client.post(
                f"{base_url}/jobs", data=data, files=multipart_files
            )
    except httpx.RequestError as e:
        log.error(f"转发上传到预处理服务失败: {e}")
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code, detail=_extract_detail(resp)
        )
    return resp.json()


@router.get("/jobs/{job_id}")
async def get_job(request: Request, job_id: str, user=Depends(get_verified_user)):
    base_url = _service_base_url(request)
    try:
        async with httpx.AsyncClient(timeout=POLL_TIMEOUT) as client:
            resp = await client.get(f"{base_url}/jobs/{job_id}")
    except httpx.RequestError as e:
        log.error(f"查询预处理任务失败: {e}")
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code, detail=_extract_detail(resp)
        )

    meta = resp.json()
    _assert_owner(meta, user)
    return meta


@router.delete("/jobs/{job_id}")
async def delete_job(request: Request, job_id: str, user=Depends(get_verified_user)):
    base_url = _service_base_url(request)
    try:
        async with httpx.AsyncClient(timeout=POLL_TIMEOUT) as client:
            meta_resp = await client.get(f"{base_url}/jobs/{job_id}")
            if meta_resp.status_code == 200:
                _assert_owner(meta_resp.json(), user)
            resp = await client.delete(f"{base_url}/jobs/{job_id}")
    except httpx.RequestError as e:
        log.error(f"删除预处理任务失败: {e}")
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code, detail=_extract_detail(resp)
        )
    return resp.json()


@router.get("/jobs/{job_id}/download")
async def download_job(
    request: Request, job_id: str, user=Depends(get_verified_user)
):
    base_url = _service_base_url(request)

    # 先校验归属
    try:
        async with httpx.AsyncClient(timeout=POLL_TIMEOUT) as client:
            meta_resp = await client.get(f"{base_url}/jobs/{job_id}")
    except httpx.RequestError as e:
        log.error(f"下载前查询任务失败: {e}")
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_DETAIL)
    if meta_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="任务不存在")
    if meta_resp.status_code == 200:
        _assert_owner(meta_resp.json(), user)

    async def _proxy_stream():
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
            async with client.stream(
                "GET", f"{base_url}/jobs/{job_id}/download"
            ) as upstream:
                if upstream.status_code >= 400:
                    raise HTTPException(
                        status_code=upstream.status_code,
                        detail="下载失败，任务可能尚未完成",
                    )
                async for chunk in upstream.aiter_bytes():
                    yield chunk

    headers = {
        "Content-Disposition": f'attachment; filename="preprocess-{job_id}.zip"'
    }
    return StreamingResponse(
        _proxy_stream(), media_type="application/zip", headers=headers
    )


def _assert_owner(meta: dict, user) -> None:
    """非 admin 只能访问自己的 job。"""
    if user.role == "admin":
        return
    owner = meta.get("owner")
    if owner is not None and owner != user.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")


def _extract_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
        if isinstance(payload, dict) and "detail" in payload:
            return payload["detail"]
    except Exception:
        pass
    return "预处理服务返回错误"
