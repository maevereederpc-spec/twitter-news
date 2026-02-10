import streamlit as st

# ============================================================
# NYT Dashboard — with Saved Preferences + Congress Tab
# ============================================================

import os
import json
import time
import re
from typing import List, Dict, Optional
import feedparser
import requests
from bs4 import BeautifulSoup
import streamlit as st
from datetime import datetime, timedelta, timezone
from collections import Counter
import altair as alt

# ---------- Timezone support ----------
try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except Exception:
    ZONEINFO_AVAILABLE = False
    try:
        import pytz
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

# ---------- Load & Save Preferences ----------
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

prefs = load_prefs()

# ---------- RSS Fetch ----------
@st.cache_data(ttl=CACHE_TTL)
def fetch_rss(url: str):
    parsed = feedparser.parse(url)
    items = []
    for entry in parsed.entries:
        items.append({
            "title": entry.get("title"),
            "link": entry.get("link"),
            "summary": entry.get("summary") or entry.get("description"),
            "published": entry.get("published"),
            "media": extract_media(entry),
            "source": parsed.feed.get("title"),
        })
    return items

def extract_media(entry):
    media = entry.get("media_content") or entry.get("media_thumbnail")
    if media and isinstance(media, list):
        return media[0].get("url")
    return None

# ---------- UI Styling ----------
st.set_page_config(page_title="NYT Dashboard", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: #fff7fb;
}

.article-card {
    background: #ffffff;
    border-radius: 14px;
    padding: 18px;
    border: 1px solid rgba(0,0,0,0.08);
    box-shadow: 0 6px 18px rgba(0,0,0,0.06);
    transition: 0.15s ease;
}
.article-card:hover {
    transform: translateY(-3px);
}

.open-button {
    background: linear-gradient(180deg, #ff8fc2, #ff5fae);
    color: white;
    border: none;
    padding: 10px 16px;
    border-radius: 999px;
    font-weight: 700;
    cursor: pointer;
    font-size: 0.95rem;
}
.open-button:hover {
    transform: translateY(-2px);
}

.heading-box {
    background: rgba(255,182,213,0.18);
    padding: 8px 12px;
    border-radius: 8px;
    font-weight: 700;
}

</style>
""", unsafe_allow_html=True)

# ---------- Sidebar ----------
st.sidebar.markdown("## NYT Dashboard Settings")

feed_choice = st.sidebar.selectbox(
    "NYT Feed",
    ["Top Stories", "Politics"],
    index=["Top Stories", "Politics"].index(prefs.get("feed_choice", "Top Stories"))
)

num_articles = st.sidebar.slider(
    "Max Articles",
    5, 200,
    prefs.get("num_articles", 60)
)

image_width = st.sidebar.number_input(
    "Image Width",
    80, 400,
    prefs.get("image_width", DEFAULT_THUMB_WIDTH)
)

layout_choice = st.sidebar.selectbox(
    "Layout",
    ["3-up grid", "Single column"],
    index=["3-up grid", "Single column"].index(prefs.get("layout_choice", "3-up grid"))
)

show_images = st.sidebar.checkbox(
    "Show images",
    value=prefs.get("show_images", True)
)

tz_choice = st.sidebar.selectbox(
    "Timezone",
    ["System", "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific"],
    index=["System", "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific"].index(
        prefs.get("tz_choice", "System")
    )
)

# Save preferences button
if st.sidebar.button("Save Preferences"):
    save_prefs({
        "feed_choice": feed_choice,
        "num_articles": num_articles,
        "image_width": image_width,
        "layout_choice": layout_choice,
        "show_images": show_images,
        "tz_choice": tz_choice,
    })
    st.sidebar.success("Preferences saved!")

# ---------- Header ----------
st.markdown("""
<div style='display:flex;align-items:center;gap:12px;margin-bottom:12px;'>
    <div style='width:40px;height:40px;border-radius:8px;background:linear-gradient(180deg,#ffb6d5,#ff8fc2);display:flex;align-items:center;justify-content:center;color:white;font-weight:800;font-size:16px;'>NY</div>
    <div style='font-size:1.2rem;font-weight:700;'>NYT Dashboard</div>
</div>
""", unsafe_allow_html=True)

# ---------- Fetch Articles ----------
feed_url = NYT_FEEDS[feed_choice]
articles = fetch_rss(feed_url)[:num_articles]

# ---------- Tabs ----------
tab_news, tab_congress = st.tabs(["News", "Congress"])

# ============================================================
# NEWS TAB
# ============================================================
with tab_news:
    if layout_choice == "3-up grid":
        cols = st.columns(3)
        for i, art in enumerate(articles):
            with cols[i % 3]:
                st.markdown("<div class='article-card'>", unsafe_allow_html=True)
                st.markdown(f"<div class='heading-box'>{art['title']}</div>", unsafe_allow_html=True)

                if show_images and art["media"]:
                    st.image(art["media"], width=image_width)

                if art["summary"]:
                    st.write(art["summary"][:250] + "…")

                st.markdown(
                    f"<button class='open-button' onclick=\"window.location.href='{art['link']}'\">Open</button>",
                    unsafe_allow_html=True
                )

                st.markdown("</div>", unsafe_allow_html=True)

    else:
        for art in articles:
            st.markdown("<div class='article-card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='heading-box'>{art['title']}</div>", unsafe_allow_html=True)

            if show_images and art["media"]:
                st.image(art["media"], width=image_width)

            if art["summary"]:
                st.write(art["summary"][:400] + "…")

            st.markdown(
                f"<button class='open-button' onclick=\"window.location.href='{art['link']}'\">Open</button>",
                unsafe_allow_html=True
            )

            st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# CONGRESS TAB
# ============================================================
with tab_congress:
    st.markdown("## Current U.S. Congress Makeup")

    # These values reflect the 119th Congress (2025–2027)
    senate = {
        "Democrats": 51,
        "Republicans": 49,
    }

    house = {
        "Democrats": 213,
        "Republicans": 222,
    }

    def chamber_chart(data: Dict, title: str):
        df = [{"Party": k, "Seats": v} for k, v in data.items()]
        chart = (
            alt.Chart(alt.Data(values=df))
            .mark_bar(cornerRadius=6)
            .encode(
                x=alt.X("Party:N", sort=None),
                y="Seats:Q",
                color=alt.Color(
                    "Party:N",
                    scale=alt.Scale(
                        domain=["Democrats", "Republicans"],
                        range=["#4b9bd6", "#e65a3b"]
                    )
                ),
                tooltip=["Party", "Seats"]
            )
            .properties(width=400, height=300, title=title)
        )
        st.altair_chart(chart, use_container_width=False)

    chamber_chart(senate, "Senate Composition")
    chamber_chart(house, "House Composition")

    st.caption("Data reflects the current 119th U.S. Congress (2025–2027).")
