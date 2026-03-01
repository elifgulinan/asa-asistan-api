"""
ASA Asistan Flask API — Mistral AI + çok sayfalı crawler + rakip karşılaştırma + AI Ads.
v2: Sektör tespiti, bilişsel yük azaltma, AI SEO optimizasyonu.
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
        json={
            "model": MISTRAL_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        },
        timeout=60
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# ─────────────────────────────────────────────
# SEKTÖR TESPİTİ
# ─────────────────────────────────────────────

def detect_sector(d):
    """
    Sitenin sektörünü tespit et. 
    Döner: {'sektor': 'estetik klinik', 'sehir': 'Bodrum', 'hedef_kitle': 'bireysel müşteriler'}
    """
    url = d.get("url", "")
    title = d.get("title") or ""
    meta = d.get("meta_description") or ""
    h1 = " | ".join(d.get("h1_tags", [])[:3])
    h2 = " | ".join(d.get("h2_tags", [])[:4])
    body_snippet = (d.get("body_text") or "")[:300]

    prompt = (
        f"Aşağıdaki web sitesinin sektörünü, şehrini ve hedef kitlesini tespit et.\n"
        f"URL: {url}\n"
        f"Başlık: {title[:100]}\n"
        f"Meta: {meta[:100]}\n"
        f"H1: {h1[:100]}\n"
        f"H2: {h2[:150]}\n"
        f"İçerik: {body_snippet}\n\n"
        "Sadece JSON döndür, başka hiçbir şey yazma:\n"
        '{"sektor": "...", "sehir": "...", "hedef_kitle": "..."}\n'
        "sektor örnekleri: hukuk bürosu, estetik klinik, restoran, inşaat, e-ticaret, güzellik salonu, muhasebe, diş kliniği, otel, oto galeri, vs.\n"
        "sehir bilinmiyorsa boş bırak.\n"
        "hedef_kitle: bireysel müşteriler veya kurumsal müşteriler veya her ikisi"
    )
    system = "Sadece JSON döndür. Başka hiçbir şey yazma. Türkçe."
    try:
        raw = call_mistral(prompt, system=system, max_tokens=100)
        # JSON temizle
        raw = re.sub(r'```json|```', '', raw).strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Sektör tespiti başarısız: {e}")
        return {"sektor": "genel işletme", "sehir": "", "hedef_kitle": "bireysel müşteriler"}


# ─────────────────────────────────────────────
# ANALİZ PROMPT — "ONAYLA" MODELİ
# ─────────────────────────────────────────────

def build_analysis_prompt(d, sektor_bilgi):
    url = d.get("url", "")
    s = d.get("summary", {})
    sektor = sektor_bilgi.get("sektor", "genel işletme")
    sehir = sektor_bilgi.get("sehir", "")
    hedef = sektor_bilgi.get("hedef_kitle", "bireysel müşteriler")

    if d.get("error"):
        return f"SEO analizi yap:\nURL: {url}\nSektör: {sektor}\nHata: {d['error']}"

    issues = " | ".join([i['text'] for i in s.get("issues", [])]) or "Sorun yok"
    title = d.get("title") or "(yok)"
    meta = d.get("meta_description") or "(yok)"
    h1 = d.get("h1_tags", [])
    word_count = d.get("word_count", 0)
    mobile = "Evet" if d.get("has_mobile_friendly") else "Hayır"

    lokasyon = f" {sehir}'daki" if sehir else ""

    return (
        f"Sen{lokasyon} bir {sektor} sitesini analiz ediyorsun.\n"
        f"Hedef kitle: {hedef}\n"
        f"URL: {url} | {s.get('total_pages_crawled', 1)} sayfa tarandı\n"
        f"Başlık: {title[:80]}\n"
        f"Meta: {meta[:100]}\n"
        f"H1 sayısı: {len(h1)} | Kelime sayısı: {word_count} | Mobil uyumlu: {mobile}\n"
        f"Tespit edilen sorunlar: {issues}\n\n"
        f"Şimdi bu {sektor} sitesi için şunu yaz:\n\n"
        f"1. Siteyi 1 cümleyle değerlendir (işletme sahibine hitap et, teknik terim kullanma)\n"
        f"2. HAZIR OLAN şeyler: (Google'da ne iyi gözüküyor — max 2 madde, kısa)\n"
        f"3. HAZIRLADIM: (işletme sahibine '3 şey hazırladım, onaylar mısınız?' formatında — "
        f"teknik terim yok, sadece ne kazanacakları var)\n"
        f"   - Hazır 1: [ne yapılacak] → [ne kazanacaklar]\n"
        f"   - Hazır 2: [ne yapılacak] → [ne kazanacaklar]\n"
        f"   - Hazır 3: [ne yapılacak] → [ne kazanacaklar]\n"
        f"4. Son iki satırda:\n"
        f"ÖNERİLEN BAŞLIK: ...\n"
        f"ÖNERİLEN META: ...\n\n"
        f"ÖNERİLEN BAŞLIK ve META hem Google hem de ChatGPT/Perplexity gibi AI arama motorları için optimize olmalı. "
        f"Şehir adı, sektör ve en önemli hizmet mutlaka geçmeli. Doğal, soru-cevap formatına uygun yaz."
    )


# ─────────────────────────────────────────────
# ADS PROMPT
# ─────────────────────────────────────────────

def build_ads_prompt(d, sektor_bilgi=None):
    url = d.get("url", "")
    title = d.get("title") or ""
    h1 = d.get("h1_tags", [])
    h2 = d.get("h2_tags", [])
    ctx = ", ".join((h1 + h2)[:4]) if (h1 + h2) else title[:60]

    sektor = ""
    sehir = ""
    if sektor_bilgi:
        sektor = sektor_bilgi.get("sektor", "")
        sehir = sektor_bilgi.get("sehir", "")

    sektor_hint = ""
    if sektor:
        sektor_hint = f"Sektör: {sektor}"
    if sehir:
        sektor_hint += f" | Şehir: {sehir}"

    return (
        f"Site: {url}\n"
        f"Konu: {ctx[:100]}\n"
        f"{sektor_hint}\n\n"
        "Örnek:\n"
        "KEYWORDS: bodrum sac ekimi, prp tedavisi, botoks bodrum, estetik klinik, sac ekimi fiyatlari\n"
        "HEADLINES: Bodrum Sac Ekimi Uzmani | PRP ve Botoks | Estetik Klinik Bodrum\n"
        "DESCRIPTIONS: Uzman ekip ile kalici sonuclar. Randevu alin! | Bodrum estetik merkezi. Hemen arayin!\n"
        "NEGATIVE: ucretsiz, bedava, kendin yap\n\n"
        f"Simdi {url} icin ayni formatta yaz. Sadece 4 satir:"
    )


def parse_ads(raw):
    def ex(label, sep):
        m = re.search(rf'\*{{0,2}}{label}\*{{0,2}}:\*{{0,2}}\s*(.+)$', raw, re.MULTILINE | re.IGNORECASE)
        if not m:
            return []
        return [x.strip().strip('*').strip() for x in m.group(1).split(sep) if x.strip().strip('*').strip()]
    return {
        "keywords": [{"keyword": k, "intent": "ticari", "priority": "orta"} for k in ex("KEYWORDS", ",")],
        "ad_headlines": ex("HEADLINES", "|"),
        "ad_descriptions": ex("DESCRIPTIONS", "|"),
        "negative_keywords": ex("NEGATIVE", ",")
    }


# ─────────────────────────────────────────────
# META ÖNERİSİ PROMPT — AI SEO DAHİL
# ─────────────────────────────────────────────

def build_meta_prompt(d, sektor_bilgi):
    url = d.get("url", "")
    title = d.get("title") or "(yok)"
    meta = d.get("meta_description") or "(yok)"
    sektor = sektor_bilgi.get("sektor", "genel işletme")
    sehir = sektor_bilgi.get("sehir", "")
    h1 = " | ".join(d.get("h1_tags", [])[:2])

    lokasyon = f"{sehir} " if sehir else ""

    return (
        f"Bir {lokasyon}{sektor} sitesi için SEO meta içerikleri yaz.\n"
        f"URL: {url}\n"
        f"Mevcut başlık: {title[:80]}\n"
        f"Mevcut meta: {meta[:120]}\n"
        f"H1: {h1[:100]}\n\n"
        f"Kurallar:\n"
        f"- Başlık: max 60 karakter, {lokasyon}{sektor} ana hizmet içermeli\n"
        f"- Meta: max 155 karakter, doğal dil, soru-cevap formatına uygun (AI arama için)\n"
        f"- Her ikisi de hem Google hem ChatGPT/Perplexity/Gemini için optimize olmalı\n"
        f"- Şehir adı mutlaka geçmeli (varsa)\n\n"
        f"Sadece şunu yaz:\n"
        f"ÖNERİLEN BAŞLIK: ...\n"
        f"ÖNERİLEN META: ..."
    )


# ─────────────────────────────────────────────
# AI SEO PROMPT — ChatGPT/Perplexity/Gemini'de görün
# ─────────────────────────────────────────────

def build_ai_seo_prompt(d, sektor_bilgi):
    url = d.get("url", "")
    sektor = sektor_bilgi.get("sektor", "genel işletme")
    sehir = sektor_bilgi.get("sehir", "")
    hedef = sektor_bilgi.get("hedef_kitle", "bireysel müşteriler")
    lokasyon = f"{sehir} " if sehir else ""

    h1 = " | ".join(d.get("h1_tags", [])[:3])
    h2 = " | ".join(d.get("h2_tags", [])[:4])
    body = (d.get("body_text") or "")[:400]

    return (
        f"Sen bir {lokasyon}{sektor} sitesi için AI SEO stratejisi hazırlıyorsun.\n"
        f"Hedef kitle: {hedef}\n"
        f"URL: {url}\n"
        f"H1: {h1[:100]}\nH2: {h2[:150]}\nİçerik: {body}\n\n"
        f"ChatGPT, Perplexity ve Gemini gibi AI arama motorlarında '{lokasyon}{sektor}' aramasında "
        f"bu sitenin önerilmesi için şunları hazırla:\n\n"
        f"1. SORU-CEVAP (5 adet): Müşterilerin en çok sorduğu sorular ve kısa net cevaplar.\n"
        f"   Format: S: [soru] / C: [1-2 cümle cevap]\n"
        f"   Sorular doğal konuşma dilinde olmalı, teknik terim yok.\n\n"
        f"2. İŞLETME TANITIM BLOĞU: 3-4 cümlelik özet. AI bu bloğu doğrudan alıntılar.\n"
        f"   İçermeli: ne yapıyor, nerede, neden güvenilir, nasıl iletişim.\n\n"
        f"3. GÖRSEL ÖNERİSİ: Bu sektör için ideal fotoğraf nasıl olmalı?\n"
        f"   Format: 'Fotoğrafta şunlar olmalı: ...'\n"
        f"   Canva veya AI görsel aracına yapıştırılabilecek kadar net bir tarif yaz.\n"
        f"   Gerçekçi, profesyonel, klişesiz olsun.\n\n"
        f"Sadece bu 3 bölümü yaz, başka hiçbir şey ekleme. Türkçe, sade dil."
    )


def parse_ai_seo(raw):
    """AI SEO çıktısını parse et"""
    result = {
        "soru_cevap": [],
        "tanitim_blogu": "",
        "gorsel_onerisi": ""
    }

    # Soru-cevap bloğunu çıkar
    sc_match = re.search(r'SORU-CEVAP.*?\n(.*?)(?=\n\d\.|İŞLETME|$)', raw, re.DOTALL | re.IGNORECASE)
    if sc_match:
        sc_text = sc_match.group(1)
        pairs = re.findall(r'S:\s*(.+?)\s*/\s*C:\s*(.+?)(?=\nS:|\Z)', sc_text, re.DOTALL)
        result["soru_cevap"] = [{"soru": s.strip(), "cevap": c.strip()} for s, c in pairs]

    # Tanıtım bloğunu çıkar
    tanitim_match = re.search(r'İŞLETME TANITIM BLOĞU.*?\n(.*?)(?=\n\d\.|GÖRSEL|$)', raw, re.DOTALL | re.IGNORECASE)
    if tanitim_match:
        result["tanitim_blogu"] = tanitim_match.group(1).strip()

    # Görsel önerisini çıkar
    gorsel_match = re.search(r'GÖRSEL ÖNERİSİ.*?\n(.*?)$', raw, re.DOTALL | re.IGNORECASE)
    if gorsel_match:
        result["gorsel_onerisi"] = gorsel_match.group(1).strip()

    # Parse başarısız olduysa ham metni de koy
    result["raw"] = raw
    return result


# ─────────────────────────────────────────────
# KARŞILAŞTIRMA PROMPT
# ─────────────────────────────────────────────

def build_comparison_prompt(site, rivals, sektor_bilgi=None):
    sektor = sektor_bilgi.get("sektor", "genel işletme") if sektor_bilgi else "genel işletme"

    def fmt(d):
        s = d.get("summary", {})
        return (
            f"Başlık:{'Var' if d.get('title') else 'Yok'} "
            f"Meta:{'Var' if d.get('meta_description') else 'Yok'} "
            f"Kelime:{d.get('word_count', 0)} "
            f"Mobil:{'E' if d.get('has_mobile_friendly') else 'H'}"
        )

    rival_text = "".join([
        f"Rakip {i+1} ({r.get('url', '')[:30]}): {fmt(r)}\n"
        for i, r in enumerate(rivals)
    ])

    return (
        f"Sektör: {sektor}\n"
        f"Karşılaştırma (Türkçe, kısa, işletme sahibine hitap et):\n"
        f"Senin siten ({site.get('url', '')[:30]}): {fmt(site)}\n"
        f"{rival_text}\n"
        f"1) Rakiplerden önde olduğun alanlar\n"
        f"2) Geride olduğun alanlar\n"
        f"3) Bu hafta yapılabilecek en hızlı 3 kazanım"
    )


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

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

    # Sektör tespiti
    try:
        sektor_bilgi = detect_sector(crawler_data)
        logger.info(f"Sektör tespiti: {sektor_bilgi}")
    except Exception as e:
        logger.warning(f"Sektör tespiti atlandı: {e}")
        sektor_bilgi = {"sektor": "genel işletme", "sehir": "", "hedef_kitle": "bireysel müşteriler"}

    try:
        ai_analysis = call_mistral(build_analysis_prompt(crawler_data, sektor_bilgi), max_tokens=600)
    except Exception as e:
        return ok({
            "url": url,
            "crawler_data": crawler_data,
            "sektor_bilgi": sektor_bilgi,
            "ai_analysis": None,
            "error": str(e)
        })

    # AI SEO — ChatGPT/Perplexity/Gemini'de görün
    try:
        ai_seo_raw = call_mistral(build_ai_seo_prompt(crawler_data, sektor_bilgi), max_tokens=800)
        ai_seo = parse_ai_seo(ai_seo_raw)
        logger.info(f"AI SEO tamamlandı: {len(ai_seo.get('soru_cevap', []))} soru-cevap")
    except Exception as e:
        logger.warning(f"AI SEO atlandı: {e}")
        ai_seo = {"soru_cevap": [], "tanitim_blogu": "", "gorsel_onerisi": "", "raw": ""}

    return ok({
        "url": url,
        "crawler_data": crawler_data,
        "sektor_bilgi": sektor_bilgi,
        "ai_analysis": ai_analysis,
        "ai_seo": ai_seo
    })


@app.route("/api/ai_seo", methods=["POST"])
def ai_seo_endpoint():
    """Sadece AI SEO çıktısı — ayrı çağrılabilir"""
    if not request.is_json:
        return err("Content-Type: application/json gerekli")
    data = request.get_json()
    url = (data.get("url") or "").strip()
    crawler_data = data.get("crawler_data")
    sektor_bilgi = data.get("sektor_bilgi")

    if not url:
        return err('"url" boş olamaz')
    if not crawler_data:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            crawler_data = scrape_seo(url)
        except Exception as e:
            return err(f"Crawler hatası: {e}", 500)

    if not sektor_bilgi:
        try:
            sektor_bilgi = detect_sector(crawler_data)
        except Exception:
            sektor_bilgi = {"sektor": "genel işletme", "sehir": "", "hedef_kitle": "bireysel müşteriler"}

    try:
        ai_seo_raw = call_mistral(build_ai_seo_prompt(crawler_data, sektor_bilgi), max_tokens=800)
        ai_seo = parse_ai_seo(ai_seo_raw)
    except Exception as e:
        return err(f"AI SEO hatası: {e}", 500)

    return ok({"url": url, "sektor_bilgi": sektor_bilgi, "ai_seo": ai_seo})


@app.route("/api/ads", methods=["POST"])
def ads():
    if not request.is_json:
        return err("Content-Type: application/json gerekli")
    data = request.get_json()
    url = (data.get("url") or "").strip()
    crawler_data = data.get("crawler_data")
    sektor_bilgi = data.get("sektor_bilgi")  # frontend'den geçebilir

    if not url:
        return err('"url" boş olamaz')
    if not crawler_data:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            crawler_data = scrape_seo(url)
        except Exception as e:
            return err(f"Crawler hatası: {e}", 500)

    # Sektör bilgisi yoksa tespit et
    if not sektor_bilgi:
        try:
            sektor_bilgi = detect_sector(crawler_data)
        except Exception:
            sektor_bilgi = {"sektor": "genel işletme", "sehir": "", "hedef_kitle": "bireysel müşteriler"}

    raw = ""
    try:
        raw = call_mistral(
            build_ads_prompt(crawler_data, sektor_bilgi),
            system="Google Ads uzmanisin. Sadece 4 satir yaz: KEYWORDS, HEADLINES, DESCRIPTIONS, NEGATIVE. Baska hicbir sey ekleme.",
            max_tokens=200
        )
        logger.info(f"Ads raw: {raw}")
        ads_data = parse_ads(raw)
    except Exception as e:
        logger.error(f"Ads error: {e}, raw: {raw}")
        ads_data = {"keywords": [], "ad_headlines": [], "ad_descriptions": [], "negative_keywords": []}

    return ok({"url": url, "ads": ads_data, "sektor_bilgi": sektor_bilgi})


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

    # Sektör tespiti
    try:
        sektor_bilgi = detect_sector(site_data)
    except Exception:
        sektor_bilgi = {"sektor": "genel işletme", "sehir": "", "hedef_kitle": "bireysel müşteriler"}

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
        comparison = call_mistral(build_comparison_prompt(site_data, rival_data, sektor_bilgi))
    except Exception as e:
        return ok({
            "site": site_data,
            "rivals": rival_data,
            "sektor_bilgi": sektor_bilgi,
            "comparison": None,
            "error": str(e)
        })

    return ok({
        "site": site_data,
        "rivals": rival_data,
        "sektor_bilgi": sektor_bilgi,
        "comparison": comparison
    })


# ─────────────────────────────────────────────
# HATA YÖNETİMİ
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return err("Endpoint bulunamadı", 404)

@app.errorhandler(500)
def server_error(e):
    return err("Sunucu hatası", 500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
