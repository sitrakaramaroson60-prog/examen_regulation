"""Client HTTP défensif pour la collecte web.

Garanties : schéma http(s) uniquement, ports standards, liste blanche de domaines, refus des adresses
privées/internes (SSRF), redirections contrôlées une à une, délai d'attente, taille plafonnée,
respect de robots.txt, aucune authentification ni contournement de protection.

Limite connue : la résolution DNS est vérifiée avant la requête mais n'est pas « épinglée » ;
un attaquant contrôlant le DNS d'un domaine autorisé pourrait tenter un rebinding. En production,
exécutez le worker dans un réseau sans accès aux ressources internes (filtrage de sortie).
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from django.conf import settings

ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "text/csv", "application/json", "application/xml", "text/xml")


class ScrapingBlocked(Exception):
    """Requête refusée par la politique de sécurité."""


class ScrapingNotConfigured(ScrapingBlocked):
    pass


def allowed_domains():
    return [d.lower().lstrip(".") for d in settings.SCRAPING_ALLOWED_DOMAINS]


def is_public_ip(ip_str):
    ip = ipaddress.ip_address(ip_str)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def host_allowed(host):
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in allowed_domains())


def check_url(url):
    domains = allowed_domains()
    if not domains:
        raise ScrapingNotConfigured("Le web scraping n'est pas configuré (aucun domaine autorisé).")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ScrapingBlocked("Schéma non autorisé.")
    if parts.username or parts.password:
        raise ScrapingBlocked("Identifiants dans l'URL interdits.")
    host = parts.hostname
    if not host:
        raise ScrapingBlocked("URL sans hôte.")
    default_port = 443 if parts.scheme == "https" else 80
    if parts.port not in (None, default_port):
        raise ScrapingBlocked("Port non autorisé.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ScrapingBlocked("Les adresses IP littérales sont interdites.")
    if not host_allowed(host):
        raise ScrapingBlocked(f"Domaine non autorisé : {host}.")
    try:
        infos = socket.getaddrinfo(host, parts.port or default_port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ScrapingBlocked("Résolution DNS impossible.")
    for info in infos:
        if not is_public_ip(info[4][0]):
            raise ScrapingBlocked("Destination interne ou privée refusée.")
    return parts


def _get(url, session):
    return session.get(url, allow_redirects=False, timeout=settings.SCRAPING_TIMEOUT_SECONDS, stream=True, headers={"User-Agent": settings.SCRAPING_USER_AGENT, "Accept": ", ".join(ALLOWED_CONTENT_TYPES)})


def robots_allows(url, session):
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    check_url(robots_url)
    try:
        r = _get(robots_url, session)
    except requests.RequestException:
        raise ScrapingBlocked("robots.txt inaccessible : collecte suspendue par prudence.")
    if r.status_code in (404, 410):
        return True
    if r.status_code != 200:
        raise ScrapingBlocked(f"robots.txt a répondu {r.status_code} : collecte suspendue.")
    body = r.raw.read(200_000, decode_content=True).decode("utf-8", "replace")
    rp = RobotFileParser()
    rp.parse(body.splitlines())
    return rp.can_fetch(settings.SCRAPING_USER_AGENT, url)


def fetch(url, session=None):
    """Retourne (final_url, status, content_type, bytes). Lève ScrapingBlocked si la politique l'interdit."""
    session = session or requests.Session()
    session.trust_env = False  # ignore les proxies d'environnement
    check_url(url)
    if not robots_allows(url, session):
        raise ScrapingBlocked("Collecte interdite par robots.txt.")
    current = url
    for _ in range(settings.SCRAPING_MAX_REDIRECTS + 1):
        check_url(current)
        resp = _get(current, session)
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location:
                raise ScrapingBlocked("Redirection invalide.")
            current = urljoin(current, location)
            continue
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if ctype not in ALLOWED_CONTENT_TYPES:
            raise ScrapingBlocked(f"Type de contenu non autorisé : {ctype or 'inconnu'}.")
        length = resp.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > settings.SCRAPING_MAX_BYTES:
            raise ScrapingBlocked("Contenu trop volumineux.")
        data = resp.raw.read(settings.SCRAPING_MAX_BYTES + 1, decode_content=True)
        if len(data) > settings.SCRAPING_MAX_BYTES:
            raise ScrapingBlocked("Contenu trop volumineux.")
        return current, resp.status_code, ctype, data
    raise ScrapingBlocked("Trop de redirections.")
