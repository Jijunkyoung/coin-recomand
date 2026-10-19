"""Publish the already-built Pages artifact to the owner's Cloudflare account.

Credentials stay in GitHub Actions. Only public dashboard files are deployed;
account APIs and their owner authorization remain on the existing backend.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_PROJECT = "coin-recomand-jijunkyoung"
SUPABASE_REF = "pgtxtnggjqaysjhtdepz"
REQUIRED_FILES = (
    "index.html", "us-stocks.html", "kr-stocks.html", "research.html",
    "data/latest.json", "data/stocks-us.json", "data/stocks-kr.json",
    "supabase-runtime-config.js",
)


def settings(env: dict[str, str]) -> dict[str, str] | None:
    account = env.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = env.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account and not token:
        return None
    if not account or not token:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID와 CLOUDFLARE_API_TOKEN을 둘 다 Repository secret에 등록해 주세요.")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account):
        raise ValueError("CLOUDFLARE_ACCOUNT_ID에는 32자리 Account ID를 입력해 주세요.")
    project = env.get("CLOUDFLARE_PAGES_PROJECT", "").strip() or DEFAULT_PROJECT
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?", project):
        raise ValueError("CLOUDFLARE_PAGES_PROJECT는 소문자·숫자·하이픈으로 된 58자 이내 프로젝트명이어야 합니다.")
    return {"account": account, "token": token, "project": project}


def output(env: dict[str, str], **values: str) -> None:
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")


def request_json(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    request = Request(url, data=None if payload is None else json.dumps(payload).encode(),
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError:
        # Keep HTTP status available to the caller; never include response bodies or credentials in logs.
        raise
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("배포 설정 서버에 연결하지 못했습니다. 잠시 후 다시 실행해 주세요.") from exc


def ensure_project(config: dict[str, str]) -> str:
    base = f"https://api.cloudflare.com/client/v4/accounts/{config['account']}/pages/projects"
    try:
        result = request_json(f"{base}/{config['project']}", config["token"])
    except HTTPError as exc:
        if exc.code != 404:
            raise RuntimeError(f"Cloudflare 프로젝트 조회 실패 (HTTP {exc.code}). 토큰의 Account / Cloudflare Pages / Edit 권한과 계정 범위를 확인해 주세요.") from exc
        try:
            result = request_json(base, config["token"], "POST", {"name": config["project"], "production_branch": "main"})
        except HTTPError as create_error:
            raise RuntimeError(f"Cloudflare 프로젝트 생성 실패 (HTTP {create_error.code}). 권한을 확인하고, 프로젝트명이 사용 중이면 CLOUDFLARE_PAGES_PROJECT 저장소 변수를 다른 이름으로 설정해 주세요.") from create_error
    project = result.get("result") or {}
    if result.get("success") is not True or project.get("name") != config["project"] or project.get("subdomain") != f"{config['project']}.pages.dev":
        raise RuntimeError("Cloudflare가 예상한 프로젝트 주소를 확인해 주지 않았습니다.")
    if project.get("production_branch") != "main":
        raise RuntimeError("Cloudflare 프로젝트의 production branch를 main으로 설정해 주세요.")
    source = project.get("source") or {}
    if source.get("type") in {"github", "gitlab"} and source.get("config", {}).get("production_deployments_enabled") is not False:
        raise RuntimeError("이 프로젝트의 Cloudflare Git 자동 배포를 먼저 꺼주세요. 분석자료가 없는 저장소 원본이 최신 결과물을 덮어쓰지 않도록 GitHub Actions 배포만 사용합니다.")
    return f"https://{project['subdomain']}"


def allow_login_redirects(site_url: str, token: str) -> None:
    url = f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/config/auth"
    if not re.fullmatch(r"https://[a-z0-9-]+\.pages\.dev", site_url):
        raise ValueError("로그인 복귀 주소는 확인된 Cloudflare Pages 프로젝트 주소여야 합니다.")
    # Exact production paths only, including Pages' extensionless HTML redirects.
    paths = ("", "/", "/index.html", "/index", "/us-stocks.html", "/us-stocks", "/kr-stocks.html", "/kr-stocks", "/research.html", "/research")
    try:
        current = request_json(url, token)
        raw = current.get("uri_allow_list") or ""
        if not isinstance(raw, str):
            raise RuntimeError("기존 로그인 복귀 주소의 형식을 확인하지 못했습니다.")
        allowed = list(dict.fromkeys(value.strip() for value in raw.split(",") if value.strip()))
        merged = list(dict.fromkeys([*allowed, *(site_url + path for path in paths)]))
        if merged != allowed:
            result = request_json(url, token, "PATCH", {"uri_allow_list": ",".join(merged)})
            confirmed = {value.strip() for value in str(result.get("uri_allow_list") or "").split(",")}
            if not set(merged).issubset(confirmed):
                raise RuntimeError("새 주소의 로그인 복귀 설정이 확인되지 않았습니다.")
    except HTTPError as exc:
        raise RuntimeError(f"Cloudflare 로그인 복귀 주소 등록 실패 (HTTP {exc.code}). SUPABASE_ACCESS_TOKEN을 확인해 주세요.") from exc


def validate_site(site: Path) -> None:
    for name in REQUIRED_FILES:
        if not (site / name).is_file():
            raise ValueError(f"분석 결과물에 {name} 파일이 없습니다. 저장소 원본 대신 같은 실행의 github-pages artifact를 사용해야 합니다.")
    for name in ("data/latest.json", "data/stocks-us.json", "data/stocks-kr.json"):
        data = json.loads((site / name).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data:
            raise ValueError(f"분석 결과 파일이 올바르지 않습니다: {name}")
    text = (site / "supabase-runtime-config.js").read_text(encoding="utf-8")
    match = re.search(r"Object\.freeze\((\{.*\})\);", text, re.S)
    config = json.loads(match.group(1)) if match else {}
    if not isinstance(config, dict):
        raise ValueError("공개 로그인 설정의 형식이 올바르지 않습니다.")
    key = str(config.get("anonKey") or "")
    public = key.startswith("sb_publishable_")
    if not public:
        try:
            payload = key.split(".")[1]
            role = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("role")
            public = role == "anon"
        except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            public = False
    if config.get("url") != f"https://{SUPABASE_REF}.supabase.co" or not public:
        raise ValueError("로그인 설정에는 기존 프로젝트의 공개 publishable/anon 키만 사용할 수 있습니다.")


def unpack(archive: Path, site: Path) -> None:
    site.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        if len(members) > 20000 or sum(member.size for member in members) > 250 * 1024 * 1024:
            raise ValueError("정적 사이트 배포 크기 제한을 초과했습니다.")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError("배포 파일에는 상위 경로나 링크를 포함할 수 없습니다.")
            if member.size > 25 * 1024 * 1024:
                raise ValueError("Cloudflare Pages의 단일 파일 25 MiB 제한을 초과했습니다.")
        bundle.extractall(site, filter="data")
    validate_site(site)


def verify(site: Path, site_url: str) -> None:
    # Check generated public files byte-for-byte; never fetch private account APIs.
    files = ("index.html", "us-stocks.html", "data/latest.json", "data/stocks-us.json", "data/stocks-kr.json", "supabase-runtime-config.js")
    for attempt in range(6):
        try:
            for name in files:
                request = Request(f"{site_url}/{name}?deployment_check={time.time_ns()}", headers={"Cache-Control": "no-cache"})
                with urlopen(request, timeout=15) as response:
                    if hashlib.sha256(response.read()).digest() != hashlib.sha256((site / name).read_bytes()).digest():
                        raise ValueError("게시된 분석자료가 이번 배포 결과물과 다릅니다.")
            return
        except (URLError, TimeoutError, ValueError):
            if attempt == 5:
                raise RuntimeError("Cloudflare 게시 확인에 실패했습니다. 다음 실행에서 다시 동기화됩니다.") from None
            time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "unpack", "prepare", "verify"))
    args = parser.parse_args()
    env = dict(os.environ)
    config = settings(env)
    if args.action == "check":
        output(env, enabled="true" if config else "false", project=config["project"] if config else "")
        print("Cloudflare 배포 설정 확인 완료." if config else "Cloudflare 인증값 미등록: 기존 GitHub 배포를 유지합니다.")
        if not config and env.get("GITHUB_STEP_SUMMARY"):
            with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
                stream.write("Cloudflare 동기화 대기: Repository secrets에 `CLOUDFLARE_ACCOUNT_ID`와 `CLOUDFLARE_API_TOKEN`을 등록한 뒤 다시 실행하세요.\n")
        return
    if not config:
        raise ValueError("먼저 Cloudflare 인증값 두 개를 등록해 주세요.")
    site = Path("cloudflare-site")
    if args.action == "unpack":
        unpack(Path("cloudflare-artifact/artifact.tar"), site)
        print("이번 실행의 최신 분석자료와 공개 로그인 설정 파일을 확인했습니다.")
    elif args.action == "prepare":
        site_url = ensure_project(config)
        token = env.get("SUPABASE_ACCESS_TOKEN", "").strip()
        if not token:
            raise ValueError("로그인 복귀 주소 등록에 필요한 기존 SUPABASE_ACCESS_TOKEN이 없습니다.")
        allow_login_redirects(site_url, token)
        print("Cloudflare 프로젝트와 로그인 복귀 주소 준비 완료. 기존 로그인 설정과 계좌 권한은 유지됩니다.")
    else:
        site_url = f"https://{config['project']}.pages.dev"
        verify(site, site_url)
        if env.get("GITHUB_STEP_SUMMARY"):
            with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
                stream.write(f"## Cloudflare 대시보드 동기화 완료\n\n[대시보드 열기]({site_url})\n\n[미국주식]({site_url}/us-stocks.html) · [국내주식]({site_url}/kr-stocks.html)\n\n이번 실행에서 생성한 분석자료와 공개 로그인 설정의 일치를 확인했습니다.\n")
        print(f"Cloudflare 대시보드 동기화 확인 완료: {site_url}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, tarfile.TarError) as error:
        # Error messages above contain configuration names/statuses, never credential values.
        raise SystemExit(str(error)) from None
