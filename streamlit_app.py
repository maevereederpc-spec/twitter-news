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
DEFAULT_FEEDS = [
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"
]
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
if "bookmarks" not in st.session_state:
    st.session_state["bookmarks"] = {}
if "show_sidebar" not in st.session_state:
    st.session_state["show_sidebar"] = True

def toggle_bookmark(article: Dict):
    link = article.get("link")
    if not link:
        return
    if link in st.session_state["bookmarks"]:
        del st.session_state["bookmarks"][link]
    else:
        st.session_state["bookmarks"][link] = article

# ---------- Page config and theme CSS ----------
st.set_page_config(page_title="NYT Dashboard", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    :root{
      --bg:#fff7fb;
      --card:#ffffff;
      --muted:#bdb0b6;
      --accent:#ffb6d5;
      --accent-strong:#ff8fc2;
      --text:#2b1f22;
      --sidebar-black:#0b0b0b;
      --sidebar-text:#ffffff;
      --border: rgba(43,31,34,0.08);
      --shadow: 0 6px 18px rgba(43,31,34,0.06);
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
    .card {
      background: #ffffff;
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 6px 18px rgba(43,31,34,0.06);
      border: 1px solid rgba(43,31,34,0.08);
      margin-bottom: 14px;
    }
    .heading-box {
      background: linear-gradient(90deg, rgba(255,182,213,0.18), rgba(255,143,194,0.08));
      padding: 8px 12px;
      border-radius: 8px;
      display: inline-block;
      margin-bottom: 8px;
    }
    .muted { color: #bdb0b6; font-size: 0.92rem; }
    .summary { color: #3b2a2f; font-size: 0.98rem; line-height: 1.6; margin-top: 8px; }
    .stButton>button {
      background: linear-gradient(180deg, var(--action-pink), var(--action-pink-strong));
      color: #fff; border: none; padding: 8px 12px; border-radius: 10px; font-weight: 600;
    }
    a.article-link { text-decoration: none; color: var(--text); }
    a.article-link:hover { text-decoration: underline; }
    .three-col-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; align-items: start; }
    @media (max-width: 1100px) { .three-col-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 700px) { .three-col-grid { grid-template-columns: 1fr; } }
    .single-col-list { display: block; gap: 12px; }
    /* extra spacing for action area */
    .action-anchor-button { margin-right: 18px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Sidebar content (includes timezone selector) ----------
COMMON_TZ = [
    "System", "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
    "Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney"
]

with st.sidebar:
    st.markdown("## NYT RSS Explorer")
    feeds_input = st.text_area("RSS feeds (one per line)", value="\n".join(DEFAULT_FEEDS), height=140)
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
    st.write("Choose how published times are displayed.")
    tz_choice = st.selectbox("Display timezone", COMMON_TZ, index=0)
    if tz_choice != "System" and not ZONEINFO_AVAILABLE and 'pytz' not in globals():
        st.warning("Timezone conversion requires Python 3.9+ (zoneinfo) or pytz installed. Times will show in UTC or system timezone.")
    st.markdown("---")
    st.markdown("### Summarize")
    st.write("Create a short summary of the aggregated headlines and short summaries.")
    summary_length = st.slider("Summary sentences", 1, 6, 3)
    if st.button("Summarize headlines"):
        st.session_state["_summarize_now"] = True
    st.markdown("---")
    st.markdown("### Bookmarks")
    st.write(f"**Saved** {len(st.session_state['bookmarks'])}")
    if st.button("Clear bookmarks"):
        st.session_state["bookmarks"].clear()

# ---------- Sidebar toggle ----------
show_sidebar = st.checkbox("Show sidebar", value=st.session_state["show_sidebar"])
st.session_state["show_sidebar"] = show_sidebar
if not st.session_state["show_sidebar"]:
    st.markdown("<style>[data-testid='stSidebar'] { display: none; }</style>", unsafe_allow_html=True)

# ---------- Text size adjustments ----------
if text_size == "Large":
    st.markdown("<style> .card h3{font-size:1.15rem;} .summary{font-size:1.05rem;} </style>", unsafe_allow_html=True)
elif text_size == "Extra large":
    st.markdown("<style> .card h3{font-size:1.25rem;} .summary{font-size:1.12rem;} </style>", unsafe_allow_html=True)

# ---------- Top header: NYT Dashboard with heading-box ----------
st.markdown("<div class='heading-box'><h2 style='margin:0;'>NYT Dashboard</h2></div>", unsafe_allow_html=True)

# ---------- Fetch and aggregate ----------
rss_list = [r.strip() for r in feeds_input.splitlines() if r.strip()]
all_items = []
for feed in rss_list:
    try:
        items = fetch_rss(feed)
        all_items.extend(items)
    except Exception:
        st.warning(f"Failed to fetch feed {feed}")

# Deduplicate and parse dates
seen = set()
unique = []
for it in all_items:
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

# ---------- Long-scroll rendering (either grid or single-column list) ----------
tab1, tab2 = st.tabs(["Results", "Bookmarks"])
with tab1:
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
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    # Title links now use same-tab anchor; clicking title also redirects fully
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
                            st.image(art["media"], width=int(image_width))
                        except Exception:
                            pass
                    if art.get("summary"):
                        st.markdown(
                            f"<div class='summary'>{(art.get('summary') or '')[:320]}{'…' if len(art.get('summary') or '')>320 else ''}</div>",
                            unsafe_allow_html=True,
                        )

                    # Action area: two columns so Open (anchor) and Save (Streamlit button) are spaced
                    action_cols = st.columns([1, 1])
                    # Left column: Open anchor (same-tab redirect). Add class for spacing.
                    with action_cols[0]:
                        st.markdown(
                            f"<a class='action-anchor-button' href='{art.get('link')}' target='_self' rel='noopener noreferrer' style='text-decoration:none;'>"
                            f"<button style='background:linear-gradient(180deg,var(--action-pink),var(--action-pink-strong));color:#fff;border:none;padding:8px 12px;border-radius:10px;font-weight:600;'>Open</button>"
                            f"</a>",
                            unsafe_allow_html=True,
                        )
                    # Right column: Save button (Streamlit) so it updates session state
                    with action_cols[1]:
                        if st.button("★ Save", key=f"save_{idx}"):
                            toggle_bookmark(art)
                    st.markdown("</div>", unsafe_allow_html=True)

        else:  # Simple single-column list
            for idx, art in enumerate(filtered):
                st.markdown("<div class='card'>", unsafe_allow_html=True)
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

                # Action area: two columns for spacing
                action_cols = st.columns([1, 1])
                with action_cols[0]:
                    st.markdown(
                        f"<a class='action-anchor-button' href='{art.get('link')}' target='_self' rel='noopener noreferrer' style='text-decoration:none;'>"
                        f"<button style='background:linear-gradient(180deg,var(--action-pink),var(--action-pink-strong));color:#fff;border:none;padding:8px 12px;border-radius:10px;font-weight:600;'>Open</button>"
                        f"</a>",
                        unsafe_allow_html=True,
                    )
                with action_cols[1]:
                    if st.button("★ Save", key=f"save_list_{idx}"):
                        toggle_bookmark(art)
                st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    bookmarks = list(st.session_state["bookmarks"].values())
    if not bookmarks:
        st.info("No bookmarks yet. Save articles with the ★ Save button.")
    else:
        if layout_choice == "3-up grid (3 per row)":
            cols = st.columns(3)
            for idx, art in enumerate(bookmarks):
                col = cols[idx % 3]
                with col:
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    st.markdown(
                        f"<div class='heading-box'><a class='article-link' href='{art.get('link')}' target='_self' rel='noopener noreferrer'><strong>{art.get('title')}</strong></a></div>",
                        unsafe_allow_html=True,
                    )
                    if art.get("media") and show_images:
                        try:
                            st.image(art["media"], width=int(image_width))
                        except Exception:
                            pass
                    if art.get("summary"):
                        st.markdown(f"<div class='summary'>{(art.get('summary') or '')[:400]}</div>", unsafe_allow_html=True)
                    if st.button("Remove", key=f"remove_{idx}"):
                        toggle_bookmark(art)
                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            for idx, art in enumerate(bookmarks):
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='heading-box' style='width:100%'><a class='article-link' href='{art.get('link')}' target='_self' rel='noopener noreferrer'><strong>{art.get('title')}</strong></a></div>",
                    unsafe_allow_html=True,
                )
                if art.get("media") and show_images:
                    try:
                        st.image(art["media"], width=int(image_width))
                    except Exception:
                        pass
                if art.get("summary"):
                    st.markdown(f"<div class='summary'>{(art.get('summary') or '')[:400]}</div>", unsafe_allow_html=True)
                if st.button("Remove", key=f"remove_list_{idx}"):
                    toggle_bookmark(art)
                st.markdown("</div>", unsafe_allow_html=True)

st.caption("Open now fully redirects you to the NYT article in the same tab. Save bookmarks persist for this session.")
