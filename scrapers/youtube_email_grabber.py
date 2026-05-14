from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib import error, parse, request

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None


DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_RETRIES = 3
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CHANNEL_TAB_SUFFIX_RE = re.compile(r"/(about|featured|videos|shorts|streams|playlists|community|channels)$", re.IGNORECASE)
STANDARD_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
OBFUSCATED_EMAIL_RE = re.compile(
    r"""
    (?P<local>[A-Z0-9._%+-]{1,64})
    \s*
    (?:@|\(at\)|\[at\]|\{at\}|\sat\s)
    \s*
    (?P<domain>[A-Z0-9-]+(?:\s*(?:\.|\(dot\)|\[dot\]|\{dot\}|\sdot\s)\s*[A-Z0-9-]+)+)
    """,
    re.IGNORECASE | re.VERBOSE,
)


class YtDlpSearchError(RuntimeError):
    """Raised when yt-dlp search fails."""


class ChannelPageFetchError(RuntimeError):
    """Raised when a channel page cannot be fetched."""


@dataclass
class ChannelProfile:
    about_url: str
    profile_bio: str
    emails: list[tuple[str, str]]
    needs_manual_verification: bool


@dataclass
class VideoMatch:
    keyword: str
    email: str
    source: str
    source_url: str
    matched_text: str
    profile_handle: str
    profile_bio: str
    video_id: str
    video_title: str
    video_url: str
    channel_id: str
    channel_title: str
    channel_url: str
    published_at: str


@dataclass
class ManualVerificationLead:
    keyword: str
    status: str
    reason: str
    manual_email: str
    notes: str
    profile_handle: str
    profile_bio: str
    channel_title: str
    channel_url: str
    channel_id: str
    about_url: str
    source_video_title: str
    source_video_url: str
    source_video_id: str
    published_at: str


class YtDlpClient:
    def __init__(
        self,
        yt_dlp_path: str | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.yt_dlp_path = yt_dlp_path or shutil.which("yt-dlp")
        self.use_python_module = YoutubeDL is not None and yt_dlp_path is None

        if not self.use_python_module and not self.yt_dlp_path:
            raise YtDlpSearchError(
                "yt-dlp is not installed. Install it with 'py -3 -m pip install yt-dlp' "
                "or pass --yt-dlp-path to a local yt-dlp executable."
            )

    def search_videos(
        self,
        query: str,
        max_results: int,
        order: str,
        published_after: datetime | None = None,
    ) -> list[dict]:
        search_term = build_search_term(
            query=query,
            max_results=expanded_search_count(max_results=max_results, order=order),
        )

        if self.use_python_module:
            entries = self._search_with_python_module(search_term=search_term, max_results=max_results)
        else:
            entries = self._search_with_command(search_term=search_term)

        filtered_entries: list[dict] = []
        for entry in entries:
            if not entry:
                continue
            if published_after and not is_entry_after(entry, published_after):
                continue
            filtered_entries.append(entry)

        if order == "date":
            filtered_entries.sort(key=entry_sort_key, reverse=True)

        return filtered_entries[:max_results]

    def _search_with_python_module(self, search_term: str, max_results: int) -> list[dict]:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
            "noplaylist": True,
            "playlistend": max_results,
            "socket_timeout": self.timeout,
        }

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                with YoutubeDL(options) as ydl:
                    payload = ydl.extract_info(search_term, download=False)
                return normalize_entries(payload)
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(attempt * 1.5)
                    continue
                raise YtDlpSearchError(f"yt-dlp Python module search failed: {exc}") from exc

        raise YtDlpSearchError(f"yt-dlp Python module search failed: {last_error}")

    def _search_with_command(self, search_term: str) -> list[dict]:
        command = [
            self.yt_dlp_path,
            "--dump-single-json",
            "--quiet",
            "--no-warnings",
            "--skip-download",
            "--socket-timeout",
            str(self.timeout),
            search_term,
        ]

        result = None
        for attempt in range(1, self.retries + 1):
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
            except OSError as exc:
                raise YtDlpSearchError(f"Failed to launch yt-dlp: {exc}") from exc

            if result.returncode == 0:
                break

            if attempt < self.retries:
                time.sleep(attempt * 1.5)

        if result is None:
            raise YtDlpSearchError("yt-dlp command search failed before producing output.")

        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "Unknown yt-dlp error"
            raise YtDlpSearchError(f"yt-dlp command search failed: {message}")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise YtDlpSearchError("yt-dlp returned non-JSON output.") from exc

        return normalize_entries(payload)


class ChannelPageFetcher:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT_SECONDS, retries: int = DEFAULT_RETRIES) -> None:
        self.timeout = timeout
        self.retries = retries

    def fetch_text(self, url: str) -> str:
        last_error: Exception | None = None
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }

        for attempt in range(1, self.retries + 1):
            req = request.Request(url, headers=headers)
            try:
                with request.urlopen(req, timeout=self.timeout) as response:
                    content_type = response.headers.get_content_charset() or "utf-8"
                    return response.read().decode(content_type, errors="replace")
            except error.HTTPError as exc:
                last_error = exc
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.retries:
                    time.sleep(attempt * 1.5)
                    continue
                raise ChannelPageFetchError(f"HTTP {exc.code} for {url}") from exc
            except error.URLError as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(attempt * 1.5)
                    continue
                raise ChannelPageFetchError(f"Unable to fetch {url}: {exc}") from exc

        raise ChannelPageFetchError(f"Unable to fetch {url}: {last_error}")


def expanded_search_count(max_results: int, order: str) -> int:
    if order != "date":
        return max_results
    return min(max(max_results * 4, max_results), 200)


def build_search_term(query: str, max_results: int) -> str:
    return f"ytsearch{max_results}:{query}"


def normalize_entries(payload: dict | None) -> list[dict]:
    if not payload:
        return []

    entries = payload.get("entries")
    if entries is None:
        return [payload]

    return [entry for entry in entries if entry]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search YouTube videos with yt-dlp and extract public emails from video descriptions."
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Keyword to search. Repeat this flag to run multiple keyword groups.",
    )
    parser.add_argument(
        "--query-file",
        help="Optional text file with one keyword per line.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=25,
        help="Maximum videos to inspect per keyword. Default: 25",
    )
    parser.add_argument(
        "--order",
        choices=["relevance", "date"],
        default="relevance",
        help="Search sort order supported by yt-dlp. Default: relevance",
    )
    parser.add_argument(
        "--published-after",
        help="Only keep videos published after this UTC date or timestamp, for example 2025-01-01 or 2025-01-01T00:00:00Z",
    )
    parser.add_argument(
        "--output",
        default="output/youtube_emails.csv",
        help="CSV path for extracted emails. Default: output/youtube_emails.csv",
    )
    parser.add_argument(
        "--verification-queue-output",
        help="CSV path for channels that need manual email verification. Default: output filename plus _verification_queue.",
    )
    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="Keep duplicate email rows instead of returning one row per unique email.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Optional delay in seconds between keywords. Default: 0",
    )
    parser.add_argument(
        "--yt-dlp-path",
        help="Optional path to a local yt-dlp executable.",
    )
    parser.add_argument(
        "--skip-channel-about",
        action="store_true",
        help="Skip scanning each unique channel's About page for additional public emails.",
    )
    return parser.parse_args()


def load_queries(cli_queries: list[str], query_file: str | None) -> list[str]:
    queries = [query.strip() for query in cli_queries if query and query.strip()]

    if query_file:
        path = Path(query_file)
        if not path.exists():
            raise FileNotFoundError(f"Query file does not exist: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                queries.append(value)

    deduped_queries = list(dict.fromkeys(queries))
    if not deduped_queries:
        raise ValueError("No queries supplied. Use --query or --query-file.")
    return deduped_queries


def parse_published_after(value: str | None) -> datetime | None:
    if not value:
        return None

    raw = value.strip()
    if not raw:
        return None

    known_formats = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y%m%d")
    for fmt in known_formats:
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "Invalid --published-after value. Use formats like 2025-01-01 or 2025-01-01T00:00:00Z."
        ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_entry_datetime(entry: dict) -> datetime | None:
    timestamp = entry.get("timestamp") or entry.get("release_timestamp")
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    for key in ("upload_date", "release_date"):
        raw = entry.get(key)
        if isinstance(raw, str) and len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)

    return None


def entry_sort_key(entry: dict) -> datetime:
    return parse_entry_datetime(entry) or datetime(1970, 1, 1, tzinfo=timezone.utc)


def format_published_at(entry: dict) -> str:
    parsed = parse_entry_datetime(entry)
    if parsed is None:
        return ""
    return parsed.isoformat().replace("+00:00", "Z")


def is_entry_after(entry: dict, threshold: datetime) -> bool:
    published = parse_entry_datetime(entry)
    if published is None:
        return False
    return published >= threshold


def decode_json_unicode_escapes(text: str) -> str:
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), text)


def page_text_variants(text: str) -> list[str]:
    decoded = decode_json_unicode_escapes(text)
    return [
        text,
        html.unescape(text),
        decoded,
        html.unescape(decoded),
    ]


def normalize_email(candidate: str) -> str:
    return candidate.strip().strip(".,;:!?)(").lower()


def extract_emails(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    seen: set[str] = set()

    for raw in STANDARD_EMAIL_RE.findall(text):
        email = normalize_email(raw)
        if email not in seen:
            seen.add(email)
            matches.append((email, raw))

    for obfuscated in OBFUSCATED_EMAIL_RE.finditer(text):
        local_part = obfuscated.group("local").strip()
        domain_part = obfuscated.group("domain")
        domain = re.sub(r"\s*(?:\.|\(dot\)|\[dot\]|\{dot\}|\sdot\s)\s*", ".", domain_part, flags=re.IGNORECASE)
        candidate = normalize_email(f"{local_part}@{domain}")
        if STANDARD_EMAIL_RE.fullmatch(candidate) and candidate not in seen:
            seen.add(candidate)
            matches.append((candidate, obfuscated.group(0)))

    return matches


def extract_emails_from_page_text(text: str) -> list[tuple[str, str]]:
    combined: list[tuple[str, str]] = []
    seen: set[str] = set()

    for variant in page_text_variants(text):
        for email, matched_text in extract_emails(variant):
            if email in seen:
                continue
            seen.add(email)
            combined.append((email, matched_text))

    return combined


def detects_manual_email_button(text: str) -> bool:
    markers = (
        "view email address",
        "view email",
        "show email",
        "查看电子邮件地址",
        "查看电子邮件",
        "显示电子邮件",
        "business email",
    )

    for variant in page_text_variants(text):
        haystack = normalize_whitespace(variant).lower()
        if any(marker in haystack for marker in markers):
            return True

    return False


def decode_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_profile_text(text: str, limit: int = 500) -> str:
    cleaned = html.unescape(decode_json_unicode_escapes(text))
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = normalize_whitespace(cleaned)
    if len(cleaned) > limit:
        return cleaned[: limit - 3].rstrip() + "..."
    return cleaned


def extract_profile_bio(text: str) -> str:
    patterns = [
        r'"channelDescription"\s*:\s*"((?:\\.|[^"\\])*)"',
        r'"description"\s*:\s*\{\s*"simpleText"\s*:\s*"((?:\\.|[^"\\])*)"',
        r'"description"\s*:\s*"((?:\\.|[^"\\])*)"'
    ]
    candidates: list[str] = []
    seen: set[str] = set()

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = clean_profile_text(decode_json_string(match.group(1)))
            if len(candidate) < 12 or candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)

    if not candidates:
        return ""

    candidates.sort(key=len, reverse=True)
    return candidates[0]


def build_video_url(entry: dict) -> str:
    webpage_url = entry.get("webpage_url")
    if webpage_url:
        return webpage_url

    video_id = entry.get("id", "")
    if not video_id:
        return ""
    return f"https://www.youtube.com/watch?v={video_id}"


def build_channel_url(entry: dict) -> str:
    for key in ("channel_url", "uploader_url"):
        value = entry.get(key)
        if value:
            return value

    channel_id = entry.get("channel_id")
    if channel_id:
        return f"https://www.youtube.com/channel/{channel_id}"

    uploader_id = entry.get("uploader_id")
    if uploader_id:
        return f"https://www.youtube.com/{uploader_id}"

    return ""


def build_channel_about_url(channel_url: str) -> str:
    if not channel_url:
        return ""

    parsed_url = parse.urlsplit(channel_url)
    scheme = parsed_url.scheme or "https"
    netloc = parsed_url.netloc or "www.youtube.com"
    path = parsed_url.path.rstrip("/")
    if not path:
        return ""

    normalized_path = CHANNEL_TAB_SUFFIX_RE.sub("", path)
    if not normalized_path:
        return ""

    return parse.urlunsplit((scheme, netloc, f"{normalized_path}/about", "", ""))


def extract_channel_handle(channel_url: str) -> str:
    if not channel_url:
        return ""

    path = parse.urlsplit(channel_url).path.strip("/")
    if not path:
        return ""

    handle = path.split("/", 1)[0]
    return handle if handle.startswith("@") else ""


def build_matches(
    keyword: str,
    videos: Iterable[dict],
    channel_profiles: dict[str, ChannelProfile] | None = None,
) -> list[VideoMatch]:
    rows: list[VideoMatch] = []

    for video in videos:
        description = video.get("description", "") or ""
        extracted = extract_emails(description)
        if not extracted:
            continue

        video_id = video.get("id", "")
        channel_id = video.get("channel_id", "") or ""
        channel_url = build_channel_url(video)
        channel_title = video.get("channel") or video.get("uploader") or ""
        channel_key = channel_id or channel_url
        profile = channel_profiles.get(channel_key) if channel_profiles else None

        for email, matched_text in extracted:
            rows.append(
                VideoMatch(
                    keyword=keyword,
                    email=email,
                    source="description",
                    source_url=build_video_url(video),
                    matched_text=matched_text,
                    profile_handle=extract_channel_handle(channel_url),
                    profile_bio=profile.profile_bio if profile else "",
                    video_id=video_id,
                    video_title=video.get("title", "") or "",
                    video_url=build_video_url(video),
                    channel_id=channel_id,
                    channel_title=channel_title,
                    channel_url=channel_url,
                    published_at=format_published_at(video),
                )
            )

    return rows


def build_channel_matches(
    keyword: str,
    source_video: dict,
    profile: ChannelProfile,
) -> list[VideoMatch]:
    rows: list[VideoMatch] = []

    channel_id = source_video.get("channel_id", "") or ""
    channel_url = build_channel_url(source_video)
    channel_title = source_video.get("channel") or source_video.get("uploader") or ""

    for email, matched_text in profile.emails:
        rows.append(
            VideoMatch(
                keyword=keyword,
                email=email,
                source="channel_about",
                source_url=profile.about_url,
                matched_text=matched_text,
                profile_handle=extract_channel_handle(channel_url),
                profile_bio=profile.profile_bio,
                video_id=source_video.get("id", "") or "",
                video_title=source_video.get("title", "") or "",
                video_url=build_video_url(source_video),
                channel_id=channel_id,
                channel_title=channel_title,
                channel_url=channel_url,
                published_at=format_published_at(source_video),
            )
        )

    return rows


def build_manual_verification_lead(
    keyword: str,
    source_video: dict,
    profile: ChannelProfile,
) -> ManualVerificationLead:
    channel_url = build_channel_url(source_video)
    reason = "email_button_detected"
    if profile.emails:
        reason = "email_button_detected; visible_email_also_found"

    return ManualVerificationLead(
        keyword=keyword,
        status="needs_manual",
        reason=reason,
        manual_email="",
        notes="",
        profile_handle=extract_channel_handle(channel_url),
        profile_bio=profile.profile_bio,
        channel_title=source_video.get("channel") or source_video.get("uploader") or "",
        channel_url=channel_url,
        channel_id=source_video.get("channel_id", "") or "",
        about_url=profile.about_url,
        source_video_title=source_video.get("title", "") or "",
        source_video_url=build_video_url(source_video),
        source_video_id=source_video.get("id", "") or "",
        published_at=format_published_at(source_video),
    )


def build_channel_seed_map(videos: Iterable[dict]) -> dict[str, dict]:
    seeds: dict[str, dict] = {}

    for video in videos:
        channel_url = build_channel_url(video)
        channel_id = video.get("channel_id", "") or ""
        key = channel_id or channel_url
        if not key or key in seeds:
            continue
        seeds[key] = video

    return seeds


def scan_channel_about_pages(
    keyword: str,
    videos: Iterable[dict],
    fetcher: ChannelPageFetcher,
    profile_cache: dict[str, ChannelProfile | None],
) -> tuple[list[VideoMatch], int, dict[str, ChannelProfile], list[ManualVerificationLead]]:
    rows: list[VideoMatch] = []
    pages_scanned = 0
    profiles_for_query: dict[str, ChannelProfile] = {}
    manual_leads: list[ManualVerificationLead] = []

    for channel_key, source_video in build_channel_seed_map(videos).items():
        channel_url = build_channel_url(source_video)
        about_url = build_channel_about_url(channel_url)
        if not about_url:
            continue

        if about_url not in profile_cache:
            pages_scanned += 1
            try:
                page_text = fetcher.fetch_text(about_url)
            except ChannelPageFetchError:
                profile_cache[about_url] = None
            else:
                profile_cache[about_url] = ChannelProfile(
                    about_url=about_url,
                    profile_bio=extract_profile_bio(page_text),
                    emails=extract_emails_from_page_text(page_text),
                    needs_manual_verification=detects_manual_email_button(page_text),
                )

        profile = profile_cache.get(about_url)
        if not profile:
            continue

        profiles_for_query[channel_key] = profile
        if profile.needs_manual_verification:
            manual_leads.append(build_manual_verification_lead(keyword=keyword, source_video=source_video, profile=profile))

        if not profile.emails:
            continue

        rows.extend(build_channel_matches(keyword=keyword, source_video=source_video, profile=profile))

    return rows, pages_scanned, profiles_for_query, manual_leads


def dedupe_matches(matches: list[VideoMatch]) -> list[VideoMatch]:
    deduped: list[VideoMatch] = []
    seen: set[tuple[str, str]] = set()

    for match in matches:
        identity = (match.email, match.channel_id or match.channel_url or match.source_url)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(match)

    return deduped


def dedupe_manual_leads(leads: list[ManualVerificationLead]) -> list[ManualVerificationLead]:
    deduped: list[ManualVerificationLead] = []
    seen: set[str] = set()

    for lead in leads:
        identity = lead.channel_id or lead.channel_url or lead.about_url
        if not identity or identity in seen:
            continue
        seen.add(identity)
        deduped.append(lead)

    return deduped


def write_csv(matches: list[VideoMatch], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "keyword",
                "email",
                "source",
                "source_url",
                "matched_text",
                "profile_handle",
                "profile_bio",
                "video_title",
                "video_url",
                "video_id",
                "channel_title",
                "channel_url",
                "channel_id",
                "published_at",
            ],
        )
        writer.writeheader()
        for match in matches:
            writer.writerow(
                {
                    "keyword": match.keyword,
                    "email": match.email,
                    "source": match.source,
                    "source_url": match.source_url,
                    "matched_text": match.matched_text,
                    "profile_handle": match.profile_handle,
                    "profile_bio": match.profile_bio,
                    "video_title": match.video_title,
                    "video_url": match.video_url,
                    "video_id": match.video_id,
                    "channel_title": match.channel_title,
                    "channel_url": match.channel_url,
                    "channel_id": match.channel_id,
                    "published_at": match.published_at,
                }
            )


def write_manual_queue_csv(leads: list[ManualVerificationLead], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "keyword",
                "status",
                "reason",
                "manual_email",
                "notes",
                "profile_handle",
                "profile_bio",
                "channel_title",
                "channel_url",
                "channel_id",
                "about_url",
                "source_video_title",
                "source_video_url",
                "source_video_id",
                "published_at",
            ],
        )
        writer.writeheader()
        for lead in leads:
            writer.writerow(
                {
                    "keyword": lead.keyword,
                    "status": lead.status,
                    "reason": lead.reason,
                    "manual_email": lead.manual_email,
                    "notes": lead.notes,
                    "profile_handle": lead.profile_handle,
                    "profile_bio": lead.profile_bio,
                    "channel_title": lead.channel_title,
                    "channel_url": lead.channel_url,
                    "channel_id": lead.channel_id,
                    "about_url": lead.about_url,
                    "source_video_title": lead.source_video_title,
                    "source_video_url": lead.source_video_url,
                    "source_video_id": lead.source_video_id,
                    "published_at": lead.published_at,
                }
            )


def default_verification_queue_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_verification_queue.csv")


def print_summary(total_videos: int, raw_matches: list[VideoMatch], final_matches: list[VideoMatch], output: Path) -> None:
    print()
    print("Done.")
    print(f"Videos scanned: {total_videos}")
    print(f"Emails found (raw): {len(raw_matches)}")
    print(f"Emails exported: {len(final_matches)}")
    print(f"CSV written to: {output}")


def main() -> int:
    args = parse_args()

    try:
        queries = load_queries(args.query, args.query_file)
        published_after = parse_published_after(args.published_after)
        client = YtDlpClient(yt_dlp_path=args.yt_dlp_path)
    except (FileNotFoundError, ValueError, YtDlpSearchError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    total_videos = 0
    total_channel_pages = 0
    all_matches: list[VideoMatch] = []
    manual_leads: list[ManualVerificationLead] = []
    profile_cache: dict[str, ChannelProfile | None] = {}
    fetcher = None if args.skip_channel_about else ChannelPageFetcher()

    for index, query in enumerate(queries, start=1):
        print(f"[{index}/{len(queries)}] Searching: {query}")
        try:
            videos = client.search_videos(
                query=query,
                max_results=args.max_results,
                order=args.order,
                published_after=published_after,
            )
        except YtDlpSearchError as exc:
            print(f"  Failed to fetch YouTube data for query '{query}': {exc}", file=sys.stderr)
            continue

        total_videos += len(videos)
        channel_matches: list[VideoMatch] = []
        pages_scanned = 0
        channel_profiles: dict[str, ChannelProfile] = {}
        query_manual_leads: list[ManualVerificationLead] = []
        if fetcher is not None:
            channel_matches, pages_scanned, channel_profiles, query_manual_leads = scan_channel_about_pages(
                keyword=query,
                videos=videos,
                fetcher=fetcher,
                profile_cache=profile_cache,
            )
            total_channel_pages += pages_scanned
            manual_leads.extend(query_manual_leads)
        query_matches = build_matches(keyword=query, videos=videos, channel_profiles=channel_profiles)
        all_matches.extend(query_matches)
        all_matches.extend(channel_matches)
        print(f"  Videos fetched: {len(videos)}")
        print(f"  Emails found in descriptions: {len(query_matches)}")
        if fetcher is not None:
            print(f"  Unique channel About pages scanned: {pages_scanned}")
            print(f"  Emails found in channel About pages: {len(channel_matches)}")
            print(f"  Manual verification leads: {len(query_manual_leads)}")

        if args.sleep > 0 and index < len(queries):
            time.sleep(args.sleep)

    final_matches = all_matches if args.keep_duplicates else dedupe_matches(all_matches)
    output_path = Path(args.output)
    verification_queue_path = (
        Path(args.verification_queue_output)
        if args.verification_queue_output
        else default_verification_queue_path(output_path)
    )
    final_manual_leads = manual_leads if args.keep_duplicates else dedupe_manual_leads(manual_leads)
    write_csv(final_matches, output_path)
    write_manual_queue_csv(final_manual_leads, verification_queue_path)
    if fetcher is not None:
        print(f"Unique channel About pages fetched across run: {total_channel_pages}")
    print(f"Manual verification leads exported: {len(final_manual_leads)}")
    print(f"Manual queue written to: {verification_queue_path}")
    print_summary(total_videos=total_videos, raw_matches=all_matches, final_matches=final_matches, output=output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
