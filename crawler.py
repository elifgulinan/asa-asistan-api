"""
ASA Asistan Crawler — çok sayfalı SEO tarayıcı, encoding fix dahil.
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
MAX_PAGES = 5
REQUEST_TIMEOUT = 15


def fix_encoding(text):
    if not text:
        return text
    try:
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def get_soup(url):
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    content_type = resp.headers.get('content-type', '').lower()
    if 'charset=' in content_type:
        charset = content_type.split('charset=')[-1].strip().split(';')[0].strip()
        try:
            resp.encoding = charset
        except Exception:
            resp.encoding = resp.apparent_encoding or 'utf-8'
    else:
        resp.encoding = resp.apparent_encoding or 'utf-8'
    return BeautifulSoup(resp.text, "html.parser"), resp.status_code


def get_internal_links(soup, base_url):
    base_domain = urlparse(base_url).netloc
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:")):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        clean_url = parsed._replace(fragment="").geturl()
        if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
            links.add(clean_url.rstrip("/"))
    return links


def safe_text(tag):
    if not tag:
        return None
    text = tag.get_text(strip=True) if hasattr(tag, 'get_text') else str(tag)
    try:
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def scrape_page(url):
    try:
        soup, status = get_soup(url)

        title_tag = soup.find("title")
        title = safe_text(title_tag)

        meta_desc = soup.find("meta", attrs={"name": "description"}) or \
                    soup.find("meta", attrs={"property": "og:description"})
        meta_description = meta_desc.get("content", "").strip() if meta_desc else None
        if meta_description:
            try:
                meta_description = meta_description.encode('latin-1').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        og_title_tag = soup.find("meta", attrs={"property": "og:title"})
        og_title = og_title_tag.get("content", "").strip() if og_title_tag else None

        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        canonical = canonical_tag.get("href", "").strip() if canonical_tag else None

        h1_tags = [safe_text(h) for h in soup.find_all("h1")]
        h2_tags = [safe_text(h) for h in soup.find_all("h2")]
        h3_tags = [safe_text(h) for h in soup.find_all("h3")]

        body = soup.find("body")
        word_count = len(body.get_text(separator=" ").split()) if body else 0

        viewport = soup.find("meta", attrs={"name": "viewport"})
        has_mobile_friendly = bool(viewport and "width=device-width" in viewport.get("content", "").lower())

        images = soup.find_all("img")
        images_without_alt = sum(1 for img in images if not img.get("alt", "").strip())

        internal_links = get_internal_links(soup, url)

        return {
            "url": url, "status_code": status,
            "title": title, "meta_description": meta_description,
            "og_title": og_title, "canonical": canonical,
            "h1_tags": h1_tags, "h2_tags": h2_tags, "h3_tags": h3_tags,
            "word_count": word_count, "has_mobile_friendly": has_mobile_friendly,
            "images_without_alt": images_without_alt,
            "internal_links": list(internal_links),
            "internal_links_count": len(internal_links),
            "error": None
        }
    except Exception as e:
        return {
            "url": url, "status_code": None,
            "title": None, "meta_description": None,
            "og_title": None, "canonical": None,
            "h1_tags": [], "h2_tags": [], "h3_tags": [],
            "word_count": 0, "has_mobile_friendly": False,
            "images_without_alt": 0, "internal_links": [],
            "internal_links_count": 0, "error": str(e)
        }


def build_summary(pages):
    successful = [p for p in pages if not p.get("error")]
    error_pages_list = [p for p in pages if p.get("error")]

    total_words = sum(p.get("word_count", 0) for p in successful)
    avg_word_count = round(total_words / len(successful)) if successful else 0
    total_images_without_alt = sum(p.get("images_without_alt", 0) for p in successful)

    pages_missing_title = [p["url"] for p in successful if not p.get("title")]
    pages_missing_meta = [p["url"] for p in successful if not p.get("meta_description")]
    pages_missing_h1 = [p["url"] for p in successful if not p.get("h1_tags")]
    pages_with_multiple_h1 = [p["url"] for p in successful if len(p.get("h1_tags", [])) > 1]
    pages_not_mobile_friendly = [p["url"] for p in successful if not p.get("has_mobile_friendly")]

    issues = []
    if pages_with_multiple_h1:
        issues.append({"level": "red", "text": f"{len(pages_with_multiple_h1)} sayfada birden fazla H1 var (SEO hatası)", "pages": pages_with_multiple_h1})
    if total_images_without_alt > 0:
        issues.append({"level": "orange", "text": f"Toplam {total_images_without_alt} görselde alt etiketi eksik", "pages": []})
    if pages_missing_title:
        issues.append({"level": "red", "text": f"{len(pages_missing_title)} sayfada başlık (title) eksik", "pages": pages_missing_title})
    if pages_missing_meta:
        issues.append({"level": "orange", "text": f"{len(pages_missing_meta)} sayfada meta açıklama eksik", "pages": pages_missing_meta})
    if pages_missing_h1:
        issues.append({"level": "orange", "text": f"{len(pages_missing_h1)} sayfada H1 başlığı yok", "pages": pages_missing_h1})
    if pages_not_mobile_friendly:
        issues.append({"level": "red", "text": f"{len(pages_not_mobile_friendly)} sayfa mobil uyumlu değil", "pages": pages_not_mobile_friendly})
    if avg_word_count < 300:
        issues.append({"level": "orange", "text": f"Ortalama sayfa içeriği çok az ({avg_word_count} kelime)", "pages": []})

    return {
        "total_pages_crawled": len(pages),
        "successful_pages": len(successful),
        "error_pages": len(error_pages_list),
        "avg_word_count": avg_word_count,
        "total_images_without_alt": total_images_without_alt,
        "pages_missing_title": pages_missing_title,
        "pages_missing_meta": pages_missing_meta,
        "pages_missing_h1": pages_missing_h1,
        "pages_with_multiple_h1": pages_with_multiple_h1,
        "pages_not_mobile_friendly": pages_not_mobile_friendly,
        "issues": issues
    }


def scrape_seo(start_url):
    visited = set()
    to_visit = [start_url]
    pages = []

    while to_visit and len(pages) < MAX_PAGES:
        url = to_visit.pop(0)
        parsed = urlparse(url)
        clean_url = parsed._replace(fragment="").geturl().rstrip("/") or url
        if clean_url in visited:
            continue
        visited.add(clean_url)
        logger.info(f"Taranıyor: {clean_url}")
        page_data = scrape_page(clean_url)
        pages.append(page_data)
        if not page_data.get("error"):
            for link in page_data.get("internal_links", []):
                if link not in visited and link not in to_visit:
                    to_visit.append(link)

    summary = build_summary(pages)
    homepage = pages[0] if pages else {}

    return {
        "url": start_url,
        "title": homepage.get("title"),
        "meta_description": homepage.get("meta_description"),
        "h1_tags": homepage.get("h1_tags", []),
        "h2_tags": homepage.get("h2_tags", []),
        "h3_tags": homepage.get("h3_tags", []),
        "word_count": homepage.get("word_count", 0),
        "has_mobile_friendly": homepage.get("has_mobile_friendly", False),
        "images_without_alt": homepage.get("images_without_alt", 0),
        "canonical": homepage.get("canonical"),
        "og_title": homepage.get("og_title"),
        "pages": pages,
        "summary": summary,
        "error": homepage.get("error")
    }
