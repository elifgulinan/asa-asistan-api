"""
SEO data crawler - scrapes basic SEO metrics from any website.
Çok sayfalı tarama: anasayfadan iç linkleri keşfeder, ilk 5 sayfayı tarar.
robots.txt kontrolü dahil.
"""
import json
import re
import time
from typing import Any
from urllib.parse import urlparse, urljoin, urlunparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

REQUEST_DELAY = 1.0
TIMEOUT = 15
MAX_PAGES = 5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip('/') or '/', parsed.params, parsed.query, ''))


def check_robots(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        return True, robots_url
    return rp.can_fetch(USER_AGENT, url), robots_url


def get_internal_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    links = []
    skip_ext = ('.jpg','.jpeg','.png','.gif','.pdf','.zip','.mp4','.svg','.webp','.ico','.xml','.css','.js')

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()
        if not href or href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc != base_domain:
            continue
        if parsed.scheme not in ('http', 'https'):
            continue
        if any(parsed.path.lower().endswith(ext) for ext in skip_ext):
            continue
        normalized = normalize_url(full_url)
        if normalized not in links:
            links.append(normalized)

    return links


def scrape_page(url: str, session: requests.Session) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": url,
        "title": None,
        "meta_description": None,
        "h1_tags": [],
        "h2_tags": [],
        "h3_tags": [],
        "word_count": 0,
        "has_mobile_friendly": False,
        "canonical": None,
        "og_title": None,
        "images_without_alt": 0,
        "internal_links_count": 0,
    }

    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        result["error"] = "Zaman aşımı"
        return result
    except requests.exceptions.ConnectionError as e:
        result["error"] = f"Bağlantı hatası: {str(e)[:100]}"
        return result
    except requests.exceptions.HTTPError as e:
        result["error"] = f"HTTP hatası: {e}"
        return result
    except requests.exceptions.RequestException as e:
        result["error"] = f"İstek hatası: {str(e)[:100]}"
        return result

    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("title")
    result["title"] = title_tag.get_text(strip=True) if title_tag else None

    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if meta_desc and meta_desc.get("content"):
        result["meta_description"] = meta_desc["content"].strip()

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        result["og_title"] = og_title["content"].strip()

    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        result["canonical"] = canonical["href"].strip()

    result["h1_tags"] = [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
    result["h2_tags"] = [h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)]
    result["h3_tags"] = [h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)]

    body = soup.find("body")
    if body:
        text = re.sub(r"\s+", " ", body.get_text(separator=" ", strip=True))
        result["word_count"] = len(text.split()) if text else 0

    viewport = soup.find("meta", attrs={"name": "viewport"})
    if viewport and viewport.get("content"):
        content = viewport["content"].lower()
        result["has_mobile_friendly"] = "width" in content and "user-scalable=no" not in content

    images = soup.find_all("img")
    result["images_without_alt"] = sum(1 for img in images if not img.get("alt", "").strip())

    parsed_base = urlparse(url)
    internal = [a for a in soup.find_all("a", href=True)
                if urlparse(urljoin(url, a["href"])).netloc == parsed_base.netloc]
    result["internal_links_count"] = len(internal)

    result["_internal_links"] = get_internal_links(soup, url)

    return result


def build_issues(missing_title, missing_meta, missing_h1, multiple_h1, non_mobile, images_no_alt, avg_words) -> list:
    issues = []
    if missing_title:
        issues.append({"level": "red", "text": f"{len(missing_title)} sayfada başlık (title) eksik", "pages": missing_title})
    if missing_meta:
        issues.append({"level": "red", "text": f"{len(missing_meta)} sayfada meta açıklama eksik", "pages": missing_meta})
    if multiple_h1:
        issues.append({"level": "orange", "text": f"{len(multiple_h1)} sayfada birden fazla H1 var (SEO hatası)", "pages": multiple_h1})
    if missing_h1:
        issues.append({"level": "orange", "text": f"{len(missing_h1)} sayfada H1 etiketi yok", "pages": missing_h1})
    if non_mobile:
        issues.append({"level": "red", "text": f"{len(non_mobile)} sayfa mobil uyumsuz", "pages": non_mobile})
    if images_no_alt > 0:
        issues.append({"level": "orange", "text": f"Toplam {images_no_alt} görselde alt etiketi eksik", "pages": []})
    if avg_words < 300:
        issues.append({"level": "orange", "text": f"Ortalama sayfa içeriği çok az ({avg_words} kelime)", "pages": []})
    return issues


def build_summary(pages: list, base_url: str, robots_url: str) -> dict:
    if not pages:
        return {}
    ok_pages = [p for p in pages if "error" not in p]
    missing_title = [p["url"] for p in ok_pages if not p.get("title")]
    missing_meta = [p["url"] for p in ok_pages if not p.get("meta_description")]
    missing_h1 = [p["url"] for p in ok_pages if not p.get("h1_tags")]
    multiple_h1 = [p["url"] for p in ok_pages if len(p.get("h1_tags", [])) > 1]
    non_mobile = [p["url"] for p in ok_pages if not p.get("has_mobile_friendly")]
    total_images_no_alt = sum(p.get("images_without_alt", 0) for p in ok_pages)
    avg_word_count = int(sum(p.get("word_count", 0) for p in ok_pages) / len(ok_pages)) if ok_pages else 0

    return {
        "total_pages_crawled": len(pages),
        "successful_pages": len(ok_pages),
        "error_pages": len(pages) - len(ok_pages),
        "avg_word_count": avg_word_count,
        "total_images_without_alt": total_images_no_alt,
        "pages_missing_title": missing_title,
        "pages_missing_meta": missing_meta,
        "pages_missing_h1": missing_h1,
        "pages_with_multiple_h1": multiple_h1,
        "pages_not_mobile_friendly": non_mobile,
        "issues": build_issues(missing_title, missing_meta, missing_h1, multiple_h1, non_mobile, total_images_no_alt, avg_word_count),
    }


def scrape_seo(url: str) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    base_url = normalize_url(url)
    allowed, robots_url = check_robots(base_url)

    if not allowed:
        return {
            "url": base_url,
            "robots_checked": True,
            "robots_url": robots_url,
            "error": f"robots.txt tarafından engellendi: {robots_url}",
            "pages": [],
            "summary": {}
        }

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    visited = set()
    to_visit = [base_url]
    pages = []

    while to_visit and len(pages) < MAX_PAGES:
        current_url = to_visit.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        page_data = scrape_page(current_url, session)
        internal_links = page_data.pop("_internal_links", [])
        pages.append(page_data)

        for link in internal_links:
            if link not in visited and link not in to_visit:
                to_visit.append(link)

    summary = build_summary(pages, base_url, robots_url)

    return {
        "url": base_url,
        "robots_checked": True,
        "robots_url": robots_url,
        "pages": pages,
        "summary": summary,
        "title": pages[0].get("title") if pages else None,
        "meta_description": pages[0].get("meta_description") if pages else None,
        "h1_tags": pages[0].get("h1_tags", []) if pages else [],
        "h2_tags": pages[0].get("h2_tags", []) if pages else [],
        "word_count": pages[0].get("word_count", 0) if pages else 0,
        "has_mobile_friendly": pages[0].get("has_mobile_friendly", False) if pages else False,
    }


def main() -> None:
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.example.com"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    data = scrape_seo(url)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
