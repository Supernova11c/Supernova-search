"""Polite, bounded crawler for public HTTP(S) pages."""

from __future__ import annotations

import ipaddress
import socket
import time
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


class Crawler:
    def __init__(self, index, max_pages=100, max_depth=2, delay=1.0, timeout=10):
        self.index = index
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "SupernovaSearchBot/1.0 (+https://github.com/Supernova11c/Supernova-search; educational crawler)"})
        self.robot_cache = {}
        self.host_last_request = {}

    @staticmethod
    def _normalize(url):
        parsed = urlparse(urldefrag(url)[0])
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        path = parsed.path or "/"
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))

    @staticmethod
    def _public_host(host):
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        except (socket.gaierror, OSError):
            return False
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)

    def _allowed_by_robots(self, url):
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robot_cache:
            parser = RobotFileParser()
            robots_url = origin + "/robots.txt"
            try:
                response = self.session.get(robots_url, timeout=self.timeout, allow_redirects=False)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:
                    # If robots.txt cannot be retrieved, do not crawl this host.
                    parser.parse(["User-agent: *", "Disallow: /"])
            except requests.RequestException:
                parser.parse(["User-agent: *", "Disallow: /"])
            self.robot_cache[origin] = parser
        return self.robot_cache[origin].can_fetch(self.session.headers["User-Agent"], url)

    def _fetch(self, url):
        host = urlparse(url).hostname
        wait = self.delay - (time.monotonic() - self.host_last_request.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self.host_last_request[host] = time.monotonic()
        response = self.session.get(url, timeout=self.timeout, allow_redirects=False, stream=True)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            return None, urljoin(url, location) if location else None
        content_type = response.headers.get("Content-Type", "").lower()
        if response.status_code != 200 or "text/html" not in content_type:
            response.close()
            return None, None
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > 5_000_000:
            response.close()
            return None, None
        body = response.raw.read(5_000_001, decode_content=True)
        response.close()
        if len(body) > 5_000_000:
            return None, None
        return body, None

    def crawl(self, seeds):
        allowed_hosts = set()
        queue = deque()
        for seed in seeds:
            normalized = self._normalize(seed)
            if normalized:
                host = urlparse(normalized).hostname
                allowed_hosts.add(host)
                queue.append((normalized, 0, host))

        visited = set()
        indexed = 0
        while queue and indexed < self.max_pages:
            url, depth, seed_host = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            parsed = urlparse(url)
            if parsed.hostname != seed_host or not self._public_host(parsed.hostname):
                continue
            try:
                if not self._allowed_by_robots(url):
                    continue
                body, redirect = self._fetch(url)
            except (requests.RequestException, ValueError, OSError):
                continue
            if redirect:
                normalized = self._normalize(redirect)
                if normalized and urlparse(normalized).hostname == seed_host:
                    queue.appendleft((normalized, depth, seed_host))
                continue
            if not body:
                continue
            soup = BeautifulSoup(body, "html.parser")
            for element in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
                element.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            text = soup.get_text(" ", strip=True)
            if text:
                self.index.add_document(url, title, text)
                indexed += 1
            if depth >= self.max_depth:
                continue
            for link in soup.find_all("a", href=True):
                target = self._normalize(urljoin(url, link["href"]))
                if target and urlparse(target).hostname == seed_host and target not in visited:
                    queue.append((target, depth + 1, seed_host))
        return indexed
