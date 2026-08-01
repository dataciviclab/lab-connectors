"""HTTP client with SSL fallback, retry, backoff, 429 handling, and proxy fallback.

This module provides a shared HTTP client used by all Lab repos.
It wraps requests with:
- Connection pooling (shared session, used for SSL fallback)
- SSL fallback (verify=False on SSLError)
- Configurable timeout and User-Agent
- Exponential backoff retry (configurable)
- 429 Retry-After handling
- Proxy fallback on 403/407 (via BLOCKED_SOURCE_PROXY env)
- HEAD, GET and POST methods
- HttpResult return type (no exceptions raised on HTTP errors)
"""

from __future__ import annotations

import datetime
import logging
import os
import random
import shutil
import ssl
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning

from lab_connectors.http.types import CircuitOpenError, HttpFallbackError, HttpResult

logger = logging.getLogger("lab_connectors.http")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/604.1",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/134.0.0.0",
]


def _rand_ua() -> str:
    return random.choice(_USER_AGENTS)


class _SimpleResponse:
    """Minimal ResponseLike wrapper per risultati da curl/urllib."""

    def __init__(self, content: bytes, status_code: int = 200, url: str = ""):
        self._content = content
        self.status_code = status_code
        self.url = url
        self.reason = "OK" if status_code < 400 else "Error"
        self.headers = {"Content-Type": "application/octet-stream"}
        self._encoding = "utf-8"

    @property
    def content(self) -> bytes:
        return self._content

    @property
    def text(self) -> str:
        return self._content.decode(self._encoding, errors="replace")

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        import json as _json

        return _json.loads(self._content)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} {self.reason}", response=self)  # type: ignore[arg-type]


class _Tls12Adapter(HTTPAdapter):
    """Adapter che forza TLS 1.2 (per server PA che non supportano TLS 1.3)."""

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> Any:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


class HttpClient:
    """HTTP client with SSL fallback, retry, and backoff.

    Usage:
        client = HttpClient(timeout=15)
        result = client.get("https://example.com/data.csv")
        if result.is_ok:
            print(result.response.status_code)
        else:
            print(f"Failed: {result.err}")

        # POST is also supported (same SSL fallback + retry pattern)
        result = client.post("https://example.com/api", data={"key": "value"})
    """

    DEFAULT_TIMEOUT_SECONDS = 60
    DEFAULT_USER_AGENT = "DataCivicLab-HttpClient/0.1"

    def __init__(
        self,
        timeout: int | float | tuple[int, int] = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
        retry_backoff: float = 1.0,
        user_agent: str | None = None,
        retry_jitter: float = 0.0,
        circuit_threshold: int = 0,
    ):
        """Initialize HttpClient.

        Args:
            timeout: Request timeout in seconds.
            max_retries: Number of attempts on transient errors (5xx, 429,
                connection errors). Default 2 (2 total attempts: try once,
                retry once on failure).
            retry_backoff: Base delay in seconds for exponential backoff.
                Actual delay = backoff * 2^(attempt-1). Default 1.0.
            user_agent: Custom User-Agent string.
            retry_jitter: Randomisation factor for backoff delay (0.0 = no
                jitter). Each sleep is multiplied by ``uniform(1-jitter,
                1+jitter)``. Es. 0.1 = ±10% variation. Disabled by default.
            circuit_threshold: Number of consecutive failures on the same
                host before the circuit breaker opens. 0 = disabled.
                When open, further requests to that host return
                ``CircuitOpenError`` immediately without a network call.
                The circuit resets on the first success.

        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.retry_jitter = retry_jitter
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

        # Circuit breaker (per-host)
        self._circuit_threshold = circuit_threshold
        self._cb_consecutive: dict[str, int] = {}
        self._cb_lock = threading.Lock()

        # Shared session for SSL fallback (connection pooling)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = self.user_agent

    def close(self) -> None:
        """Close the underlying session and release connection pool resources."""
        self._session.close()

    def __enter__(self) -> HttpClient:
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Close the session when exiting the context manager."""
        self.close()

    # ------------------------------------------------------------------
    # Circuit breaker (per-host)
    # ------------------------------------------------------------------

    @staticmethod
    def _netloc(url: str) -> str | None:
        """Extract hostname from URL for circuit breaker key."""
        try:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.netloc or "").lower()
            return host or None
        except Exception:
            return None

    def _circuit_should_block(self, url: str) -> bool:
        """Check if the circuit is open for this host.

        Returns True if the request should be skipped.
        """
        if self._circuit_threshold <= 0:
            return False
        host = self._netloc(url)
        if not host:
            return False
        with self._cb_lock:
            return self._cb_consecutive.get(host, 0) >= self._circuit_threshold

    def circuit_is_open(self, url: str) -> bool:
        """Check if the circuit breaker is open for a given URL's host.

        Returns True if the host is currently blocked.
        Public alternative to ``_circuit_should_block`` for external callers.
        """
        return self._circuit_should_block(url)

    def _circuit_after_result(self, url: str, result: HttpResult) -> None:
        """Update circuit state after a request completes."""
        if self._circuit_threshold <= 0:
            return
        host = self._netloc(url)
        if not host:
            return
        # Consider an error as: err is set, or HTTP 5xx
        failed = result.err is not None or (
            result.response is not None and result.response.status_code >= 500
        )
        with self._cb_lock:
            if failed:
                n = self._cb_consecutive.get(host, 0) + 1
                self._cb_consecutive[host] = n
                if n == self._circuit_threshold:
                    logger.warning(
                        "Circuit breaker: host %s aperto dopo %d errori consecutivi",
                        host,
                        n,
                    )
            else:
                self._cb_consecutive[host] = 0

    # ------------------------------------------------------------------
    # Proxy fallback
    # ------------------------------------------------------------------

    PROXY_BLOCKED_STATUSES = {403, 407}

    @staticmethod
    def _resolve_fallback_proxies() -> dict[str, str] | None:
        """Read fallback proxy from ``BLOCKED_SOURCE_PROXY`` environment variable.

        GitHub Variable (org-level) già configurata in
        ``dataciviclab/dataset-incubator`` settings.
        """
        url = os.environ.get("BLOCKED_SOURCE_PROXY")
        if not url:
            return None
        return {"http": url, "https": url}

    # ------------------------------------------------------------------
    # Generic retry loop
    # ------------------------------------------------------------------

    def _execute(
        self,
        method_name: str,
        url: str,
        request_fn: Callable[..., requests.Response],
        ssl_fallback_fn: Callable[..., HttpResult],
        effective_retries: int,
        **kwargs: Any,
    ) -> HttpResult:
        """Execute an HTTP request with retry, backoff, and SSL fallback.

        If the server returns 403/407 and ``BLOCKED_SOURCE_PROXY`` is set,
        a single extra attempt is made through the proxy — independent of
        the retry budget.

        Args:
            method_name: HTTP method name for logging (e.g. "HEAD", "GET").
            url: The URL to request.
            request_fn: Callable that performs the primary request.
            ssl_fallback_fn: Callable that performs the SSL fallback request.
            effective_retries: Number of total attempts (>= 1).
            **kwargs: Passed to request_fn.

        Returns:
            HttpResult with response or err.

        """
        last_err: Exception | None = None
        primary_exc: requests.exceptions.SSLError | None = None
        fallback_proxies = self._resolve_fallback_proxies()
        blocked_status: int | None = None

        for attempt in range(effective_retries):
            if attempt > 0:
                delay = self.retry_backoff * (2 ** (attempt - 1))
                if self.retry_jitter > 0:
                    delay *= random.uniform(1 - self.retry_jitter, 1 + self.retry_jitter)
                time.sleep(delay)

            try:
                response = request_fn(url, timeout=self.timeout, **kwargs)
            except requests.exceptions.SSLError as exc:
                primary_exc = exc
                logger.warning(
                    "SSL error on %s %s (attempt %d) — fallback",
                    method_name,
                    url,
                    attempt + 1,
                )
                urllib3.disable_warnings(category=InsecureRequestWarning)
                return ssl_fallback_fn(url, primary_exc, kwargs)

            except requests.exceptions.RequestException as exc:
                last_err = exc
                if attempt < effective_retries - 1:
                    continue
                # Se è l'ultimo tentativo e il proxy è configurato, ritenta via proxy
                # (copre timeout/connection error su siti che bloccano GHA — es. MUR, ISTAT)
                if fallback_proxies:
                    logger.info(
                        "Ultimo tentativo fallito per %s %s — riprovo con fallback proxy",
                        method_name,
                        url,
                    )
                    try:
                        kwargs["proxies"] = fallback_proxies
                        response = request_fn(url, timeout=self.timeout, **kwargs)
                        return HttpResult(response=response, err=None)
                    except requests.exceptions.RequestException:
                        pass  # fallisce anche col proxy → errore originale sotto
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)
            except Exception as exc:
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)

            # 429 Retry-After
            if response.status_code == 429 and attempt < effective_retries - 1:
                retry_after = self._parse_retry_after(response)
                if retry_after is not None:
                    time.sleep(min(retry_after, 300))
                last_err = Exception("HTTP 429")
                continue

            # 5xx retry
            if response.status_code >= 500 and attempt < effective_retries - 1:
                last_err = Exception(f"HTTP {response.status_code}")
                continue

            # 403/407 — save status for proxy fallback (does NOT consume retry)
            if response.status_code in self.PROXY_BLOCKED_STATUSES and fallback_proxies:
                blocked_status = response.status_code
                break  # exit retry loop → proxy fallback below

            return HttpResult(response=response, err=None, ssl_fallback_used=None)

        # Proxy fallback: one extra attempt outside the retry budget
        if blocked_status is not None and fallback_proxies:
            logger.info(
                "HTTP %s on %s %s — retrying with fallback proxy",
                blocked_status,
                method_name,
                url,
            )
            try:
                kwargs["proxies"] = fallback_proxies
                response = request_fn(url, timeout=self.timeout, **kwargs)
                return HttpResult(response=response, err=None)
            except requests.exceptions.RequestException as exc:
                return HttpResult(response=None, err=exc, ssl_fallback_used=False)

        return HttpResult(
            response=None,
            err=last_err or Exception("Max retries exhausted"),
            ssl_fallback_used=False,
        )

    # ------------------------------------------------------------------
    # HEAD
    # ------------------------------------------------------------------

    def head(self, url: str, **kwargs: Any) -> HttpResult:
        """Send HEAD request with SSL fallback, retry, backoff and 429 handling.

        HEAD is idempotent — retries on 5xx, 429, and connection errors.

        Args:
            url: The URL to request.
            **kwargs: Passed to requests.head().

        Returns:
            HttpResult with response or err.

        """
        # Circuit breaker check
        if self._circuit_should_block(url):
            host = self._netloc(url)
            logger.warning("HEAD %s — skipped (circuit open for %s)", url, host)
            return HttpResult(
                response=None,
                err=CircuitOpenError(f"Circuit open for host {host}"),
                ssl_fallback_used=None,
            )

        headers = kwargs.pop("headers", None) or {}
        headers.setdefault("User-Agent", self.user_agent)
        kwargs["headers"] = headers
        kwargs.setdefault("allow_redirects", True)

        result = self._execute(
            "HEAD",
            url,
            lambda u, **kw: requests.head(u, **kw),
            lambda u, exc, kw: self._head_ssl_fallback(u, exc, kw),
            max(1, self.max_retries),
            **kwargs,
        )
        self._circuit_after_result(url, result)
        return result

    def _head_ssl_fallback(
        self,
        url: str,
        primary_exc: requests.exceptions.SSLError,
        kwargs: dict[str, Any],
    ) -> HttpResult:
        """SSL fallback for HEAD — verify=False poi catena completa."""
        # Filtra sia headers sia verify: verify viene forzato a False qui sotto,
        # passarlo anche via **fallback_kwargs causerebbe TypeError
        # ("got multiple values for keyword argument 'verify'").
        fallback_kwargs = {k: v for k, v in kwargs.items() if k not in ("headers", "verify")}
        fallback_kwargs.setdefault("allow_redirects", True)
        _head_fb: Exception | None = None
        try:
            response = self._session.head(
                url,
                timeout=self.timeout,
                verify=False,
                **fallback_kwargs,
            )
            return HttpResult(response=response, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as _exc:
            _head_fb = _exc
            logger.warning(
                "Fallback HEAD (verify=False) fallito per %s: %s — catena",
                url,
                _exc,
            )
        attempts_before: list[Exception] = [_head_fb] if _head_fb else []
        return self._run_fallback_chain(url, "HEAD", fallback_kwargs, primary_exc, attempts_before)

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get(self, url: str, **kwargs: Any) -> HttpResult:
        """Send GET request with SSL fallback, retry, backoff and 429 handling.

        Args:
            url: The URL to request.
            **kwargs: Passed to requests.get().

        Returns:
            HttpResult with response or err.

        """
        # Circuit breaker check
        if self._circuit_should_block(url):
            host = self._netloc(url)
            logger.warning("GET %s — skipped (circuit open for %s)", url, host)
            return HttpResult(
                response=None,
                err=CircuitOpenError(f"Circuit open for host {host}"),
                ssl_fallback_used=None,
            )

        headers = kwargs.pop("headers", None) or {}
        headers.setdefault("User-Agent", self.user_agent)
        kwargs["headers"] = headers

        result = self._execute(
            "GET",
            url,
            lambda u, **kw: requests.get(u, **kw),
            lambda u, exc, kw: self._get_ssl_fallback(u, exc, kw),
            max(1, self.max_retries),
            **kwargs,
        )
        self._circuit_after_result(url, result)
        return result

    def _get_ssl_fallback(
        self,
        url: str,
        primary_exc: requests.exceptions.SSLError,
        kwargs: dict[str, Any],
    ) -> HttpResult:
        """SSL fallback for GET — verify=False poi catena completa."""
        fallback_kwargs = {k: v for k, v in kwargs.items() if k != "verify"}
        # Tentativo 1: verify=False
        _get_fb: Exception | None = None
        try:
            response = self._session.get(
                url,
                timeout=self.timeout,
                verify=False,
                **fallback_kwargs,
            )
            return HttpResult(response=response, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as _exc:
            _get_fb = _exc
            logger.warning(
                "Fallback GET (verify=False) fallito per %s: %s — catena",
                url,
                _exc,
            )
        attempts_before: list[Exception] = [_get_fb] if _get_fb else []
        return self._run_fallback_chain(url, "GET", fallback_kwargs, primary_exc, attempts_before)

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        *,
        retries: int = 0,
        **kwargs: Any,
    ) -> HttpResult:
        """Send POST request with SSL fallback (opt-in retry, backoff, 429).

        Unlike GET/HEAD, retry is **opt-in** (default 0) because POST
        is not idempotent. Pass ``retries=N`` for idempotent endpoints
        (file download, SPARQL query).

        Args:
            url: The URL to request.
            data: Form-encoded body.
            json: JSON-serializable body.
            retries: Number of retry attempts (default 0).
            **kwargs: Passed to ``requests.post()``.

        Returns:
            HttpResult with response or err.

        """
        # Circuit breaker check
        if self._circuit_should_block(url):
            host = self._netloc(url)
            logger.warning("POST %s — skipped (circuit open for %s)", url, host)
            return HttpResult(
                response=None,
                err=CircuitOpenError(f"Circuit open for host {host}"),
                ssl_fallback_used=None,
            )

        headers = kwargs.pop("headers", None) or {}
        headers.setdefault("User-Agent", self.user_agent)
        kwargs["headers"] = headers

        result = self._execute(
            "POST",
            url,
            lambda u, **kw: requests.post(u, data=data, json=json, **kw),
            lambda u, exc, kw: self._post_ssl_fallback(u, data, json, exc, kw),
            max(1, retries),
            **kwargs,
        )
        self._circuit_after_result(url, result)
        return result

    def _post_ssl_fallback(
        self,
        url: str,
        data: Any,
        json: Any,
        primary_exc: requests.exceptions.SSLError,
        kwargs: dict[str, Any],
    ) -> HttpResult:
        """SSL fallback for POST — verify=False poi TLS 1.2 poi proxy."""
        fallback_kwargs = {k: v for k, v in kwargs.items() if k != "verify"}
        # Tentativo 1: verify=False
        _post_fb: Exception | None = None
        try:
            response = self._session.post(
                url,
                data=data,
                json=json,
                timeout=self.timeout,
                verify=False,
                **fallback_kwargs,
            )
            return HttpResult(response=response, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as _exc:
            _post_fb = _exc
            logger.warning(
                "Fallback POST (verify=False) fallito per %s: %s — provo TLS 1.2",
                url,
                _exc,
            )
        # Tentativo 2: TLS 1.2
        attempts_before: list[Exception] = [_post_fb] if _post_fb else []
        try:
            session = self._tls12_session()
            resp = session.post(url, data=data, json=json, timeout=self.timeout, **fallback_kwargs)
            session.close()
            return HttpResult(response=resp, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as tls12_exc:
            logger.warning("Fallback POST (TLS 1.2) fallito per %s: %s", url, tls12_exc)
            attempts_before.append(tls12_exc)
        # Tentativo 3: TLS 1.2 + proxy
        proxies = self._resolve_fallback_proxies()
        if proxies:
            try:
                session = self._tls12_session()
                resp = session.post(
                    url,
                    data=data,
                    json=json,
                    timeout=self.timeout,
                    proxies=proxies,
                    **fallback_kwargs,
                )
                session.close()
                return HttpResult(response=resp, err=None, ssl_fallback_used=True)
            except requests.exceptions.RequestException as proxy_exc:
                logger.warning("Fallback POST (TLS 1.2 + proxy) fallito per %s", url)
                attempts_before.append(proxy_exc)
        # Tentativo 4: curl -k (solo GET-like, per POST usiamo solo requests)
        return HttpResult(
            response=None,
            err=HttpFallbackError(
                primary_error=primary_exc,
                fallback_error=attempts_before[-1],
            ),
            ssl_fallback_used=False,
        )

    # ------------------------------------------------------------------
    # Fallback extra: curl e urllib
    # ------------------------------------------------------------------

    _CURL_TIMEOUT_MARGIN = 10

    def _tls12_session(self) -> requests.Session:
        """Create a session with TLS 1.2 forced."""
        session = requests.Session()
        session.mount("https://", _Tls12Adapter())
        session.headers["User-Agent"] = self.user_agent
        return session

    def _requests_tls12_proxy(self, method: str, url: str, **kwargs: Any) -> HttpResult:
        """GET/HEAD via TLS 1.2 + proxy."""
        proxies = self._resolve_fallback_proxies()
        if not proxies:
            return HttpResult(
                response=None,
                err=Exception("Nessun proxy configurato"),
                ssl_fallback_used=False,
            )
        try:
            session = self._tls12_session()
            fn = getattr(session, method.lower())
            resp = fn(url, timeout=self.timeout, proxies=proxies, **kwargs)
            session.close()
            return HttpResult(response=resp, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as exc:
            return HttpResult(response=None, err=exc, ssl_fallback_used=False)

    def _via_curl(self, url: str, timeout: int | None = None) -> HttpResult:
        """Download via curl -k -L."""
        curl = shutil.which("curl")
        if not curl:
            return HttpResult(
                response=None,
                err=Exception("curl non disponibile"),
                ssl_fallback_used=False,
            )
        t = timeout or self._default_timeout()
        try:
            ua = _rand_ua()
            result = subprocess.run(
                [curl, "-k", "-sS", "-L", "--max-time", str(t), "-H", f"User-Agent: {ua}", url],
                capture_output=True,
                check=False,
                timeout=t + self._CURL_TIMEOUT_MARGIN,
            )
            if result.returncode == 0 and len(result.stdout) > 0:
                resp = _SimpleResponse(result.stdout, url=url)
                return HttpResult(response=resp, err=None, ssl_fallback_used=True)
            stderr_text = result.stderr.decode("utf-8", errors="replace")[:200]
            err_msg = stderr_text or f"exit code {result.returncode}"
            return HttpResult(
                response=None,
                err=Exception(f"curl: {err_msg}"),
                ssl_fallback_used=False,
            )
        except Exception as exc:
            return HttpResult(response=None, err=exc, ssl_fallback_used=False)

    def _via_urllib(self, url: str, timeout: int | None = None) -> HttpResult:
        """Download via urllib + TLSv1.2 + User-Agent random."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        t = timeout or self._default_timeout()
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": _rand_ua(),
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                with urllib.request.urlopen(req, timeout=t, context=ctx) as r:
                    content = r.read()
                    resp = _SimpleResponse(content, url=url)
                    return HttpResult(response=resp, err=None, ssl_fallback_used=True)
            except Exception as exc:
                last_err = exc
                if attempt < 2:
                    time.sleep((attempt + 1) * 3)
        return HttpResult(
            response=None,
            err=last_err or Exception("urllib exhausted"),
            ssl_fallback_used=False,
        )

    @staticmethod
    def _default_timeout() -> int:
        return 120

    # ------------------------------------------------------------------
    # Catena di fallback condivisa per GET/HEAD
    # ------------------------------------------------------------------

    def _run_fallback_chain(
        self,
        url: str,
        method: str,
        kwargs: dict[str, Any],
        primary_exc: Exception,
        attempts_before: list[Exception],
    ) -> HttpResult:
        """Esegue la catena di fallback per GET/HEAD.

        Ordine:
          1. requests verify=False (gia' tentato prima, non replicato qui)
          2. requests TLS 1.2
          3. requests TLS 1.2 + proxy
          4. curl -k
          5. urllib TLS 1.2
        """
        fallback_kwargs = {k: v for k, v in kwargs.items() if k != "verify"}

        # --- 2: TLS 1.2 ---
        try:
            session = self._tls12_session()
            fn = getattr(session, method.lower())
            resp = fn(url, timeout=self.timeout, **fallback_kwargs)
            session.close()
            return HttpResult(response=resp, err=None, ssl_fallback_used=True)
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Fallback %s (TLS 1.2) fallito per %s: %s",
                method,
                url,
                exc,
            )
            attempts_before.append(exc)

        # --- 3: TLS 1.2 + proxy ---
        result = self._requests_tls12_proxy(method, url, **fallback_kwargs)
        if result.is_ok:
            return result
        logger.warning(
            "Fallback %s (TLS 1.2 + proxy) fallito per %s",
            method,
            url,
        )
        if result.err:
            attempts_before.append(result.err)

        # --- 4: curl -k ---
        result = self._via_curl(url)
        if result.is_ok:
            return result
        logger.warning("Fallback %s (curl) fallito per %s", method, url)
        if result.err:
            attempts_before.append(result.err)

        # --- 5: urllib TLS 1.2 ---
        result = self._via_urllib(url)
        if result.is_ok:
            return result
        logger.warning("Fallback %s (urllib) fallito per %s", method, url)
        if result.err:
            attempts_before.append(result.err)

        return HttpResult(
            response=None,
            err=HttpFallbackError(
                primary_error=primary_exc,
                fallback_error=(
                    attempts_before[-1]
                    if attempts_before
                    else Exception("Tutti i fallback esauriti")
                ),
            ),
            ssl_fallback_used=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_retry_after(response: requests.Response) -> float | None:
        """Parse Retry-After header, return seconds to wait or None.

        Supports both integer seconds (Retry-After: 120) and
        HTTP-date format (Retry-After: Wed, 21 Oct 2026 07:28:00 GMT).
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after is None:
            return None
        # Try integer seconds first
        try:
            return float(retry_after)
        except ValueError:
            pass
        # Try HTTP-date format
        try:
            parsed = parsedate_to_datetime(retry_after)
            now = datetime.datetime.now(datetime.UTC)
            delta = (parsed - now).total_seconds()
            return max(0.0, delta)
        except Exception:
            return None
