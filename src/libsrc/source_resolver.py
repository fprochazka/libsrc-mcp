import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from libsrc.config import Config
from libsrc.models import Dependency, ResolvedSource

logger = logging.getLogger(__name__)

# Mapping from ecosystem names used in Dependency to deps.dev API system identifiers
_ECOSYSTEM_TO_DEPSDEV_SYSTEM: dict[str, str] = {
    "maven": "MAVEN",
    "gradle": "MAVEN",
    "poetry": "PYPI",
    "uv": "PYPI",
}

# PyPI project_urls keys to check, in priority order (case-insensitive matching)
_PYPI_URL_KEYS: list[str] = [
    "source",
    "source code",
    "repository",
    "code",
    "github",
    "homepage",
]

# Known git hosting URL patterns (scheme://host/owner/repo)
_GIT_URL_RE = re.compile(
    r"^(?:https?://|git://|ssh://(?:git@)?)"
    r"(?P<host>[^/:]+)"
    r"[/:]"
    r"(?P<owner>[^/]+)"
    r"/(?P<repo>[^/.]+)"
)

_GIT_AT_RE = re.compile(r"^git@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<repo>[^/.]+)")

_MAVEN_NS = "{http://maven.apache.org/POM/4.0.0}"


def normalize_repo_url(raw_url: str) -> tuple[str, str] | None:
    """Extract (hosting, normalized_url) from a raw repository URL.

    Returns a tuple of (hosting_hostname, https://host/owner/repo) or None if
    the URL cannot be parsed into a recognizable repository pattern.
    """
    if not raw_url:
        return None

    url = raw_url.strip()

    # Strip common prefixes
    for prefix in ("scm:git:", "scm:svn:", "scm:"):
        if url.lower().startswith(prefix):
            url = url[len(prefix) :]
            break

    # Try git@host:owner/repo.git pattern
    m = _GIT_AT_RE.match(url)
    if m:
        host = m.group("host")
        owner = m.group("owner")
        repo = m.group("repo")
        return host, f"https://{host}/{owner}/{repo}"

    # Try standard URL patterns
    m = _GIT_URL_RE.match(url)
    if m:
        host = m.group("host")
        owner = m.group("owner")
        repo = m.group("repo")
        return host, f"https://{host}/{owner}/{repo}"

    # Try parsing as a URL and extracting path components
    try:
        parsed = urlparse(url)
        if parsed.hostname and parsed.path:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2:
                host = parsed.hostname
                owner = parts[0]
                repo = parts[1]
                # Strip .git suffix
                if repo.endswith(".git"):
                    repo = repo[:-4]
                # Strip /tree/... /blob/... suffixes (already handled by taking first 2)
                return host, f"https://{host}/{owner}/{repo}"
    except Exception:
        pass

    return None


class SourceResolver:
    """Resolves a Dependency to its source repository URL using a layered approach."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._http_client: httpx.AsyncClient | None = None
        self._cache_base = Path.home() / ".cache" / "libsrc" / "depsdev"

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._http_client

    async def resolve(self, dependency: Dependency) -> ResolvedSource | None:
        """Try to resolve the source repository for a dependency.

        Returns ResolvedSource with repo_url and hosting info, or None if not found.
        """
        # Try deps.dev first
        result = await self._resolve_via_depsdev(dependency)
        if result is not None:
            return result

        # Try ecosystem-specific fallbacks
        ecosystem = dependency.ecosystem.lower()
        if ecosystem in ("maven", "gradle"):
            result = await self._resolve_via_maven_pom(dependency)
        elif ecosystem in ("poetry", "uv"):
            result = await self._resolve_via_pypi(dependency)

        return result

    async def _resolve_via_depsdev(self, dep: Dependency) -> ResolvedSource | None:
        """Look up the dependency on deps.dev API."""
        system = _ECOSYSTEM_TO_DEPSDEV_SYSTEM.get(dep.ecosystem.lower())
        if system is None:
            logger.debug("No deps.dev system mapping for ecosystem: %s", dep.ecosystem)
            return None

        encoded_name = quote(dep.identifier, safe="")
        encoded_version = quote(dep.version, safe="")

        # Check cache
        cached = self._read_depsdev_cache(system, encoded_name, dep.version)
        if cached is not None:
            return self._extract_source_from_depsdev(cached)

        # Fetch from API
        url = (
            f"https://api.deps.dev/v3/systems/{system}/packages/"
            f"{encoded_name}/versions/{encoded_version}"
        )

        try:
            client = self._get_client()
            response = await client.get(url)
            if response.status_code == 404:
                logger.debug(
                    "deps.dev: package not found: %s %s", dep.identifier, dep.version
                )
                return None
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.debug("deps.dev lookup failed for %s: %s", dep.identifier, e)
            return None

        # Cache the response
        self._write_depsdev_cache(system, encoded_name, dep.version, data)

        return self._extract_source_from_depsdev(data)

    def _extract_source_from_depsdev(self, data: dict) -> ResolvedSource | None:
        """Extract source repo URL from a deps.dev GetVersion response."""
        # Check links array for SOURCE_REPO
        links = data.get("links", [])
        for link in links:
            if link.get("label") == "SOURCE_REPO":
                raw_url = link.get("url", "")
                result = normalize_repo_url(raw_url)
                if result is not None:
                    hosting, repo_url = result
                    trusted = hosting in self.config.trusted_hosts
                    return ResolvedSource(
                        repo_url=repo_url,
                        hosting=hosting,
                        trusted=trusted,
                    )

        # Check relatedProjects as secondary source
        related = data.get("relatedProjects", [])
        for project in related:
            project_key = project.get("projectKey", {}).get("id", "")
            if project_key:
                # projectKey is like "github.com/owner/repo"
                raw_url = f"https://{project_key}"
                result = normalize_repo_url(raw_url)
                if result is not None:
                    hosting, repo_url = result
                    trusted = hosting in self.config.trusted_hosts
                    return ResolvedSource(
                        repo_url=repo_url,
                        hosting=hosting,
                        trusted=trusted,
                    )

        return None

    def _depsdev_cache_path(self, system: str, encoded_name: str, version: str) -> Path:
        return self._cache_base / system.lower() / encoded_name / f"{version}.json"

    def _read_depsdev_cache(
        self, system: str, encoded_name: str, version: str
    ) -> dict | None:
        cache_file = self._depsdev_cache_path(system, encoded_name, version)
        if not cache_file.is_file():
            return None

        # Check TTL
        try:
            mtime = cache_file.stat().st_mtime
            mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            age_hours = (now - mtime_dt).total_seconds() / 3600
            if age_hours > self.config.deps_dev_cache_ttl:
                logger.debug("deps.dev cache expired for %s/%s", encoded_name, version)
                return None
        except OSError:
            return None

        try:
            return json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Failed to read deps.dev cache: %s", e)
            return None

    def _write_depsdev_cache(
        self, system: str, encoded_name: str, version: str, data: dict
    ) -> None:
        cache_file = self._depsdev_cache_path(system, encoded_name, version)
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.debug("Failed to write deps.dev cache: %s", e)

    async def _resolve_via_maven_pom(self, dep: Dependency) -> ResolvedSource | None:
        """Download POM from Maven Central and extract SCM URL."""
        parts = dep.identifier.split(":")
        if len(parts) != 2:
            logger.debug("Invalid Maven identifier format: %s", dep.identifier)
            return None

        group_id, artifact_id = parts
        group_path = group_id.replace(".", "/")
        pom_url = (
            f"https://repo1.maven.org/maven2/{group_path}/{artifact_id}/"
            f"{dep.version}/{artifact_id}-{dep.version}.pom"
        )

        try:
            client = self._get_client()
            response = await client.get(pom_url)
            if response.status_code == 404:
                logger.debug("Maven POM not found: %s", pom_url)
                return None
            response.raise_for_status()
            pom_text = response.text
        except httpx.HTTPError as e:
            logger.debug("Failed to download Maven POM for %s: %s", dep.identifier, e)
            return None

        return self._extract_scm_from_pom(pom_text)

    def _extract_scm_from_pom(self, pom_text: str) -> ResolvedSource | None:
        """Parse POM XML and extract SCM URL."""
        try:
            root = ET.fromstring(pom_text)
        except ET.ParseError as e:
            logger.debug("Failed to parse POM XML: %s", e)
            return None

        # Try with namespace first, then without
        for ns_prefix in (_MAVEN_NS, ""):
            scm = root.find(f"{ns_prefix}scm")
            if scm is None:
                continue

            # Try <url> first, then <connection>
            for tag in ("url", "connection"):
                elem = scm.find(f"{ns_prefix}{tag}")
                if elem is not None and elem.text:
                    raw_url = elem.text.strip()
                    result = normalize_repo_url(raw_url)
                    if result is not None:
                        hosting, repo_url = result
                        trusted = hosting in self.config.trusted_hosts
                        return ResolvedSource(
                            repo_url=repo_url,
                            hosting=hosting,
                            trusted=trusted,
                        )

        return None

    async def _resolve_via_pypi(self, dep: Dependency) -> ResolvedSource | None:
        """Look up the dependency on PyPI JSON API."""
        url = f"https://pypi.org/pypi/{quote(dep.identifier, safe='')}/{quote(dep.version, safe='')}/json"

        try:
            client = self._get_client()
            response = await client.get(url)
            if response.status_code == 404:
                logger.debug(
                    "PyPI package not found: %s %s", dep.identifier, dep.version
                )
                return None
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.debug("PyPI lookup failed for %s: %s", dep.identifier, e)
            return None

        project_urls = data.get("info", {}).get("project_urls") or {}

        # Build a lowercase-keyed lookup
        urls_lower: dict[str, str] = {k.lower(): v for k, v in project_urls.items()}

        # Check keys in priority order
        for key in _PYPI_URL_KEYS:
            value = urls_lower.get(key)
            if value:
                result = normalize_repo_url(value)
                if result is not None:
                    hosting, repo_url = result
                    trusted = hosting in self.config.trusted_hosts
                    return ResolvedSource(
                        repo_url=repo_url,
                        hosting=hosting,
                        trusted=trusted,
                    )

        return None

    async def _close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
