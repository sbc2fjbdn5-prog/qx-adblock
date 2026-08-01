#!/usr/bin/env python3
"""Snapshot curated Quantumult X ad-block modules and their dependencies."""

from __future__ import annotations

import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlparse


SOURCE_CATALOG = "sources.json"
OWNER = "sbc2fjbdn5-prog"
REPOSITORY = "qx-adblock"
RAW_BASE = (
    f"https://raw.githubusercontent.com/{OWNER}/{REPOSITORY}/"
    "refs/heads/main/"
)
ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "modules"
DEPENDENCY_DIR = ROOT / "dependencies"
MAX_WORKERS = 6

URL_RE = re.compile(rb"https?://[^\s\"'<>,]+", re.I)
CODE_EXTENSIONS = {
    ".js",
    ".json",
    ".conf",
    ".txt",
    ".list",
    ".module",
    ".sgmodule",
    ".plugin",
    ".lpx",
    ".stoverride",
}
RECURSIVE_EXTENSIONS = CODE_EXTENSIONS - {".js"}
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
}
CODE_HOSTS = {
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "cdn.jsdelivr.net",
    "gitlab.com",
    "raw.gitmirror.com",
}

# Some source URLs referenced by the page now return 404. These commit-pinned
# public copies preserve the same scripts so the mirror can still be complete.
RECOVERY_SOURCES = {
    "https://raw.githubusercontent.com/DivineEngine/Profiles/master/Surge/Rewrite/bstar.js":
        "https://raw.githubusercontent.com/Vikingama/plugins/3eb43876fa886ab61d202061b4901afd9509f42b/script/divine.engine.bstar.js",
    "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/script/smzdm/smzdm_remove_ads.js":
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/script/archive/smzdm/smzdm_remove_ads.js",
    "https://github.com/ddgksf2013/MoYu/raw/master/CaiXinZhouKanProCrack.js":
        "https://raw.githubusercontent.com/x1Kat/K/15b4e65dee15351aed08865664cfd804a2e7beea/Script/caixinzhoukanpro.js",
    "https://raw.githubusercontent.com/NobyDa/Script/master/QuantumultX/File/aimeiju.js":
        "https://raw.githubusercontent.com/NobyDa/Script/730362a7c51e9a3b4bbc10858d81ccd086f6d7e8/QuantumultX/File/aimeiju.js",
    "https://raw.githubusercontent.com/WeiRen0/Scripts/main/cytq.js":
        "https://raw.githubusercontent.com/ly661/WeiRen0-Scripts/150f4514950bc2f3a7b13a3a85b9fd4e9117ae3f/cytq.js",
    "https://raw.githubusercontent.com/WeiRen0/Scripts/main/wyun.js":
        "https://raw.githubusercontent.com/ly661/WeiRen0-Scripts/150f4514950bc2f3a7b13a3a85b9fd4e9117ae3f/wyun.js",
    "https://raw.githubusercontent.com/ddgksf2013/Cuttlefish/master/Script/bilibili_cc.js":
        "https://raw.githubusercontent.com/a1758446/github_ddgksf2013_Cuttlefish/8caf8167dd2636916fd0babd3e0c792a4d277242/Script/bilibili_cc.js",
    "https://raw.githubusercontent.com/iEwha/Profiles/master/Script/baimiao.js":
        "https://raw.githubusercontent.com/iEwha/Profiles/be6af858224a1e014e4bf86e839881fbceae24dd/Script/baimiao.js",
    "https://raw.githubusercontent.com/lutqhysky/quantumultx/mylove/xiaoxiaoyouqu/Script/xxyq.js":
        "https://raw.githubusercontent.com/lutqhysky/quantumultx/9412f53e4052df10886aee37aff27075e1358874/xiaoxiaoyouqu/Script/xxyq.js",
}


@dataclasses.dataclass
class FetchResult:
    url: str
    ok: bool
    content: bytes = b""
    error: str = ""
    recovery_url: str = ""


def curl_fetch_once(url: str) -> FetchResult:
    command = [
        "curl",
        "-fL",
        "--silent",
        "--show-error",
        "--compressed",
        "--connect-timeout",
        "15",
        "--max-time",
        "75",
        "--retry",
        "2",
        "--retry-delay",
        "1",
        "--retry-all-errors",
        "-A",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36",
        url,
    ]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode == 0:
        return FetchResult(url=url, ok=True, content=completed.stdout)
    error = completed.stderr.decode("utf-8", "replace").strip()
    return FetchResult(url=url, ok=False, error=error or f"curl exit {completed.returncode}")


def curl_fetch(url: str) -> FetchResult:
    result = curl_fetch_once(url)
    if result.ok or url not in RECOVERY_SOURCES:
        return result
    recovery_url = RECOVERY_SOURCES[url]
    recovered = curl_fetch_once(recovery_url)
    if recovered.ok:
        return FetchResult(
            url=url,
            ok=True,
            content=recovered.content,
            recovery_url=recovery_url,
        )
    return FetchResult(
        url=url,
        ok=False,
        error=f"primary: {result.error}\nrecovery: {recovered.error}",
        recovery_url=recovery_url,
    )


def fetch_many(urls: list[str]) -> dict[str, FetchResult]:
    results: dict[str, FetchResult] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(curl_fetch, url): url for url in urls}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results[result.url] = result
    return results


def load_sources() -> list[dict[str, str]]:
    path = ROOT / SOURCE_CATALOG
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{SOURCE_CATALOG} must contain a JSON array")
    required = {"title", "source_url", "local_path", "group"}
    for index, item in enumerate(data):
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(f"invalid source entry at index {index}")
    return data


def safe_segment(segment: str) -> str:
    decoded = unquote(segment)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", decoded).strip("._")
    return safe or "_"


def dependency_path(url: str, occupied: dict[str, str]) -> str:
    parsed = urlparse(url)
    host = safe_segment(parsed.netloc.lower().replace(":", "_"))
    raw_segments = [s for s in parsed.path.split("/") if s]
    segments = [safe_segment(s) for s in raw_segments] or ["index"]
    candidate = str(PurePosixPath("dependencies", host, *segments))
    if parsed.query:
        path = PurePosixPath(candidate)
        suffix = path.suffix
        stem = path.name[: -len(suffix)] if suffix else path.name
        name = f"{stem}--{hashlib.sha256(url.encode()).hexdigest()[:10]}{suffix}"
        candidate = str(path.with_name(name))
    # macOS commonly uses a case-insensitive filesystem, so compare paths by
    # case-folded keys. This keeps distinct upstream files such as KP.js and
    # kp.js from overwriting one another locally.
    key = candidate.casefold()
    previous = occupied.get(key)
    if previous is not None and previous != url:
        path = PurePosixPath(candidate)
        suffix = path.suffix
        stem = path.name[: -len(suffix)] if suffix else path.name
        name = f"{stem}--{hashlib.sha256(url.encode()).hexdigest()[:10]}{suffix}"
        candidate = str(path.with_name(name))
        key = candidate.casefold()
    occupied[key] = url
    return candidate


def trim_url(raw: bytes) -> bytes:
    while raw and raw[-1:] in b",;)]}:\"":
        raw = raw[:-1]
    return raw


def should_mirror(url: str, line: bytes, start: int) -> bool:
    if url.startswith(RAW_BASE):
        return False
    parsed = urlparse(url)
    suffix = PurePosixPath(parsed.path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return False
    # Rewrite match patterns can themselves end in `.js` (for example a
    # blocked advertising asset). Mirror only URLs used as script/task
    # targets, not the URL being matched by a reject rule.
    if "*" in url:
        return False
    lower = line.lower()
    markers = [lower.find(token) for token in (b"script-", b"script-path", b"script_path")]
    markers = [pos for pos in markers if pos >= 0]
    if markers and start > min(markers):
        return True
    if b"tag=" in lower and (b"cron" in lower or re.match(rb"\s*[0-9*/?, -]+\s+https?://", line)):
        return True
    return False


def extract_dependencies(content: bytes) -> list[str]:
    if b"\x00" in content:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith((b"#", b"//", b"/*", b";")):
            continue
        for match in URL_RE.finditer(line):
            raw = trim_url(match.group(0))
            try:
                url = raw.decode("ascii")
            except UnicodeDecodeError:
                continue
            if url not in seen and should_mirror(url, line, match.start()):
                seen.add(url)
                found.append(url)
    return found


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def raw_url(local_path: str) -> str:
    return RAW_BASE + quote(local_path, safe="/-._~")


def write_bytes(local_path: str, content: bytes) -> None:
    path = ROOT / local_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def remove_stale_files(directory: Path, keep: set[str]) -> None:
    if not directory.exists():
        return
    for path in directory.rglob("*"):
        if path.is_file() and path.relative_to(ROOT).as_posix() not in keep:
            path.unlink()
    for path in sorted(directory.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    MODULE_DIR.mkdir(parents=True, exist_ok=True)
    DEPENDENCY_DIR.mkdir(parents=True, exist_ok=True)

    initial_items = load_sources()
    print(f"Discovered {len(initial_items)} ad-block modules")
    if not initial_items:
        print("No module sources found", file=sys.stderr)
        return 1

    url_to_path: dict[str, str] = {}
    occupied: dict[str, str] = {}
    title_by_url: dict[str, str] = {}
    for item in initial_items:
        url = item["source_url"]
        local_path = item["local_path"]
        url_to_path[url] = local_path
        occupied[local_path.casefold()] = url
        title_by_url[url] = item["title"]

    initial_results: dict[str, FetchResult] = {}
    remote_urls: list[str] = []
    for item in initial_items:
        url = item["source_url"]
        local_source_path = item.get("local_source_path")
        if local_source_path:
            source_path = ROOT / local_source_path
            try:
                initial_results[url] = FetchResult(
                    url=url,
                    ok=True,
                    content=source_path.read_bytes(),
                )
            except OSError as error:
                initial_results[url] = FetchResult(
                    url=url,
                    ok=False,
                    error=f"local source: {error}",
                )
        else:
            remote_urls.append(url)
    initial_results.update(fetch_many(remote_urls))
    successful_content: dict[str, bytes] = {}
    failures: dict[str, str] = {}
    recovered_from: dict[str, str] = {}
    for url, result in initial_results.items():
        if result.ok:
            successful_content[url] = result.content
            write_bytes(url_to_path[url], result.content)
            if result.recovery_url:
                recovered_from[url] = result.recovery_url
        else:
            failures[url] = result.error
    print(f"Downloaded {len(successful_content)}/{len(initial_items)} modules")

    references: dict[str, set[str]] = defaultdict(set)
    scan_queue: deque[str] = deque(successful_content)
    scanned: set[str] = set()

    while scan_queue:
        newly_discovered: list[str] = []
        while scan_queue:
            parent_url = scan_queue.popleft()
            if parent_url in scanned:
                continue
            scanned.add(parent_url)
            content = successful_content[parent_url]
            for dependency_url in extract_dependencies(content):
                references[dependency_url].add(parent_url)
                if dependency_url in url_to_path:
                    continue
                url_to_path[dependency_url] = dependency_path(dependency_url, occupied)
                newly_discovered.append(dependency_url)
        if not newly_discovered:
            break
        print(f"Downloading {len(newly_discovered)} newly discovered dependencies")
        dependency_results = fetch_many(newly_discovered)
        for url, result in dependency_results.items():
            if not result.ok:
                failures[url] = result.error
                continue
            successful_content[url] = result.content
            write_bytes(url_to_path[url], result.content)
            if result.recovery_url:
                recovered_from[url] = result.recovery_url
            suffix = PurePosixPath(urlparse(url).path).suffix.lower()
            if suffix in RECURSIVE_EXTENSIONS and b"\x00" not in result.content:
                scan_queue.append(url)

    replacements_by_parent: dict[str, list[dict[str, str]]] = defaultdict(list)
    for parent_url in scanned:
        content = successful_content[parent_url]
        rewritten = content
        for dependency_url in extract_dependencies(content):
            if dependency_url not in successful_content:
                continue
            mirror = raw_url(url_to_path[dependency_url])
            source_bytes = dependency_url.encode("ascii")
            if source_bytes not in rewritten:
                continue
            rewritten = rewritten.replace(source_bytes, mirror.encode("ascii"))
            replacements_by_parent[parent_url].append(
                {
                    "source_url": dependency_url,
                    "mirror_url": mirror,
                    "local_path": url_to_path[dependency_url],
                }
            )
        successful_content[parent_url] = rewritten
        write_bytes(url_to_path[parent_url], rewritten)

    initial_manifest: list[dict[str, object]] = []
    for item in initial_items:
        url = item["source_url"]
        content = successful_content.get(url)
        initial_manifest.append(
            {
                "title": item["title"],
                "source_url": url,
                "upstream_url": item.get("upstream_url", url),
                "group": item["group"],
                "local_path": url_to_path[url],
                "mirror_url": raw_url(url_to_path[url]),
                "status": "ok" if content is not None else "failed",
                "recovery_source_url": recovered_from.get(url),
                "sha256": sha256(content) if content is not None else None,
                "dependency_replacements": replacements_by_parent.get(url, []),
                "error": failures.get(url),
            }
        )

    dependency_manifest: list[dict[str, object]] = []
    initial_urls = {item["source_url"] for item in initial_items}
    for url in sorted(set(url_to_path) - initial_urls):
        content = successful_content.get(url)
        dependency_manifest.append(
            {
                "source_url": url,
                "local_path": url_to_path[url],
                "mirror_url": raw_url(url_to_path[url]),
                "status": (
                    "recovered" if url in recovered_from else "ok"
                ) if content is not None else "failed",
                "recovery_source_url": recovered_from.get(url),
                "sha256": sha256(content) if content is not None else None,
                "referenced_by": sorted(references.get(url, set())),
                "dependency_replacements": replacements_by_parent.get(url, []),
                "error": failures.get(url),
            }
        )

    remove_stale_files(MODULE_DIR, {str(item["local_path"]) for item in initial_manifest})
    remove_stale_files(
        DEPENDENCY_DIR,
        {str(item["local_path"]) for item in dependency_manifest},
    )

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest = {
        "generated_at": generated_at,
        "source_catalog": SOURCE_CATALOG,
        "destination_repository": f"https://github.com/{OWNER}/{REPOSITORY}",
        "raw_base": RAW_BASE,
        "summary": {
            "discovered_modules": len(initial_items),
            "downloaded_modules": sum(1 for item in initial_manifest if item["status"] == "ok"),
            "discovered_dependencies": len(dependency_manifest),
            "downloaded_dependencies": sum(
                1 for item in dependency_manifest if item["status"] in {"ok", "recovered"}
            ),
            "failed_downloads": len(failures),
            "rewritten_dependency_references": sum(
                len(items) for items in replacements_by_parent.values()
            ),
        },
        "modules": initial_manifest,
        "dependencies": dependency_manifest,
        "failures": [{"url": url, "error": error} for url, error in sorted(failures.items())],
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    index_lines = [
        "# Quantumult X 去广告模块索引",
        "",
        "收录来源：yfamilys、ddgksf2013、app2smile、blackmatrix7、Adblock4limbo、zirawell 及自制模块",
        "",
        f"生成时间：`{generated_at}`",
        "",
        "| 名称 | 镜像文件 | 原始地址 |",
        "|---|---|---|",
    ]
    for item in initial_manifest:
        title = str(item["title"]).replace("|", "\\|")
        mirror_link = f"[Raw]({item['mirror_url']})" if item["status"] == "ok" else "下载失败"
        index_lines.append(f"| {title} | {mirror_link} | [来源]({item['upstream_url']}) |")
    (ROOT / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    summary = manifest["summary"]
    readme = f"""# qx-adblock

Quantumult X 去广告模块专用镜像。模块及其脚本依赖均保存到本仓库，并将运行时依赖引用改写为本仓库 Raw 地址。

## 快照统计

- 去广告模块：**{summary['downloaded_modules']} / {summary['discovered_modules']}**
- 已发现脚本依赖：**{summary['discovered_dependencies']}**
- 成功保存脚本依赖：**{summary['downloaded_dependencies']}**
- 已替换为本仓库 Raw 地址的依赖引用：**{summary['rewritten_dependency_references']}**
- 下载失败：**{summary['failed_downloads']}**

完整列表见 [`INDEX.md`](INDEX.md)，机器可读清单见 [`manifest.json`](manifest.json)。

## 目录

- `modules/`：按来源分类的 QX 去广告模块
- `custom_sources/`：自制模块的可维护源文件
- `dependencies/`：重写文件引用的远程脚本快照
- `sources.json`：模块来源清单
- `tools/sync.py`：重新抓取并更新快照

## 更新

```bash
python3 tools/sync.py
git add modules dependencies INDEX.md manifest.json README.md sources.json
git commit -m "Update Quantumult X ad-block mirror"
git push
```

## 来源

每个文件保留原有署名和头部说明。来源仓库及上游作者拥有各自内容的相应权利；本仓库用于个人备份。
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    (ROOT / ".gitignore").write_text(".DS_Store\n__pycache__/\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["downloaded_modules"] == summary["discovered_modules"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
