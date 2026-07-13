from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import webbrowser
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


CURRENT_VERSION = "v2.5.0"
GITHUB_LATEST_RELEASE_API = "https://api.github.com/repos/CaKa12152/Drill-Pirate/releases/latest"
GITHUB_RELEASES_API = "https://api.github.com/repos/CaKa12152/Drill-Pirate/releases?per_page=20"
GITHUB_RELEASES_URL = "https://github.com/CaKa12152/Drill-Pirate/releases/"

ProgressCallback = Callable[[str, int, int], None]


@dataclass(slots=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int = 0
    checksum_url: str = ""


@dataclass(slots=True)
class UpdateInfo:
    tag: str
    name: str
    html_url: str
    body: str
    asset: ReleaseAsset | None
    channel: str = "stable"


def fetch_latest_update(timeout_seconds: float = 5.0, channel: str = "stable") -> UpdateInfo | None:
    release = fetch_latest_release(timeout_seconds=timeout_seconds, channel=channel)
    if not release or not is_newer_version(release.tag, CURRENT_VERSION):
        return None
    return release


def fetch_latest_release(timeout_seconds: float = 5.0, channel: str = "stable") -> UpdateInfo | None:
    normalized_channel = normalize_update_channel(channel)
    if normalized_channel == "beta":
        return fetch_beta_release(timeout_seconds=timeout_seconds)
    return fetch_stable_release(timeout_seconds=timeout_seconds)


def fetch_stable_release(timeout_seconds: float = 5.0) -> UpdateInfo | None:
    request = urllib.request.Request(
        GITHUB_LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Drill-Pirate/{CURRENT_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    return update_from_release_payload(payload, "stable")


def fetch_beta_release(timeout_seconds: float = 5.0) -> UpdateInfo | None:
    request = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Drill-Pirate/{CURRENT_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    for release_payload in payload:
        if release_payload.get("draft"):
            continue
        release = update_from_release_payload(release_payload, "beta")
        if release:
            return release
    return None


def fetch_release_by_tag(tag: str, timeout_seconds: float = 5.0) -> UpdateInfo | None:
    cleaned = tag.strip()
    if not cleaned:
        return None
    url = f"https://api.github.com/repos/CaKa12152/Drill-Pirate/releases/tags/{cleaned}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Drill-Pirate/{CURRENT_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    return update_from_release_payload(payload, "stable")


def update_from_release_payload(payload: dict, channel: str) -> UpdateInfo | None:
    tag = str(payload.get("tag_name") or "")
    if not tag:
        return None
    raw_assets = [item for item in payload.get("assets", []) if item.get("browser_download_url")]
    checksum_urls = checksum_asset_urls(raw_assets)
    assets = [
        ReleaseAsset(
            name=str(item.get("name") or ""),
            download_url=str(item.get("browser_download_url") or ""),
            size=int(item.get("size") or 0),
            checksum_url=checksum_urls.get(str(item.get("name") or ""), checksum_urls.get("*", "")),
        )
        for item in raw_assets
        if not is_checksum_asset(str(item.get("name") or ""))
    ]
    return UpdateInfo(
        tag=tag,
        name=str(payload.get("name") or tag),
        html_url=str(payload.get("html_url") or GITHUB_RELEASES_URL),
        body=str(payload.get("body") or ""),
        asset=choose_windows_asset(assets),
        channel=channel,
    )


def normalize_update_channel(channel: object) -> str:
    return "beta" if str(channel).lower().strip() == "beta" else "stable"


def is_checksum_asset(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith((".sha256", ".sha256.txt", ".sha256sum", ".sha256sums.txt"))


def checksum_asset_urls(raw_assets: list[dict]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for item in raw_assets:
        name = str(item.get("name") or "")
        if not is_checksum_asset(name):
            continue
        url = str(item.get("browser_download_url") or "")
        lowered = name.lower()
        for suffix in (".sha256sums.txt", ".sha256.txt", ".sha256sum", ".sha256"):
            if lowered.endswith(suffix):
                checksums[name[: -len(suffix)]] = url
                break
        if name.lower() in {"sha256sums.txt", "checksums.sha256"}:
            checksums["*"] = url
    return checksums


def is_newer_version(candidate: str, current: str) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def version_tuple(value: str) -> tuple[int, int, int, str]:
    cleaned = value.lower().strip().lstrip("v")
    parts = cleaned.replace("-", ".").split(".")
    numbers: list[int] = []
    suffix_parts: list[str] = []
    for part in parts:
        if part.isdigit() and len(numbers) < 3:
            numbers.append(int(part))
        else:
            suffix_parts.append(part)
    while len(numbers) < 3:
        numbers.append(0)
    return numbers[0], numbers[1], numbers[2], ".".join(suffix_parts)


def choose_windows_asset(assets: list[ReleaseAsset]) -> ReleaseAsset | None:
    if not assets:
        return None
    supported = [
        asset
        for asset in assets
        if asset.name.lower().endswith((".zip", ".exe", ".msi"))
    ]
    if not supported:
        return None

    def score(asset: ReleaseAsset) -> tuple[int, int]:
        name = asset.name.lower()
        windows_score = 2 if "windows" in name or "win" in name else 0
        installer_score = 2 if name.endswith(".exe") or name.endswith(".msi") else 1
        return windows_score, installer_score

    return max(supported, key=score)


def download_asset(
    asset: ReleaseAsset,
    destination_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    destination_dir = destination_dir or Path(tempfile.mkdtemp(prefix="drill_pirate_update_"))
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / asset.name
    request = urllib.request.Request(
        asset.download_url,
        headers={"User-Agent": f"Drill-Pirate/{CURRENT_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as file:
        total = int(response.headers.get("Content-Length") or asset.size or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            file.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total:
                progress_callback("Downloading update", downloaded, total)
    if progress_callback:
        progress_callback("Update downloaded", 1, 1)
    verify_downloaded_asset(destination, asset)
    return destination


def verify_downloaded_asset(path: Path, asset: ReleaseAsset) -> None:
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError("Downloaded update is empty.")
    if asset.size and path.stat().st_size != asset.size:
        raise RuntimeError(
            f"Downloaded update size did not match GitHub asset size "
            f"({path.stat().st_size} bytes vs {asset.size} bytes)."
        )
    expected_hash = fetch_expected_sha256(asset)
    if expected_hash:
        actual_hash = sha256_file(path)
        if actual_hash.lower() != expected_hash.lower():
            raise RuntimeError("Downloaded update failed SHA-256 verification.")
    if path.suffix.lower() == ".zip":
        if not zipfile.is_zipfile(path):
            raise RuntimeError("Downloaded update ZIP is invalid.")
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if not any(name.lower().endswith("drill pirate.exe") for name in names):
                raise RuntimeError("Downloaded update ZIP does not contain Drill Pirate.exe.")


def fetch_expected_sha256(asset: ReleaseAsset) -> str:
    if not asset.checksum_url:
        return ""
    request = urllib.request.Request(
        asset.checksum_url,
        headers={"User-Agent": f"Drill-Pirate/{CURRENT_VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        return ""
    tokens = text.replace("\r", "\n").split()
    for index, token in enumerate(tokens):
        cleaned = token.strip().lower()
        if len(cleaned) == 64 and all(char in "0123456789abcdef" for char in cleaned):
            if len(tokens) == 1 or asset.name in tokens[index + 1 :] or asset.name in text:
                return cleaned
    return ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_update(
    update: UpdateInfo,
    progress_callback: ProgressCallback | None = None,
) -> str:
    if update.asset is None:
        webbrowser.open(update.html_url or GITHUB_RELEASES_URL)
        return "opened_release_page"

    package_path = download_asset(update.asset, progress_callback=progress_callback)
    if not getattr(sys, "frozen", False):
        webbrowser.open(update.html_url or GITHUB_RELEASES_URL)
        return "downloaded_dev_mode"

    suffix = package_path.suffix.lower()
    if suffix in (".exe", ".msi"):
        subprocess.Popen([str(package_path)], close_fds=True)
        return "launched_installer"
    if suffix == ".zip":
        script_path = write_windows_zip_update_script(package_path)
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(script_path),
            ],
            close_fds=True,
        )
        return "restart_required"

    webbrowser.open(update.html_url or GITHUB_RELEASES_URL)
    return "opened_release_page"


def write_windows_zip_update_script(package_path: Path) -> Path:
    executable = Path(sys.executable)
    target_dir = executable.parent
    script_path = package_path.with_suffix(".ps1")
    script = f"""
$ErrorActionPreference = "Stop"
$zip = {powershell_literal(str(package_path))}
$target = {powershell_literal(str(target_dir))}
$exeName = {powershell_literal(executable.name)}
$extract = Join-Path $env:TEMP ("DrillPirateUpdate_" + [guid]::NewGuid().ToString("N"))
$backup = Join-Path $env:TEMP ("DrillPirateRollback_" + [guid]::NewGuid().ToString("N"))
$log = Join-Path $env:TEMP "DrillPirateUpdate.log"
try {{
    Start-Sleep -Seconds 2
    New-Item -ItemType Directory -Path $extract -Force | Out-Null
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item -Path (Join-Path $target "*") -Destination $backup -Recurse -Force
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $candidate = Get-ChildItem -LiteralPath $extract -Recurse -Filter $exeName | Select-Object -First 1
    if ($candidate) {{
        $source = $candidate.Directory.FullName
    }} else {{
        throw "Could not find $exeName in update package."
    }}
    Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
    Start-Process -FilePath (Join-Path $target $exeName)
}} catch {{
    Add-Content -LiteralPath $log -Value ("Update failed: " + $_.Exception.Message)
    if (Test-Path -LiteralPath $backup) {{
        Copy-Item -Path (Join-Path $backup "*") -Destination $target -Recurse -Force
    }}
    Start-Process -FilePath (Join-Path $target $exeName)
}} finally {{
    if (Test-Path -LiteralPath $extract) {{
        Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue
    }}
}}
"""
    script_path.write_text(script.strip() + "\n", encoding="utf-8")
    return script_path


def powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
