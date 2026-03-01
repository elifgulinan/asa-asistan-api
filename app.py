"""
ASA Asistan Flask API — Mistral AI + çok sayfalı crawler + rakip karşılaştırma + AI Ads.
"""
import os
import logging
import requests
import re
import json
from flask import Flask, request, Response
from flask_cors import CORS
from crawler import scrape_seo

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
CORS(app)

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL = "open-mistral-7b"
MISTRAL_HOST = "https://api.mistral.ai/v1/chat/completions"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ok(data):
    return Response(json.dumps(data, ensure_ascii=False), mimetype='application/json')

def err(msg, code=400):
    return Response(json.dumps({"error": msg}, ensure_ascii=False), status=code, mimetype='application/json')


def call_mistral(prompt, system=None, max_tokens=1000):
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY ayarlanmamış")
    if not system:
        system = "Sen Türk KOBİ'lere SEO ve dijital pazarlama danışmanlığı yapan ASA Asistan'sın. Türkçe, kısa ve pratik yanıtlar ver."
    r = requests.post(
        MISTRAL_HOST,
        headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
        json={"model": MISTRAL_MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": 0.3},
        timeout=60
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def build_analysis_prompt(d):
    url = d.get("url", "")
    s = d.get("summary", {})
    if d.get("error"):
        return f"SEO analizi yap:\nURL: {url}\nHata: {d['error']}"
    issues = " | ".join([i['text'] for i in s.get("issues", [])]) or "Sorun yok"
    title = d.get("title") or "(yok)"
    meta = d.get("meta_description") or "(yok)"
    h1 = d.get("h1_tags", [])
    return (
        f"Web sitesi SEO analizi (Türkçe, kısa ve net):\n"
        f"URL: {url} | {s.get('total_pages_crawled',1)} sayfa\n"
        f"Başlık: {title[:80]}\nMeta: {meta[:100]}\n"
        f"H1: {len(h1)} | Kelime: {d.get('word_count',0)} | Mobil: {'Evet' if d.get('has_mobile_friendly') else 'Hayır'}\n"
        f"Sorunlar: {issues}\n\nGüçlü yönler ve 3 kritik öneri yaz. Son iki satırda:\nÖNERİLEN BAŞLIK: ...\nÖNERİLEN META: ..."
    )


def build_ads_prompt(d):
    url = d.get("url", "")
    title = d.get("title") or ""
    h1 = d.get("h1_tags", [])
    h2 = d.get("h2_tags", [])
    ctx = ", ".join((h1 + h2)[:4]) if (h1 + h2) else title[:60]
    return (
        f"Site: {url}\nKonu: {ctx[:100]}\n\n"
        "Ornek format:\n"
        "KEYWORDS: kelime1, kelime2, kelime3, kelime4, kelime5\n"
        "HEADLINES: baslik1 | baslik2 | baslik3\n"
        "DESCRIPTIONS: aciklama1 | aciklama2\n"
        "NEGATIVE: negatif1, negatif2, negatif3\n\n"
        "Simdi bu site icin ayni formatta Turkce yaz. Sadece 4 satir yaz, baska hicbir sey ekleme:"
    )


def parse_ads(raw):
    def ex(label, sep):
        m = re.search(rf'^{label}:\s*(.+)$', raw, re.MULTILINE | re.IGNORECASE)
        if not m:
            return []
        items = [x.strip().strip('*').strip() for x in m.group(1).split(sep) if x.strip().strip('*').strip()]
        return items
    return {
        "keywords": [{"keyword": k, "intent": "ticari", "priority": "orta"} for k in ex("KEYWORDS", ",")],
        "ad_headlines": ex("HEADLINES", "|"),
        "ad_descriptions": ex("DESCRIPTIONS", "|"),
        "negative_keywords": ex("NEGATIVE", ",")
    }


def build_comparison_prompt(site, rivals):
    def fmt(d):
        s = d.get("summary", {})
        return f"Başlık:{'Var' if d.get('title') else 'Yok'} Meta:{'Var' if d.get('meta_description') else 'Yok'} Kelime:{d.get('word_count',0)} Mobil:{'E' if d.get('has_mobile_friendly') else 'H'}"
    rival_text = "".join([f"Rakip {i+1} ({r.get('url','')[:30]}): {fmt(r)}\n" for i, r in enumerate(rivals)])
    return f"Karşılaştırma (Türkçe, kısa):\nSite ({site.get('url','')[:30]}): {fmt(site)}\n{rival_text}\n1) Önde olduğun alanlar\n2) Geride olduğun alanlar\n3) En hızlı 3 kazanım"


@app.route("/", methods=["GET"])
def index():
    return "ASA Asistan API çalışıyor"


@app.route("/api/analyze", methods=["POST"])
def analyze():
    if not request.is_json:
        return err("Content-Type: application/json gerekli")
    data = request.get_json()
    url = (data.get("url") or "").strip()
    if not url:
        return err('"url" boş olamaz')
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        crawler_data = scrape_seo(url)
    except Exception as e:
        return err(f"Crawler hatası: {e}", 500)
    try:
        ai_analysis = call_mistral(build_analysis_prompt(crawler_data))
    except Exception as e:
        return ok({"url": url, "crawler_data": crawler_data, "ai_analysis": None, "error": str(e)})
    return ok({"url": url, "crawler_data": crawler_data, "ai_analysis": ai_analysis})


@app.route("/api/ads", methods=["POST"])
def ads():
    if not request.is_json:
        return err("Content-Type: application/json gerekli")
    data = request.get_json()
    url = (data.get("url") or "").strip()
    crawler_data = data.get("crawler_data")
    if not url:
        return err('"url" boş olamaz')
    if not crawler_data:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            crawler_data = scrape_seo(url)
        except Exception as e:
            return err(f"Crawler hatası: {e}", 500)
    try:
        raw = call_mistral(build_ads_prompt(crawler_data), system="Sen Google Ads uzmanisın. Sadece istenen 4 satir formatta yaz, baska hicbir sey ekleme. Turkce kelimeler kullan.", max_tokens=200)
        ads_data = parse_ads(raw)
    except Exception:
        ads_data = {"keywords": [], "ad_headlines": [], "ad_descriptions": [], "negative_keywords": []}
    return ok({"url": url, "ads": ads_data})


@app.route("/api/compare", methods=["POST"])
def compare():
    if not request.is_json:
        return err("Content-Type: application/json gerekli")
    data = request.get_json()
    url = (data.get("url") or "").strip()
    rivals = data.get("rivals") or []
    if not url:
        return err('"url" boş olamaz')
    if not rivals:
        return err('En az 1 rakip URL gerekli')
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        site_data = scrape_seo(url)
    except Exception as e:
        return err(f"Site tarama hatası: {e}", 500)
    rival_data = []
    for r_url in rivals:
        r_url = r_url.strip()
        if not r_url:
            continue
        if not r_url.startswith(("http://", "https://")):
            r_url = "https://" + r_url
        try:
            rival_data.append(scrape_seo(r_url))
        except Exception as e:
            rival_data.append({"url": r_url, "error": str(e)})
    try:
        comparison = call_mistral(build_comparison_prompt(site_data, rival_data))
    except Exception as e:
        return ok({"site": site_data, "rivals": rival_data, "comparison": None, "error": str(e)})
    return ok({"site": site_data, "rivals": rival_data, "comparison": comparison})


@app.errorhandler(404)
def not_found(e):
    return err("Endpoint bulunamadı", 404)

@app.errorhandler(500)
def server_error(e):
    return err("Sunucu hatası", 500)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
