import streamlit as st

# app.py
"""
NYT Dashboard — preferences saved, News + Congress tabs,
no "Open" buttons, no Bookmarks tab, even spacing in 3x3 grid.
"""

import os
import json
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from collections import Counter

import feedparser
import requests
from bs4 import BeautifulSoup

import streamlit as st
import altair as alt
import pandas as pd

# ---------- Timezone support ----------
try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except Exception:
    ZONEINFO_AVAILABLE = False
    try:
        import pytz  # type: ignore
    except Exception:
        pytz = None

# ---------- Configuration ----------
NYT_FEEDS = {
    "Top Stories": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "Politics": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
}
PREFS_FILE = "user_prefs.json"
CACHE_TTL = 600
DEFAULT_THUMB_WIDTH = 220
MAX_AGGREGATE = 200

# ---------- Preferences helpers ----------
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

# ---------- RSS helpers ----------
@st.cache_data(ttl=CACHE_TTL)
def fetch_rss(url: str) -> List[Dict]:
    parsed = feedparser.parse(url)
    items = []
    for entry in parsed.entries:
        items.append({
            "title": entry.get("title"),
            "link": entry.get("link"),
            "summary": entry.get("summary") or entry.get("description"),
            "published": entry.get("published"),
            "media": _extract_media(entry),
            "source": parsed.feed.get("title"),
            "published_struct": entry.get("published_parsed"),
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
        elif pytz:
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

# ---------- Page setup and styling ----------
st.set_page_config(page_title="NYT Dashboard", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');

    :root{
      --bg:#fff7fb;
      --text:#2b1f22;
      --muted:#8b7a80;
      --accent:#ffb6d5;
      --accent-strong:#ff8fc2;
      --border: rgba(43,31,34,0.12);
      --shadow: 0 10px 30px rgba(43,31,34,0.06);
    }

    html, body, [class*="css"] {
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
      -webkit-font-smoothing:antialiased;
      -moz-osx-font-smoothing:grayscale;
    }

    .brand { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
    .brand .logo { width:40px;height:40px;border-radius:8px;background:linear-gradient(180deg,var(--accent),var(--accent-strong));display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:16px; }

    /* Grid: ensure even spacing and equal-height cards */
    .three-col-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 18px;
      align-items: stretch; /* stretch cards to equal height */
    }
    @media (max-width: 1100px) { .three-col-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 700px) { .three-col-grid { grid-template-columns: 1fr; } }

    .article-card {
      background: linear-gradient(180deg, #ffffff, #fffafc);
      border-radius: 14px;
      padding: 18px;
      box-shadow: var(--shadow);
      border: 1px solid var(--border);
      display:flex;
      flex-direction:column;
      justify-content:space-between; /* keeps spacing even inside card */
      height:100%; /* important for equal-height behavior */
      transition: transform 0.12s ease;
    }
    .article-card:hover { transform: translateY(-4px); }

    .heading-box {
      background: linear-gradient(90deg, rgba(255,182,213,0.18), rgba(255,143,194,0.08));
      padding: 8px 12px;
      border-radius: 8px;
      display: inline-block;
      margin-bottom: 10px;
      font-weight:700;
    }

    .centered-img { text-align:center; margin:8px 0; }
    .summary { color:#3b2a2f; line-height:1.5; margin-top:8px; }

    /* remove open button styles (no open button) */

    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Sidebar (preferences) ----------
COMMON_TZ = [
    "System", "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
    "Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney"
]

# Load defaults from saved prefs
default_feed = _saved_prefs.get("feed_choice", "Top Stories")
default_layout = _saved_prefs.get("layout_choice", "3-up grid (3 per row)")
default_image_width = _saved_prefs.get("image_width", DEFAULT_THUMB_WIDTH)
default_show_images = _saved_prefs.get("show_images", True)
default_tz = _saved_prefs.get("tz_choice", "System")
default_num_articles = _saved_prefs.get("num_articles", 60)
default_keyword = _saved_prefs.get("keyword", "")
default_sort_by = _saved_prefs.get("sort_by", "Newest")
default_date_from = _saved_prefs.get("date_from", (datetime.utcnow() - timedelta(days=7)).date())
default_date_to = _saved_prefs.get("date_to", datetime.utcnow().date())

with st.sidebar:
    st.markdown("## NYT Dashboard")
    feed_choice = st.selectbox("NYT feed", ["Top Stories", "Politics"], index=["Top Stories", "Politics"].index(default_feed))
    num_articles = st.slider("Max articles to aggregate", 5, 200, int(default_num_articles))
    image_width = st.number_input("Thumbnail width px", min_value=80, max_value=400, value=int(default_image_width), step=10)
    layout_choice = st.selectbox("Layout", ["3-up grid (3 per row)", "Simple list (single column)"], index=["3-up grid (3 per row)", "Simple list (single column)"].index(default_layout))
    show_images = st.checkbox("Show images", value=default_show_images)
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
            "keyword": keyword,
            "date_from": str(date_from),
            "date_to": str(date_to),
            "sort_by": sort_by,
            "tz_choice": tz_choice,
        }
        save_prefs(prefs_to_save)
        st.success("Preferences saved to user_prefs.json")

# ---------- Header ----------
st.markdown(
    "<div class='brand'><div class='logo'>NY</div><div style='font-weight:700;font-size:1.05rem;'>NYT Dashboard</div></div>",
    unsafe_allow_html=True,
)

# ---------- Fetch and prepare articles ----------
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

# ---------- Tabs: News + Congress (Bookmarks removed) ----------
tab_news, tab_congress = st.tabs(["News", "Congress"])

# NEWS tab: 3x3 grid with even spacing
with tab_news:
    if not filtered:
        st.info("No articles match your filters.")
    else:
        if layout_choice.startswith("3-up"):
            # Render grid container; each card stretches to equal height
            st.markdown("<div class='three-col-grid'>", unsafe_allow_html=True)
            for art in filtered:
                st.markdown("<div class='article-card'>", unsafe_allow_html=True)

                # Title (linked)
                title_html = f"<div class='heading-box'><a href='{art.get('link')}' target='_blank' rel='noopener noreferrer' style='color:inherit;text-decoration:none;'><strong>{art.get('title') or ''}</strong></a></div>"
                st.markdown(title_html, unsafe_allow_html=True)

                # Meta
                meta = []
                if art.get("source"):
                    meta.append(art["source"])
                if art.get("published_dt"):
                    meta.append(format_dt_for_display(art.get("published_dt"), tz_choice))
                if meta:
                    st.markdown(f"<div style='color:{_saved_prefs.get('muted_color','#8b7a80')};font-size:0.9rem;margin-bottom:8px;'>{' • '.join(meta)}</div>", unsafe_allow_html=True)

                # Image (centered)
                if show_images and art.get("media"):
                    st.markdown(f"<div class='centered-img'><img src='{art.get('media')}' width='{int(image_width)}' style='max-width:100%;height:auto;border-radius:8px;'/></div>", unsafe_allow_html=True)

                # Summary
                if art.get("summary"):
                    st.markdown(f"<div class='summary'>{(art.get('summary') or '')[:240]}{'…' if len(art.get('summary') or '')>240 else ''}</div>", unsafe_allow_html=True)

                # Footer area (keeps spacing even)
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        else:
            # Single column list — keep consistent spacing
            for art in filtered:
                st.markdown("<div class='article-card'>", unsafe_allow_html=True)

                title_html = f"<div class='heading-box' style='width:100%'><a href='{art.get('link')}' target='_blank' rel='noopener noreferrer' style='color:inherit;text-decoration:none;'><strong>{art.get('title') or ''}</strong></a></div>"
                st.markdown(title_html, unsafe_allow_html=True)

                meta = []
                if art.get("source"):
                    meta.append(art["source"])
                if art.get("published_dt"):
                    meta.append(format_dt_for_display(art.get("published_dt"), tz_choice))
                if meta:
                    st.markdown(f"<div style='color:{_saved_prefs.get('muted_color','#8b7a80')};font-size:0.9rem;margin-bottom:8px;'>{' • '.join(meta)}</div>", unsafe_allow_html=True)

                if show_images and art.get("media"):
                    st.markdown(f"<div class='centered-img'><img src='{art.get('media')}' width='{int(image_width)}' style='max-width:100%;height:auto;border-radius:8px;'/></div>", unsafe_allow_html=True)

                if art.get("summary"):
                    st.markdown(f"<div class='summary'>{(art.get('summary') or '')[:480]}{'…' if len(art.get('summary') or '')>480 else ''}</div>", unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

# CONGRESS tab (keeps previous charts)
with tab_congress:
    st.markdown("## Current U.S. Congress Makeup")

    # Static example values (update as desired)
    senate = {"Democrats": 51, "Republicans": 49}
    house = {"Democrats": 213, "Republicans": 222}

    def chamber_chart(data: Dict[str, int], title: str):
        df = pd.DataFrame([{"Party": k, "Seats": v} for k, v in data.items()])
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadius=6)
            .encode(
                x=alt.X("Party:N", sort=None),
                y=alt.Y("Seats:Q"),
                color=alt.Color(
                    "Party:N",
                    scale=alt.Scale(domain=["Democrats", "Republicans"], range=["#4b9bd6", "#e65a3b"])
                ),
                tooltip=[alt.Tooltip("Party:N"), alt.Tooltip("Seats:Q")]
            )
            .properties(width=420, height=320, title=title)
        )
        st.altair_chart(chart, use_container_width=False)

    col1, col2 = st.columns(2)
    with col1:
        chamber_chart(senate, "Senate Composition")
    with col2:
        chamber_chart(house, "House Composition")

    st.markdown("---")
    s_dem = senate.get("Democrats", 0)
    s_rep = senate.get("Republicans", 0)
    h_dem = house.get("Democrats", 0)
    h_rep = house.get("Republicans", 0)

    st.markdown(f"<div style='display:flex;gap:12px;align-items:center;margin-bottom:8px;'><div style='padding:6px 10px;border-radius:999px;background:linear-gradient(90deg,#4b9bd6,#2b7fbf);color:#fff;font-weight:700;'>Senate Democrats: {s_dem}</div><div style='padding:6px 10px;border-radius:999px;background:linear-gradient(90deg,#f28b6b,#e65a3b);color:#fff;font-weight:700;'>Senate Republicans: {s_rep}</div></div>", unsafe_allow_html=True)
    st.markdown(f"<div style='display:flex;gap:12px;align-items:center;margin-bottom:8px;'><div style='padding:6px 10px;border-radius:999px;background:linear-gradient(90deg,#4b9bd6,#2b7fbf);color:#fff;font-weight:700;'>House Democrats: {h_dem}</div><div style='padding:6px 10px;border-radius:999px;background:linear-gradient(90deg,#f28b6b,#e65a3b);color:#fff;font-weight:700;'>House Republicans: {h_rep}</div></div>", unsafe_allow_html=True)

    st.caption("Seat counts are illustrative; update the `senate` and `house` dictionaries with live data as needed.")
