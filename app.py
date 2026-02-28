"""
ASA Asistan Flask API — Mistral AI + çok sayfalı crawler + rakip karşılaştırma + AI Ads.
"""
import os
import logging
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from crawler import scrape_seo

app = Flask(__name__)
CORS(app)

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL = "open-mistral-7b"
MISTRAL_HOST = "https://api.mistral.ai/v1/chat/completions"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def call_mistral(prompt: str, system: str = None, max_tokens: int = 1000) -> str:
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY ayarlanmamış")
    if not system:
        system = "Sen Türk KOBİ'lere SEO ve dijital pazarlama danışmanlığı yapan ASA Asistan'sın. Türkçe, kısa ve pratik yanıtlar ver."
    try:
        r = requests.post(
            MISTRAL_HOST,
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MISTRAL_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7
            },
            timeout=60
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.Timeout:
        raise ValueError("Mistral yanıt vermedi (zaman aşımı)")
    except requests.exceptions.HTTPError as e:
        raise ValueError(f"Mistral HTTP hatası: {e}")
    except Exception as e:
        raise ValueError(f"Mistral hatası: {e}")


def build_analysis_prompt(crawler_data: dict) -> str:
    url = crawler_data.get("url", "")
    summary = crawler_data.get("summary", {})
    err = crawler_data.get("error")
    if err:
        return f"Bu site için SEO analizi yap (Türkçe, kısa):\nURL: {url}\nHata: {err}"
    issues = summary.get("issues", [])
    issues_text = " | ".join([i['text'] for i in issues]) or "Sorun yok"
    title = crawler_data.get("title") or "(yok)"
    meta = crawler_data.get("meta_description") or "(yok)"
    h1 = crawler_data.get("h1_tags", [])
    words = crawler_data.get("word_count", 0)
    mobile = crawler_data.get("has_mobile_friendly", False)
    pages = summary.get("total_pages_crawled", 1)
    avg_words = summary.get("avg_word_count", 0)
    img_no_alt = summary.get("total_images_without_alt", 0)
    return (
        f"Web sitesi SEO analizi (Türkçe, kısa ve net):\n"
        f"URL: {url} | {pages} sayfa tarandı\n"
        f"Başlık: {title[:80]}\n"
        f"Meta: {meta[:100]}\n"
        f"H1 sayısı: {len(h1)} | Kelime: {words} | Mobil: {'Evet' if mobile else 'Hayır'}\n"
        f"Ort. kelime/sayfa: {avg_words} | Alt eksik görsel: {img_no_alt}\n"
        f"Sorunlar: {issues_text}\n\n"
        "Güçlü yönler ve 3 kritik öneri yaz. Son iki satırda:\n"
        "ÖNERİLEN BAŞLIK: ...\nÖNERİLEN META: ..."
    )


def build_ads_prompt(crawler_data: dict) -> str:
    url = crawler_data.get("url", "")
    title = crawler_data.get("title") or ""
    meta = crawler_data.get("meta_description") or ""
    h1 = crawler_data.get("h1_tags", [])
    h2 = crawler_data.get("h2_tags", [])
    words = crawler_data.get("word_count", 0)
    avg_words = crawler_data.get("summary", {}).get("avg_word_count", 0)

    keywords_context = ", ".join((h1 + h2)[:8]) if (h1 + h2) else title

    return (
        f"Aşağıdaki web sitesi için Google Ads anahtar kelime ve reklam metni önerileri hazırla.\n\n"
        f"Site: {url}\n"
        f"Başlık: {title[:80]}\n"
        f"Meta: {meta[:120]}\n"
        f"Başlıklar: {keywords_context[:200]}\n"
        f"Kelime sayısı: {avg_words or words}\n\n"
        "Yanıtını SADECE aşağıdaki JSON formatında ver, başka hiçbir şey yazma:\n"
        '{\n'
        '  "keywords": [\n'
        '    {"keyword": "kelime 1", "intent": "ticari", "priority": "yüksek"},\n'
        '    {"keyword": "kelime 2", "intent": "bilgi", "priority": "orta"},\n'
        '    {"keyword": "kelime 3", "intent": "ticari", "priority": "yüksek"},\n'
        '    {"keyword": "kelime 4", "intent": "ticari", "priority": "orta"},\n'
        '    {"keyword": "kelime 5", "intent": "marka", "priority": "düşük"}\n'
        '  ],\n'
        '  "ad_headlines": ["Başlık 1 (max 30 karakter)", "Başlık 2", "Başlık 3"],\n'
        '  "ad_descriptions": ["Açıklama 1 (max 90 karakter)", "Açıklama 2"],\n'
        '  "negative_keywords": ["gereksiz1", "gereksiz2", "gereksiz3"]\n'
        '}'
    )


def build_comparison_prompt(site: dict, rivals: list) -> str:
    def fmt(d):
        s = d.get("summary", {})
        return (
            f"Başlık: {'Var' if d.get('title') else 'Yok'} | "
            f"Meta: {'Var' if d.get('meta_description') else 'Yok'} | "
            f"Kelime: {d.get('word_count',0)} | "
            f"Mobil: {'Evet' if d.get('has_mobile_friendly') else 'Hayır'} | "
            f"Alt eksik: {s.get('total_images_without_alt',0)}"
        )
    rival_text = ""
    for i, r in enumerate(rivals, 1):
        rival_text += f"Rakip {i} ({r.get('url','')[:40]}): {fmt(r)}\n"
    return (
        f"Site karşılaştırması (Türkçe, kısa):\n"
        f"Kendi siten ({site.get('url','')[:40]}): {fmt(site)}\n"
        f"{rival_text}\n"
        "1) Önde olduğun alanlar\n2) Geride olduğun alanlar\n3) En hızlı 3 kazanım"
    )


@app.route("/", methods=["GET"])
def index():
    return "ASA Asistan API çalışıyor"


@app.route("/api/analyze", methods=["POST"])
def analyze():
    if not request.is_json:
        return jsonify({"error": "Content-Type: application/json gerekli"}), 400
    data = request.get_json()
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": '"url" boş olamaz'}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        crawler_data = scrape_seo(url)
    except Exception as e:
        return jsonify({"error": f"Crawler hatası: {str(e)}"}), 500
    try:
        prompt = build_analysis_prompt(crawler_data)
        ai_analysis = call_mistral(prompt)
    except ValueError as e:
        return jsonify({"url": url, "crawler_data": crawler_data, "ai_analysis": None, "error": str(e)}), 503
    return jsonify({"url": url, "crawler_data": crawler_data, "ai_analysis": ai_analysis})


@app.route("/api/ads", methods=["POST"])
def ads():
    if not request.is_json:
        return jsonify({"error": "Content-Type: application/json gerekli"}), 400
    data = request.get_json()
    url = (data.get("url") or "").strip()
    crawler_data = data.get("crawler_data")
    if not url:
        return jsonify({"error": '"url" boş olamaz'}), 400
    if not crawler_data:
        # Crawler'ı çalıştır
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            crawler_data = scrape_seo(url)
        except Exception as e:
            return jsonify({"error": f"Crawler hatası: {str(e)}"}), 500
    try:
        prompt = build_ads_prompt(crawler_data)
        system = "Sen Google Ads uzmanısın. Yanıtını SADECE geçerli JSON formatında ver, markdown veya açıklama ekleme."
        raw = call_mistral(prompt, system=system, max_tokens=600)
        # JSON parse
        import json, re
        clean = re.sub(r'```json|```', '', raw).strip()
        ads_data = json.loads(clean)
    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Ads analizi hatası: {str(e)}", "raw": raw if 'raw' in locals() else None}), 500
    return jsonify({"url": url, "ads": ads_data})


@app.route("/api/compare", methods=["POST"])
def compare():
    if not request.is_json:
        return jsonify({"error": "Content-Type: application/json gerekli"}), 400
    data = request.get_json()
    url = (data.get("url") or "").strip()
    rivals = data.get("rivals") or []
    if not url:
        return jsonify({"error": '"url" boş olamaz'}), 400
    if not rivals:
        return jsonify({"error": 'En az 1 rakip URL gerekli'}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        site_data = scrape_seo(url)
    except Exception as e:
        return jsonify({"error": f"Site tarama hatası: {str(e)}"}), 500
    rival_data = []
    for r_url in rivals:
        r_url = r_url.strip()
        if not r_url:
            continue
        if not r_url.startswith(("http://", "https://")):
            r_url = "https://" + r_url
        try:
            rd = scrape_seo(r_url)
        except Exception as e:
            rd = {"url": r_url, "error": str(e)}
        rival_data.append(rd)
    try:
        prompt = build_comparison_prompt(site_data, rival_data)
        comparison = call_mistral(prompt)
    except ValueError as e:
        return jsonify({"site": site_data, "rivals": rival_data, "comparison": None, "error": str(e)}), 503
    return jsonify({"site": site_data, "rivals": rival_data, "comparison": comparison})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint bulunamadı"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Sunucu hatası"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
