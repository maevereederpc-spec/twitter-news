import streamlit as st

# app.py
import time
import re
from typing import List, Dict, Optional
from urllib.parse import urlparse
import feedparser
import requests
from newspaper import Article
from bs4 import BeautifulSoup
import streamlit as st
from datetime import datetime, timedelta, timezone
import math
from collections import Counter

# Timezone support
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    ZONEINFO_AVAILABLE = True
except Exception:
    ZONEINFO_AVAILABLE = False
    try:
        import pytz  # fallback
        ZoneInfo = None
    except Exception:
        pytz = None

# ---------- Configuration ----------
NYT_FEEDS = {
    "Top Stories": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "Politics": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
}
USER_AGENT = "NYT-RSS-Explorer/1.0"
HEADERS = {"User-Agent": USER_AGENT}
CACHE_TTL = 600
POLITE_DELAY = 0.25
DEFAULT_THUMB_WIDTH = 220
MAX_AGGREGATE = 200  # safety cap to avoid extremely long pages

# Defensive lxml check (warn if missing)
try:
    import lxml.html.clean  # noqa: F401
except Exception:
    import warnings
    warnings.warn("lxml.html.clean not available. Install lxml_html_clean or pin lxml<5 for full newspaper3k support.")

# ---------- Helpers: RSS and extraction ----------
@st.cache_data(ttl=CACHE_TTL)
def fetch_rss(url: str) -> List[Dict]:
    parsed = feedparser.parse(url)
    items = []
    for entry in parsed.entries:
        items.append({
            "title": entry.get("title"),
            "link": entry.get("link"),
            "published": entry.get("published"),
            "summary": entry.get("summary") or entry.get("description"),
            "source": parsed.feed.get("title"),
            "media": _extract_media(entry),
            "published_struct": entry.get("published_parsed")
        })
    return items

def _extract_media(entry: dict) -> Optional[str]:
    media = entry.get("media_content") or entry.get("media_thumbnail")
    if media and isinstance(media, list) and media:
        m = media[0]
        return m.get("url") or m.get("value")
    enc = entry.get("enclosures")
    if enc and isinstance(enc, list) and enc:
        return enc[0].get("href")
    summary = entry.get("summary", "")
    if "<img" in summary:
        soup = BeautifulSoup(summary, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img.get("src")
    return None

@st.cache_data(ttl=CACHE_TTL)
def extract_article_text(url: str) -> Dict:
    try:
        art = Article(url)
        art.download()
        art.parse()
        return {
            "title": art.title,
            "text": art.text,
            "top_image": art.top_image,
            "publish_date": art.publish_date.isoformat() if art.publish_date else None,
            "authors": art.authors,
            "url": url
        }
    except Exception:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            title = (soup.title.get_text(strip=True) if soup.title else None)
            paragraphs = soup.select("article p") or soup.select("p")
            text = "\n\n".join(p.get_text(strip=True) for p in paragraphs[:8])
            og_image = soup.find("meta", property="og:image")
            top_image = og_image["content"] if og_image and og_image.get("content") else None
            meta_pub = soup.find("meta", {"name": "ptime"}) or soup.find("meta", {"itemprop": "datePublished"})
            pub = meta_pub.get("content") if meta_pub and meta_pub.get("content") else None
            return {"title": title, "text": text, "top_image": top_image, "publish_date": pub, "authors": [], "url": url}
        except Exception:
            return {}

def parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt.endswith("Z") or fmt.endswith("%z"):
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    try:
        import time as _time
        if isinstance(s, _time.struct_time):
            return datetime.fromtimestamp(_time.mktime(s))
    except Exception:
        pass
    return None

def to_timezone(dt: Optional[datetime], tz_name: str) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if tz_name == "System":
        return dt.astimezone()
    try:
        if ZONEINFO_AVAILABLE:
            return dt.astimezone(ZoneInfo(tz_name))
        elif 'pytz' in globals() and pytz:
            return dt.astimezone(pytz.timezone(tz_name))
    except Exception:
        return dt.astimezone(timezone.utc)

def format_dt_for_display(dt: Optional[datetime], tz_name: str) -> str:
    if not dt:
        return ""
    converted = to_timezone(dt, tz_name)
    if not converted:
        return ""
    tz_abbr = converted.tzname() or ""
    return converted.strftime(f"%Y-%m-%d %H:%M {tz_abbr}")

# ---------- Simple extractive summarizer ----------
STOPWORDS = {
    "the","and","to","of","a","in","for","on","with","is","as","by","at","from","that","it","be","are","was","an","has","have","its","this","new","will","after","over","about","more","up","into","than","but","not","who","which"
}
def tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens = re.findall(r"[a-zA-Z0-9']{2,}", text)
    return tokens
def build_freq_map(texts: List[str]) -> Counter:
    freq = Counter()
    for t in texts:
        for w in tokenize(t):
            if w in STOPWORDS:
                continue
            freq[w] += 1
    if not freq:
        return freq
    maxf = max(freq.values())
    for k in list(freq.keys()):
        freq[k] = freq[k] / maxf
    return freq
def split_sentences(text: str) -> List[str]:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]
def score_sentence(sent: str, freq_map: Counter) -> float:
    tokens = tokenize(sent)
    if not tokens:
        return 0.0
    score = 0.0
    for t in tokens:
        score += freq_map.get(t, 0.0)
    return score / (len(tokens) ** 0.2)
def summarize_articles(articles: List[Dict], max_sentences: int = 4) -> Dict:
    if not articles:
        return {"summary": "No articles to summarize.", "top_keywords": []}
    pool_texts = []
    for a in articles:
        title = a.get("title") or ""
        summary = a.get("summary") or ""
        pool_texts.append(title)
        for s in split_sentences(summary)[:3]:
            pool_texts.append(s)
    freq = build_freq_map(pool_texts)
    candidates = []
    for t in pool_texts:
        for s in split_sentences(t):
            candidates.append(s)
    scored = []
    seen = set()
    for s in candidates:
        key = s.lower()
        if key in seen or len(s) < 20:
            continue
        seen.add(key)
        scored.append((score_sentence(s, freq), s))
    scored.sort(reverse=True, key=lambda x: x[0])
    chosen = []
    for score, sent in scored:
        if len(chosen) >= max_sentences:
            break
        low = sent.lower()
        if any(low in c.lower() or c.lower() in low for c in chosen):
            continue
        chosen.append(sent)
    if not chosen:
        for a in articles[:max_sentences]:
            if a.get("title"):
                chosen.append(a["title"])
    summary_paragraph = " ".join(chosen)
    top_keywords = freq.most_common(8)
    return {"summary": summary_paragraph, "top_keywords": top_keywords}

# ---------- Session state ----------
if "show_sidebar" not in st.session_state:
    st.session_state["show_sidebar"] = True

# ---------- Page config and modernized CSS (no large frames) ----------
st.set_page_config(page_title="NYT Dashboard", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');

    :root{
      --bg:#fff7fb;
      --card:#ffffff;
      --muted:#8b7a80;
      --accent:#ffb6d5;
      --accent-strong:#ff8fc2;
      --text:#2b1f22;
      --sidebar-black:#0b0b0b;
      --sidebar-text:#ffffff;
      --border: rgba(43,31,34,0.12);
      --shadow: 0 14px 40px rgba(43,31,34,0.08);
      --action-pink: #ff8fc2;
      --action-pink-strong: #ff5fae;
      --glass: rgba(255,255,255,0.6);
    }

    html, body, [class*="css"]  {
      background: linear-gradient(180deg, var(--bg), #fffafc);
      color: var(--text);
      font-family: 'Inter', system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
      line-height: 1.6;
      -webkit-font-smoothing:antialiased;
      -moz-osx-font-smoothing:grayscale;
    }

    /* Sidebar modernized */
    .stSidebar {
      background: linear-gradient(180deg, #0b0b0b, #0f0f0f);
      color: var(--sidebar-text);
      border-right: 1px solid rgba(255,255,255,0.04);
      padding: 20px 18px;
      box-shadow: 0 8px 30px rgba(11,11,11,0.35);
    }
    .stSidebar .stTextInput>div>div>input, .stSidebar .stTextArea>div>div>textarea {
      background: rgba(255,255,255,0.03);
      color: var(--sidebar-text);
      border-radius: 8px;
      padding: 8px;
    }
    .stSidebar .stSelectbox>div>div, .stSidebar .stSlider>div {
      color: var(--sidebar-text);
    }
    .stSidebar h2 { color: var(--sidebar-text); margin-bottom: 6px; }

    /* Article card: elevated glassy surface (no large frame behind) */
    .article-card {
      background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(255,250,252,0.98));
      border-radius: 14px;
      padding: 20px;
      box-shadow: var(--shadow);
      border: 1px solid var(--border);
      transition: transform 0.14s ease, box-shadow 0.14s ease;
      min-height: 220px;
      display:flex;
      flex-direction:column;
      justify-content:space-between;
      margin-bottom: 20px;
    }
    .article-card:hover {
      transform: translateY(-6px);
      box-shadow: 0 22px 60px rgba(43,31,34,0.12);
    }

    .heading-box {
      background: linear-gradient(90deg, rgba(255,182,213,0.18), rgba(255,143,194,0.08));
      padding: 8px 12px;
      border-radius: 10px;
      display: inline-block;
      margin-bottom: 12px;
      font-weight:700;
      color: var(--text);
    }

    .muted { color: var(--muted); font-size: 0.9rem; margin-bottom: 10px; display:block; }
    .summary { color: #3b2a2f; font-size: 0.98rem; line-height: 1.6; margin-top: 8px; }

    /* Buttons (Open anchor styled) - not blue, modern pill */
    .open-button, .open-button:link, .open-button:visited, .open-button:hover, .open-button:active {
      background: linear-gradient(180deg, var(--action-pink), var(--action-pink-strong));
      color: #fff !important;
      border: none;
      padding: 10px 18px;
      border-radius: 999px;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none !important;
      display: inline-flex;
      align-items:center;
      gap:8px;
      box-shadow: 0 6px 18px rgba(255,143,194,0.18);
      transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .open-button:hover { transform: translateY(-2px); box-shadow: 0 12px 30px rgba(255,143,194,0.18); }

    a.article-link { text-decoration: none; color: var(--text); }
    a.article-link:hover { text-decoration: underline; }

    /* layout helpers */
    .centered-img { text-align: center; margin-top: 10px; margin-bottom: 14px; }
    .action-stack { display:flex;flex-direction:column;align-items:center;gap:14px;margin-top:14px; }
    .three-col-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; align-items: start; }
    @media (max-width: 1200px) { .three-col-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 760px) { .three-col-grid { grid-template-columns: 1fr; } }
    .single-col-list { display: block; gap: 14px; }

    /* subtle header */
    .top-header {
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:12px;
      margin-bottom:18px;
    }
    .brand {
      display:flex;
      align-items:center;
      gap:12px;
    }
    .brand .logo {
      width:44px;height:44px;border-radius:10px;background:linear-gradient(180deg,var(--accent),var(--accent-strong));
      display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:18px;
      box-shadow: 0 6px 18px rgba(255,143,194,0.12);
    }
    .brand h1 { margin:0;font-size:1.15rem;font-weight:800;letter-spacing:0.2px; }

    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Sidebar content ----------
COMMON_TZ = [
    "System", "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
    "Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney"
]

with st.sidebar:
    st.markdown("## NYT Dashboard")
    st.markdown("Choose which NYT feed to view and how to display articles.")
    feed_choice = st.selectbox("NYT feed", ["Top Stories", "Politics"], index=0)
    num_articles = st.slider("Max articles to aggregate", 5, 200, 60)
    image_width = st.number_input("Thumbnail width px", min_value=100, max_value=400, value=DEFAULT_THUMB_WIDTH, step=10)
    layout_choice = st.selectbox("Layout", ["3-up grid (3 per row)", "Simple list (single column)"], index=0)
    show_images = st.checkbox("Show images", value=True)
    use_extraction = st.checkbox("Fetch full article text", value=False)
    text_size = st.selectbox("Text size", ["Comfortable", "Large", "Extra large"], index=0)
    st.markdown("---")
    st.markdown("### Filters")
    keyword = st.text_input("Keyword filter")
    date_from = st.date_input("From", value=(datetime.utcnow() - timedelta(days=7)).date())
    date_to = st.date_input("To", value=datetime.utcnow().date())
    sort_by = st.selectbox("Sort by", ["Newest", "Oldest", "Source A→Z"], index=0)
    st.markdown("---")
    st.markdown("### Timezone")
    tz_choice = st.selectbox("Display timezone", COMMON_TZ, index=0)
    if tz_choice != "System" and not ZONEINFO_AVAILABLE and 'pytz' not in globals():
        st.warning("Timezone conversion requires Python 3.9+ (zoneinfo) or pytz installed. Times may show in UTC or system timezone.")
    st.markdown("---")
    st.markdown("### Summarize")
    summary_length = st.slider("Summary sentences", 1, 6, 3)
    if st.button("Summarize headlines"):
        st.session_state["_summarize_now"] = True

# ---------- Sidebar toggle ----------
show_sidebar = st.checkbox("Show sidebar", value=st.session_state["show_sidebar"])
st.session_state["show_sidebar"] = show_sidebar
if not st.session_state["show_sidebar"]:
    st.markdown("<style>[data-testid='stSidebar'] { display: none; }</style>", unsafe_allow_html=True)

# ---------- Text size adjustments ----------
if text_size == "Large":
    st.markdown("<style> .article-card h3{font-size:1.15rem;} .summary{font-size:1.05rem;} </style>", unsafe_allow_html=True)
elif text_size == "Extra large":
    st.markdown("<style> .article-card h3{font-size:1.25rem;} .summary{font-size:1.12rem;} </style>", unsafe_allow_html=True)

# ---------- Top header (modern) ----------
st.markdown(
    "<div class='top-header'>"
    "<div class='brand'><div class='logo'>NY</div><h1>NYT Dashboard</h1></div>"
    "<div style='color:#6b4b5b;font-size:0.95rem;'>Curation · Clean · Readable</div>"
    "</div>",
    unsafe_allow_html=True,
)

# ---------- Fetch and aggregate ----------
feed_url = NYT_FEEDS.get(feed_choice, NYT_FEEDS["Top Stories"])
rss_items = []
try:
    rss_items = fetch_rss(feed_url)
except Exception:
    st.warning(f"Failed to fetch feed {feed_url}")

# Deduplicate and parse dates
seen = set()
unique = []
for it in rss_items:
    link = it.get("link")
    if not link or link in seen:
        continue
    seen.add(link)
    pub_dt = None
    if it.get("published_struct"):
        try:
            import time as _time
            pub_dt = datetime.fromtimestamp(_time.mktime(it["published_struct"]))
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pub_dt = None
    if not pub_dt:
        pub_dt = parse_iso_date(it.get("published"))
    it["published_dt"] = pub_dt
    unique.append(it)

# Apply filters
def matches_filters(item):
    pub = item.get("published_dt")
    if pub:
        if pub.date() < date_from or pub.date() > date_to:
            return False
    if keyword:
        k = keyword.lower()
        if k not in (item.get("title") or "").lower() and k not in (item.get("summary") or "").lower():
            return False
    return True

filtered = [it for it in unique if matches_filters(it)]
if sort_by == "Newest":
    filtered.sort(key=lambda x: x.get("published_dt") or datetime.min, reverse=True)
elif sort_by == "Oldest":
    filtered.sort(key=lambda x: x.get("published_dt") or datetime.min)
else:
    filtered.sort(key=lambda x: (x.get("source") or "").lower())

cap = min(num_articles, MAX_AGGREGATE)
filtered = filtered[:cap]

# ---------- Summarization trigger ----------
summarize_now = st.session_state.pop("_summarize_now", False)
summary_result = None
if summarize_now:
    summary_result = summarize_articles(filtered, max_sentences=summary_length)

# ---------- Render results (modernized visuals, no large frames) ----------
if summary_result:
    with st.expander("Summary of aggregated headlines"):
        st.markdown(f"**Summary:** {summary_result['summary']}")
        if summary_result["top_keywords"]:
            kw_line = ", ".join(f"{k} ({round(v,2)})" for k, v in summary_result["top_keywords"])
            st.markdown(f"**Top keywords:** {kw_line}")

if not filtered:
    st.info("No articles match your filters.")
else:
    if layout_choice == "3-up grid (3 per row)":
        st.markdown("<div class='three-col-grid'>", unsafe_allow_html=True)
        for idx, art in enumerate(filtered):
            # Article card only (no large frame)
            st.markdown("<div class='article-card'>", unsafe_allow_html=True)

            # Title with heading box
            st.markdown(
                f"<div class='heading-box'><a class='article-link' href='{art.get('link')}' target='_self' rel='noopener noreferrer'><strong>{art.get('title')}</strong></a></div>",
                unsafe_allow_html=True,
            )

            # Meta line (source + time)
            meta = []
            if art.get("source"):
                meta.append(f"{art['source']}")
            if art.get("published_dt"):
                meta.append(format_dt_for_display(art.get("published_dt"), tz_choice))
            if meta:
                st.markdown(f"<div class='muted'>{' • '.join(meta)}</div>", unsafe_allow_html=True)

            # Centered image (rendered as HTML to keep perfect centering)
            if show_images and art.get("media"):
                st.markdown(
                    f"<div class='centered-img'><img src='{art.get('media')}' width='{int(image_width)}' style='max-width:100%;height:auto;border-radius:10px;box-shadow:0 8px 24px rgba(43,31,34,0.06);'/></div>",
                    unsafe_allow_html=True,
                )

            # Summary
            if art.get("summary"):
                st.markdown(
                    f"<div class='summary'>{(art.get('summary') or '')[:320]}{'…' if len(art.get('summary') or '')>320 else ''}</div>",
                    unsafe_allow_html=True,
                )

            # Action stack: Open (styled button) centered
            st.markdown(
                "<div class='action-stack'>"
                f"<a class='open-button' href='{art.get('link')}' target='_self' rel='noopener noreferrer'>Open</a>"
                "</div>",
                unsafe_allow_html=True,
            )

            st.markdown("</div>", unsafe_allow_html=True)  # close article-card
        st.markdown("</div>", unsafe_allow_html=True)

    else:  # Simple single-column list
        st.markdown("<div class='single-col-list'>", unsafe_allow_html=True)
        for idx, art in enumerate(filtered):
            st.markdown("<div class='article-card'>", unsafe_allow_html=True)

            st.markdown(
                f"<div class='heading-box' style='width:100%'><a class='article-link' href='{art.get('link')}' target='_self' rel='noopener noreferrer'><strong>{art.get('title')}</strong></a></div>",
                unsafe_allow_html=True,
            )

            meta = []
            if art.get("source"):
                meta.append(f"{art['source']}")
            if art.get("published_dt"):
                meta.append(format_dt_for_display(art.get("published_dt"), tz_choice))
            if meta:
                st.markdown(f"<div class='muted'>{' • '.join(meta)}</div>", unsafe_allow_html=True)

            if show_images and art.get("media"):
                st.markdown(
                    f"<div class='centered-img'><img src='{art.get('media')}' width='{int(image_width)}' style='max-width:100%;height:auto;border-radius:10px;box-shadow:0 8px 24px rgba(43,31,34,0.06);'/></div>",
                    unsafe_allow_html=True,
                )

            if art.get("summary"):
                st.markdown(
                    f"<div class='summary'>{(art.get('summary') or '')[:600]}{'…' if len(art.get('summary') or '')>600 else ''}</div>",
                    unsafe_allow_html=True,
                )

            st.markdown(
                "<div class='action-stack'>"
                f"<a class='open-button' href='{art.get('link')}' target='_self' rel='noopener noreferrer'>Open</a>"
                "</div>",
                unsafe_allow_html=True,
            )

            st.markdown("</div>", unsafe_allow_html=True)  # close article-card
        st.markdown("</div>", unsafe_allow_html=True)

st.caption("Updated: removed large frames between articles; cards are compact, modern, and aligned with the existing color palette.")
