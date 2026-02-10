import streamlit as st

# ============================================================
# NYT Dashboard — with Saved Preferences + Congress Tab
# (Updated: Altair data uses pandas DataFrame to avoid ValueError)
# ============================================================

import os
import json
import time
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

# ---------- Page setup and styling ----------
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

.centered-img { text-align: center; margin-top: 8px; margin-bottom: 12px; }

.three-col-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; align-items: start; }
@media (max-width: 1100px) { .three-col-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 700px) { .three-col-grid { grid-template-columns: 1fr; } }

.brand { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
.brand .logo { width:40px;height:40px;border-radius:8px;background:linear-gradient(180deg,#ffb6d5,#ff8fc2);display:flex;align-items:center;justify-content:center;color:white;font-weight:800;font-size:16px; }

.congress-row { display:flex; gap:12px; align-items:center; margin-bottom:8px; }
.party-pill { padding:6px 10px; border-radius:999px; color:#fff; font-weight:700; font-family:'Inter',sans-serif; }
.dem { background: linear-gradient(90deg,#4b9bd6,#2b7fbf); }
.rep { background: linear-gradient(90deg,#f28b6b,#e65a3b); }
.ind { background: linear-gradient(90deg,#9b9b9b,#6f6f6f); }

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
<div class='brand'>
  <div class='logo'>NY</div>
  <div style='font-size:1.2rem;font-weight:700;'>NYT Dashboard</div>
</div>
""", unsafe_allow_html=True)

# ---------- Fetch Articles ----------
feed_url = NYT_FEEDS.get(feed_choice, NYT_FEEDS["Top Stories"])
articles = fetch_rss(feed_url)[:num_articles]

# ---------- Tabs: News + Congress ----------
tab_news, tab_congress = st.tabs(["News", "Congress"])

# -----------------------
# NEWS TAB
# -----------------------
with tab_news:
    if layout_choice == "3-up grid":
        st.markdown("<div class='three-col-grid'>", unsafe_allow_html=True)
        for art in articles:
            st.markdown("<div class='article-card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='heading-box'>{art.get('title') or ''}</div>", unsafe_allow_html=True)

            if show_images and art.get("media"):
                try:
                    st.markdown(f"<div class='centered-img'><img src='{art.get('media')}' width='{int(image_width)}' style='max-width:100%;height:auto;border-radius:8px;'/></div>", unsafe_allow_html=True)
                except Exception:
                    pass

            if art.get("summary"):
                st.write((art.get("summary") or "")[:250] + ("…" if len(art.get("summary") or "") > 250 else ""))

            st.markdown(
                f"<div style='display:flex;justify-content:center;margin-top:10px;'><button class='open-button' onclick=\"window.location.href='{art.get('link')}'\">Open</button></div>",
                unsafe_allow_html=True,
            )

            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    else:
        for art in articles:
            st.markdown("<div class='article-card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='heading-box'>{art.get('title') or ''}</div>", unsafe_allow_html=True)

            if show_images and art.get("media"):
                try:
                    st.markdown(f"<div class='centered-img'><img src='{art.get('media')}' width='{int(image_width)}' style='max-width:100%;height:auto;border-radius:8px;'/></div>", unsafe_allow_html=True)
                except Exception:
                    pass

            if art.get("summary"):
                st.write((art.get("summary") or "")[:400] + ("…" if len(art.get("summary") or "") > 400 else ""))

            st.markdown(
                f"<div style='display:flex;justify-content:center;margin-top:10px;'><button class='open-button' onclick=\"window.location.href='{art.get('link')}'\">Open</button></div>",
                unsafe_allow_html=True,
            )

            st.markdown("</div>", unsafe_allow_html=True)

# -----------------------
# CONGRESS TAB
# -----------------------
with tab_congress:
    st.markdown("## Current U.S. Congress Makeup")

    # Example static values (update as needed)
    senate = {
        "Democrats": 51,
        "Republicans": 49,
    }

    house = {
        "Democrats": 213,
        "Republicans": 222,
    }

    def chamber_chart(data: Dict[str, int], title: str):
        # Use pandas DataFrame so Altair can infer types
        df = pd.DataFrame([{"Party": k, "Seats": v} for k, v in data.items()])

        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadius=6)
            .encode(
                x=alt.X("Party:N", sort=None),
                y=alt.Y("Seats:Q"),
                color=alt.Color(
                    "Party:N",
                    scale=alt.Scale(
                        domain=["Democrats", "Republicans"],
                        range=["#4b9bd6", "#e65a3b"]
                    )
                ),
                tooltip=[alt.Tooltip("Party:N"), alt.Tooltip("Seats:Q")]
            )
            .properties(width=420, height=320, title=title)
        )
        st.altair_chart(chart, use_container_width=False)

    # Render charts side by side if space allows
    col1, col2 = st.columns(2)
    with col1:
        chamber_chart(senate, "Senate Composition")
    with col2:
        chamber_chart(house, "House Composition")

    # Simple numeric summary and party pills
    st.markdown("---")
    st.markdown("### Quick Summary")
    s_dem = senate.get("Democrats", 0)
    s_rep = senate.get("Republicans", 0)
    h_dem = house.get("Democrats", 0)
    h_rep = house.get("Republicans", 0)

    st.markdown(f"<div class='congress-row'><div class='party-pill dem'>Senate Democrats: {s_dem}</div><div class='party-pill rep'>Senate Republicans: {s_rep}</div></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='congress-row'><div class='party-pill dem'>House Democrats: {h_dem}</div><div class='party-pill rep'>House Republicans: {h_rep}</div></div>", unsafe_allow_html=True)

    st.caption("Seat counts are illustrative; update the `senate` and `house` dictionaries with live data as needed.")

# ---------- End of file ----------
