import streamlit as st

# app.py
import time
import re
import os
import json
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

# ---------- Timezone support ----------
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

# Preferences persistence file
PREFS_FILE = "user_prefs.json"

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
if "bookmarks" not in st.session_state:
    st.session_state["bookmarks"] = {}
if "show_sidebar" not in st.session_state:
    st.session_state["show_sidebar"] = True
if "page_index" not in st.session_state:
    st.session_state["page_index"] = 0

# ---------- Preferences persistence helpers ----------
def load_prefs() -> Dict:
    if os.path.exists(PREFS_FILE):
        try:
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_prefs(prefs: Dict):
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass

_saved_prefs = load_prefs()

# ---------- Page config and theme CSS ----------
st.set_page_config(page_title="NYT Dashboard", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
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
      --shadow: 0 10px 30px rgba(43,31,34,0.06);
      --action-pink: #ff8fc2;
      --action-pink-strong: #ff5fae;
    }
    html, body, [class*="css"]  {
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
      line-height: 1.6;
    }
    .stSidebar {
      background: linear-gradient(180deg, var(--sidebar-black), #111111);
      color: var(--sidebar-text);
      border-right: 1px solid rgba(255,255,255,0.04);
      padding-top: 18px;
    }
    .stSidebar .stTextInput>div>div>input, .stSidebar .stTextArea>div>div>textarea {
      background: #0f0f0f;
      color: var(--sidebar-text);
      font-family: 'Inter', sans-serif;
    }

    /* --- Article layout: centered title + image + subtext --- */

    /* Ensure card centers its content */
    .article-card {
      background: transparent;
      border: none;
      box-shadow: none;
      border-radius: 0;
      padding: 12px 10px;
      margin: 0;
      transition: none;
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      align-items: center;      /* center horizontally */
      text-align: center;       /* center text */
      height: 100%;
      flex: 1 1 auto;
      min-height: 0;
    }

    /* Heading box: full width but centered text */
    .heading-box {
      background: linear-gradient(180deg, var(--accent), var(--accent-strong));
      color: #ffffff;
      padding: 10px 12px;
      border-radius: 8px;
      display: block;
      width: 100%;
      margin-bottom: 8px;
      font-weight: 800;
      letter-spacing: -0.2px;
      box-shadow: 0 6px 18px rgba(255,143,194,0.12);
      border: 1px solid rgba(255,143,194,0.12);
    }
    .heading-box a.article-link, .heading-box strong {
      color: #ffffff;
      text-decoration: none;
      display: block;
      text-align: center;
    }

    /* Title/link outside heading remains centered too */
    a.article-link { text-decoration: none; color: var(--text); display:inline-block; padding:4px 6px; border-radius:6px; }
    a.article-link:hover { background: rgba(255,143,194,0.03); text-decoration: none; }

    /* Image handling: force centered rendering and constrain size */
    .article-card img,
    .article-card > img,
    .article-card img[src],
    .article-card .stImage,
    .article-card .stImage img,
    .article-card .element-container img {
      display: block;
      margin-left: auto;
      margin-right: auto;
      margin-top: 8px;
      margin-bottom: 8px;
      width: 100%;
      max-width: 100%;
      max-height: 140px;       /* adjust if you want taller/shorter thumbnails */
      object-fit: cover;
      border-radius: 6px;
      flex: 0 0 auto;
    }

    /* Keep summary centered and reserve 4 lines of space */
    .summary {
      color: #3b2a2f;
      font-size: 0.96rem;
      line-height: 1.45;
      margin-top: 6px;
      font-family: 'Inter', sans-serif;
      overflow: hidden;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 4;
      min-height: calc(1.45em * 4);
      text-align: center;
      flex: 0 0 auto;
      width: 100%;
    }

    /* Ensure column wrappers allow cards to stretch (broad selectors for Streamlit versions) */
    [data-testid="column"] > div { height: 100%; display: flex; flex-direction: column; min-height: 0; }
    [data-testid="column"] { height: 100%; min-height: 0; }
    [data-testid="column"] > div > div { flex: 1 1 auto; min-height: 0; display:flex; flex-direction:column; align-items:stretch; }
    .stColumns > div, .css-1lcbmhc > div { height: 100%; display:flex; flex-direction:column; min-height:0; }
    .stColumns > div > div, .css-1lcbmhc > div > div { flex:1 1 auto; min-height:0; display:flex; flex-direction:column; align-items:stretch; }

    /* Responsive tweaks */
    @media (max-width: 1100px) { .three-col-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 700px) { .three-col-grid { grid-template-columns: 1fr; } .article-card { padding:10px; } }

    /* header modernized */
    .top-header { margin-bottom: 12px; }
    .brand { display:flex; align-items:center; gap:12px; font-family: 'Inter', sans-serif; }
    .brand .logo { width:40px;height:40px;border-radius:8px;background:linear-gradient(180deg,var(--accent),var(--accent-strong));display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:16px; }

    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Sidebar content (with saved prefs) ----------
COMMON_TZ = [
    "System", "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
    "Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney"
]

# Load defaults from saved prefs if available
default_feed = _saved_prefs.get("feed_choice", "Top Stories")
default_layout = _saved_prefs.get("layout_choice", "3-up grid (3 per row)")
default_image_width = _saved_prefs.get("image_width", DEFAULT_THUMB_WIDTH)
default_show_images = _saved_prefs.get("show_images", True)
default_text_size = _saved_prefs.get("text_size", "Comfortable")
default_tz = _saved_prefs.get("tz_choice", "System")
default_num_articles = _saved_prefs.get("num_articles", 60)
default_keyword = _saved_prefs.get("keyword", "")
default_sort_by = _saved_prefs.get("sort_by", "Newest")
default_date_from = _saved_prefs.get("date_from", (datetime.utcnow() - timedelta(days=7)).date())
default_date_to = _saved_prefs.get("date_to", datetime.utcnow().date())

with st.sidebar:
    st.markdown("## NYT Dashboard")
    st.markdown("Choose which NYT feed to view and how to display articles.")
    feed_choice = st.selectbox("NYT feed", ["Top Stories", "Politics"], index=["Top Stories", "Politics"].index(default_feed))
    num_articles = st.slider("Max articles to aggregate", 5, 200, int(default_num_articles))
    image_width = st.number_input("Thumbnail width px", min_value=80, max_value=400, value=int(default_image_width), step=10)
    layout_choice = st.selectbox("Layout", ["3-up grid (3 per row)", "Simple list (single column)"], index=["3-up grid (3 per row)", "Simple list (single column)"].index(default_layout))
    show_images = st.checkbox("Show images", value=default_show_images)
    use_extraction = st.checkbox("Fetch full article text", value=_saved_prefs.get("use_extraction", False))
    text_size = st.selectbox("Text size", ["Comfortable", "Large", "Extra large"], index=["Comfortable", "Large", "Extra large"].index(default_text_size))
    st.markdown("---")
    st.markdown("### Filters")
    keyword = st.text_input("Keyword filter", value=default_keyword)
    date_from = st.date_input("From", value=default_date_from)
    date_to = st.date_input("To", value=default_date_to)
    sort_by = st.selectbox("Sort by", ["Newest", "Oldest", "Source A→Z"], index=["Newest", "Oldest", "Source A→Z"].index(default_sort_by))
    st.markdown("---")
    st.markdown("### Timezone")
    tz_choice = st.selectbox("Display timezone", COMMON_TZ, index=COMMON_TZ.index(default_tz) if default_tz in COMMON_TZ else 0)
    st.markdown("---")
    st.markdown("### Preferences")
    if st.button("Save preferences"):
        prefs_to_save = {
            "feed_choice": feed_choice,
            "num_articles": num_articles,
            "image_width": image_width,
            "layout_choice": layout_choice,
            "show_images": show_images,
            "use_extraction": use_extraction,
            "text_size": text_size,
            "keyword": keyword,
            "date_from": str(date_from),
            "date_to": str(date_to),
            "sort_by": sort_by,
            "tz_choice": tz_choice,
        }
        save_prefs(prefs_to_save)
        st.success("Preferences saved to user_prefs.json")

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

# ---------- Top header ----------
st.markdown(
    "<div class='top-header'><div class='brand'><div class='logo'>NY</div><div style='font-weight:700;font-size:1.05rem;'>NYT Dashboard</div></div></div>",
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
    summary_result = summarize_articles(filtered, max_sentences=3)

# ---------- Long-scroll rendering (Results only) ----------
# Open button removed per request.
with st.container():
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
            cols = st.columns(3)
            for idx, art in enumerate(filtered):
                col = cols[idx % 3]
                with col:
                    st.markdown("<div class='article-card'>", unsafe_allow_html=True)
                    st.markdown(
                        f"<div class='heading-box'><a class='article-link' href='{art.get('link')}' target='_self' rel='noopener noreferrer'><strong>{art.get('title')}</strong></a></div>",
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
                        try:
                            # st.image will render an <img> inside wrappers; CSS centers it
                            st.image(art["media"], width=int(image_width))
                        except Exception:
                            pass
                    if art.get("summary"):
                        st.markdown(
                            f"<div class='summary'>{(art.get('summary') or '')[:320]}{'…' if len(art.get('summary') or '')>320 else ''}</div>",
                            unsafe_allow_html=True,
                        )

                    st.markdown("</div>", unsafe_allow_html=True)

        else:  # Simple single-column list
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
                    try:
                        st.image(art["media"], width=int(image_width))
                    except Exception:
                        pass
                if art.get("summary"):
                    st.markdown(
                        f"<div class='summary'>{(art.get('summary') or '')[:600]}{'…' if len(art.get('summary') or '')>600 else ''}</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown("</div>", unsafe_allow_html=True)

st.caption("The UI uses a modern Inter font across headings and body.")
