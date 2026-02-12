import streamlit as st

import streamlit as st

import streamlit as st
import feedparser
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import re
from textblob import TextBlob
import time

# Page config
st.set_page_config(
    page_title="NYT Politics Dashboard",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for wine red theme and enhanced styling
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@400;600&display=swap');
    
    .main {
        padding: 0rem 1rem;
        background: linear-gradient(135deg, #fafafa 0%, #f5f0f0 100%);
    }
    
    .stMetric {
        background: linear-gradient(135deg, #8B0000 0%, #a01010 100%);
        color: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(139, 0, 0, 0.2);
        border: none;
    }
    
    .stMetric label {
        color: #ffd6d6 !important;
        font-weight: 600;
    }
    
    .stMetric [data-testid="stMetricValue"] {
        color: white !important;
        font-size: 2rem !important;
    }
    
    .headline-card {
        background: white;
        padding: 25px;
        border-radius: 15px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        margin-bottom: 20px;
        border-left: 6px solid #8B0000;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .headline-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 4px;
        background: linear-gradient(90deg, #8B0000 0%, #DC143C 50%, #8B0000 100%);
    }
    
    .headline-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 30px rgba(139, 0, 0, 0.15);
    }
    
    .headline-title {
        font-size: 20px;
        font-weight: 700;
        color: #1a1a1a;
        margin-bottom: 12px;
        line-height: 1.4;
        font-family: 'Inter', sans-serif;
    }
    
    .headline-meta {
        font-size: 13px;
        color: #666;
        margin-bottom: 12px;
        display: flex;
        gap: 15px;
        flex-wrap: wrap;
    }
    
    .meta-item {
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }
    
    .sentiment-positive {
        color: #2d8659;
        font-weight: bold;
        background: #e6f7ef;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 12px;
    }
    
    .sentiment-negative {
        color: #c41e3a;
        font-weight: bold;
        background: #fde8eb;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 12px;
    }
    
    .sentiment-neutral {
        color: #5a5a5a;
        font-weight: bold;
        background: #f0f0f0;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 12px;
    }
    
    .summary-box {
        background: linear-gradient(135deg, #8B0000 0%, #6b0000 100%);
        color: white;
        padding: 30px;
        border-radius: 20px;
        box-shadow: 0 8px 30px rgba(139, 0, 0, 0.3);
        margin: 20px 0;
        border: 2px solid #a01010;
    }
    
    .summary-title {
        font-family: 'Playfair Display', serif;
        font-size: 28px;
        font-weight: 700;
        margin-bottom: 20px;
        color: #ffd6d6;
        text-align: center;
    }
    
    .summary-content {
        font-size: 16px;
        line-height: 1.8;
        color: #fff;
        font-family: 'Inter', sans-serif;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background: linear-gradient(135deg, #fafafa 0%, #f5f0f0 100%);
        padding: 10px;
        border-radius: 15px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: white;
        border-radius: 10px;
        color: #8B0000;
        font-weight: 600;
        padding: 10px 20px;
        border: 2px solid transparent;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #8B0000 0%, #a01010 100%);
        color: white;
        border: 2px solid #DC143C;
    }
    
    h1, h2, h3 {
        font-family: 'Playfair Display', serif;
        color: #8B0000;
    }
    
    .stButton button {
        background: linear-gradient(135deg, #8B0000 0%, #a01010 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 10px 25px;
        font-weight: 600;
        box-shadow: 0 4px 15px rgba(139, 0, 0, 0.2);
        transition: all 0.3s ease;
    }
    
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(139, 0, 0, 0.3);
    }
    
    .insight-card {
        background: linear-gradient(135deg, #fff9f9 0%, #ffffff 100%);
        padding: 20px;
        border-radius: 15px;
        border: 2px solid #ffebeb;
        box-shadow: 0 2px 10px rgba(139, 0, 0, 0.05);
    }
    
    .stat-badge {
        display: inline-block;
        background: linear-gradient(135deg, #8B0000 0%, #a01010 100%);
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 14px;
        box-shadow: 0 2px 8px rgba(139, 0, 0, 0.2);
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_nyt_politics_feed():
    """Fetch NYT Politics RSS feed"""
    try:
        # NYT Politics RSS feed
        feed_url = "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"
        feed = feedparser.parse(feed_url)
        
        articles = []
        for entry in feed.entries:
            article = {
                'title': entry.get('title', 'No title'),
                'link': entry.get('link', ''),
                'published': entry.get('published', ''),
                'summary': entry.get('summary', ''),
                'published_parsed': entry.get('published_parsed', None)
            }
            articles.append(article)
        
        return articles, feed.feed.get('title', 'NYT Politics')
    except Exception as e:
        st.error(f"Error fetching feed: {str(e)}")
        return [], "Error"

def analyze_sentiment(text):
    """Analyze sentiment of text using TextBlob"""
    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        
        if polarity > 0.1:
            return 'Positive', polarity
        elif polarity < -0.1:
            return 'Negative', polarity
        else:
            return 'Neutral', polarity
    except:
        return 'Neutral', 0.0

def extract_keywords(articles, top_n=20):
    """Extract common keywords from headlines"""
    all_text = ' '.join([article['title'] for article in articles])
    # Remove common words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                  'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
                  'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                  'could', 'should', 'may', 'might', 'can', 'after', 'over', 'says',
                  'new', 'how', 'what', 'when', 'where', 'who', 'why', 'it', 'its'}
    
    words = re.findall(r'\b[a-z]{4,}\b', all_text.lower())
    words = [w for w in words if w not in stop_words]
    
    return Counter(words).most_common(top_n)

def categorize_article(title):
    """Categorize article based on keywords in title"""
    title_lower = title.lower()
    
    categories = {
        '🏛️ Legislation': ['bill', 'senate', 'congress', 'house', 'legislation', 'law', 'vote', 'passes'],
        '🗳️ Elections': ['election', 'campaign', 'ballot', 'primary', 'candidate', 'voter'],
        '🌍 International': ['foreign', 'international', 'china', 'russia', 'ukraine', 'israel', 'gaza', 'war'],
        '💰 Economy': ['economy', 'inflation', 'budget', 'spending', 'tax', 'debt', 'financial'],
        '⚖️ Judicial': ['court', 'supreme', 'judge', 'ruling', 'legal', 'justice'],
        '🏛️ Executive': ['president', 'white house', 'administration', 'executive', 'biden', 'trump'],
        '🏥 Healthcare': ['healthcare', 'medicaid', 'medicare', 'health', 'medical'],
        '🌱 Environment': ['climate', 'environment', 'energy', 'emissions', 'green'],
        '🔒 Security': ['security', 'defense', 'military', 'border', 'immigration', 'police'],
    }
    
    for category, keywords in categories.items():
        if any(keyword in title_lower for keyword in keywords):
            return category
    
    return '📰 General'

def extract_entities(articles):
    """Extract key political entities (people, places, orgs) from headlines"""
    all_text = ' '.join([a['title'] for a in articles])
    
    # Common politicians and figures
    politicians = {
        'Trump': 0, 'Biden': 0, 'Harris': 0, 'Vance': 0, 'Obama': 0,
        'Pelosi': 0, 'McCarthy': 0, 'McConnell': 0, 'Schumer': 0,
        'DeSantis': 0, 'Newsom': 0, 'Pence': 0, 'Sanders': 0,
        'AOC': 0, 'Ocasio-Cortez': 0, 'Warren': 0, 'Cruz': 0
    }
    
    # Countries and regions
    locations = {
        'China': 0, 'Russia': 0, 'Ukraine': 0, 'Israel': 0, 'Gaza': 0,
        'Iran': 0, 'Mexico': 0, 'Europe': 0, 'Asia': 0, 'Middle East': 0
    }
    
    # Organizations
    organizations = {
        'GOP': 0, 'Republican': 0, 'Democrat': 0, 'Democratic': 0,
        'Senate': 0, 'House': 0, 'Congress': 0, 'Supreme Court': 0,
        'White House': 0, 'Pentagon': 0, 'FBI': 0, 'CIA': 0, 'NATO': 0
    }
    
    # Count mentions
    for entity in politicians:
        politicians[entity] = len(re.findall(rf'\b{entity}\b', all_text, re.IGNORECASE))
    
    for entity in locations:
        locations[entity] = len(re.findall(rf'\b{entity}\b', all_text, re.IGNORECASE))
    
    for entity in organizations:
        organizations[entity] = len(re.findall(rf'\b{entity}\b', all_text, re.IGNORECASE))
    
    # Filter out zero mentions and sort
    politicians = {k: v for k, v in sorted(politicians.items(), key=lambda x: x[1], reverse=True) if v > 0}
    locations = {k: v for k, v in sorted(locations.items(), key=lambda x: x[1], reverse=True) if v > 0}
    organizations = {k: v for k, v in sorted(organizations.items(), key=lambda x: x[1], reverse=True) if v > 0}
    
    return politicians, locations, organizations

def extract_main_topic(title):
    """Extract the main topic from headline for search"""
    # Remove common political phrases
    cleaned = title
    remove_phrases = ['Trump', 'Biden', 'says', 'plans to', 'wants to', 'will', 'could', 'may']
    
    # Extract key noun phrases (simplified)
    words = title.split()
    if len(words) > 4:
        # Take middle portion as likely to contain the main topic
        topic = ' '.join(words[1:4])
    else:
        topic = ' '.join(words[:3])
    
    return topic

@st.cache_data(ttl=1800)  # Cache for 30 minutes
def generate_summary(articles):
    """Generate intelligent summary of today's headlines"""
    try:
        # Get today's articles
        today = datetime.now().date()
        today_articles = []
        
        for article in articles[:20]:
            if article['published_parsed']:
                article_date = datetime(*article['published_parsed'][:6]).date()
                if article_date == today:
                    today_articles.append(article)
        
        if not today_articles:
            today_articles = articles[:15]
        
        # Analyze sentiment distribution
        positive = sum(1 for a in today_articles if a.get('sentiment') == 'Positive')
        negative = sum(1 for a in today_articles if a.get('sentiment') == 'Negative')
        neutral = sum(1 for a in today_articles if a.get('sentiment') == 'Neutral')
        
        # Extract key topics
        all_text = ' '.join([a['title'] for a in today_articles])
        keywords = extract_keywords(today_articles, top_n=8)
        top_topics = [kw[0] for kw in keywords[:5]]
        
        # Identify key themes from headlines
        themes = []
        theme_words = {
            'election': ['election', 'vote', 'campaign', 'ballot', 'primary'],
            'legislation': ['bill', 'senate', 'congress', 'house', 'legislation', 'law'],
            'international': ['foreign', 'international', 'china', 'russia', 'ukraine', 'israel'],
            'economic': ['economy', 'inflation', 'budget', 'spending', 'tax'],
            'judicial': ['court', 'supreme', 'judge', 'ruling', 'legal'],
            'executive': ['president', 'white house', 'administration', 'executive']
        }
        
        for theme, words in theme_words.items():
            if any(word in all_text.lower() for word in words):
                themes.append(theme)
        
        # Generate summary
        sentiment_tone = "mixed" if abs(positive - negative) < 3 else ("positive" if positive > negative else "negative")
        
        summary_parts = []
        
        # Opening
        summary_parts.append(f"Today's political coverage features {len(today_articles)} articles with a {sentiment_tone} overall tone.")
        
        # Key topics
        if top_topics:
            topics_str = ", ".join([f"**{t}**" for t in top_topics[:3]])
            summary_parts.append(f"The dominant themes include {topics_str}.")
        
        # Sentiment breakdown
        if positive > 0 or negative > 0:
            summary_parts.append(f"Sentiment analysis shows {positive} positive, {neutral} neutral, and {negative} negative headlines.")
        
        # Theme analysis
        if themes:
            theme_str = ", ".join([t.capitalize() for t in themes[:3]])
            summary_parts.append(f"Major areas of focus: {theme_str}.")
        
        # Top headlines
        top_3 = today_articles[:3]
        summary_parts.append(f"\n\n**Top Stories:**")
        for i, article in enumerate(top_3, 1):
            summary_parts.append(f"\n{i}. {article['title']}")
        
        summary = " ".join(summary_parts)
        
        return summary, len(today_articles)
    
    except Exception as e:
        return f"Analyzing {len(articles)} recent political headlines. Use the tabs below to explore sentiment analysis, trending keywords, and detailed insights.", len(articles)

def main():
    # Initialize session state
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
    
    # Header with wine red theme
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h1 style="font-family: 'Playfair Display', serif; font-size: 48px; color: #8B0000; margin-bottom: 5px;">
                📰 NYT Politics Dashboard
            </h1>
            <p style="font-size: 18px; color: #666; font-style: italic;">
                Real-time intelligence on American politics
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.markdown('<h2 style="color: #8B0000;">⚙️ Dashboard Controls</h2>', unsafe_allow_html=True)
    
    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
    if auto_refresh:
        time.sleep(30)
        st.rerun()
    
    # Manual refresh button
    if st.sidebar.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()
    
    # Fetch data FIRST
    with st.spinner("Fetching latest headlines..."):
        articles, feed_title = fetch_nyt_politics_feed()
    
    if not articles:
        st.warning("No articles found. Please check your connection.")
        return
    
    # Add sentiment analysis and categorization
    for article in articles:
        sentiment, polarity = analyze_sentiment(article['title'])
        article['sentiment'] = sentiment
        article['polarity'] = polarity
        article['category'] = categorize_article(article['title'])
    
    # NOW add filters in sidebar (after articles are processed)
    st.sidebar.markdown('<h3 style="color: #8B0000;">🔍 Filters</h3>', unsafe_allow_html=True)
    
    search_query = st.sidebar.text_input("🔎 Search headlines", "")
    
    # Category filter
    all_categories = sorted(list(set([a.get('category', '📰 General') for a in articles])))
    selected_categories = st.sidebar.multiselect(
        "📑 Filter by category",
        all_categories,
        default=all_categories
    )
    
    sentiment_filter = st.sidebar.multiselect(
        "😊 Filter by sentiment",
        ["Positive", "Neutral", "Negative"],
        default=["Positive", "Neutral", "Negative"]
    )
    
    hours_back = st.sidebar.slider("⏰ Show articles from last N hours", 1, 168, 24)
    
    # Breaking news toggle
    show_breaking = st.sidebar.checkbox("🚨 Breaking News Only (last 3 hours)", value=False)
    
    # Filter by time
    if show_breaking:
        cutoff_time = datetime.now() - timedelta(hours=3)
    else:
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
    
    filtered_articles = []
    for article in articles:
        if article['published_parsed']:
            article_time = datetime(*article['published_parsed'][:6])
            if article_time >= cutoff_time:
                filtered_articles.append(article)
        else:
            filtered_articles.append(article)
    
    # Filter by search query
    if search_query:
        filtered_articles = [
            a for a in filtered_articles 
            if search_query.lower() in a['title'].lower() or 
               search_query.lower() in a.get('summary', '').lower()
        ]
    
    # Filter by category
    filtered_articles = [a for a in filtered_articles if a.get('category', '📰 General') in selected_categories]
    
    # Filter by sentiment
    filtered_articles = [a for a in filtered_articles if a['sentiment'] in sentiment_filter]
    
    # Metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("📰 Total Articles", len(filtered_articles))
    
    with col2:
        positive_count = sum(1 for a in filtered_articles if a['sentiment'] == 'Positive')
        st.metric("😊 Positive", positive_count)
    
    with col3:
        negative_count = sum(1 for a in filtered_articles if a['sentiment'] == 'Negative')
        st.metric("😞 Negative", negative_count)
    
    with col4:
        neutral_count = sum(1 for a in filtered_articles if a['sentiment'] == 'Neutral')
        st.metric("😐 Neutral", neutral_count)
    
    with col5:
        # Count breaking news (last 3 hours)
        breaking_cutoff = datetime.now() - timedelta(hours=3)
        breaking_count = sum(1 for a in filtered_articles 
                           if a.get('published_parsed') and 
                           datetime(*a['published_parsed'][:6]) >= breaking_cutoff)
        st.metric("🚨 Breaking", breaking_count)
    
    # Category distribution
    st.markdown("---")
    st.markdown('<h3 style="color: #8B0000; text-align: center;">📊 Coverage by Category</h3>', 
                unsafe_allow_html=True)
    
    category_counts = Counter([a.get('category', '📰 General') for a in filtered_articles])
    
    cols = st.columns(min(len(category_counts), 5))
    for idx, (category, count) in enumerate(category_counts.most_common(5)):
        with cols[idx]:
            st.markdown(f"""
                <div style="text-align: center; padding: 10px; background: linear-gradient(135deg, #fff9f9 0%, #ffffff 100%);
                            border-radius: 10px; border: 2px solid #ffebeb;">
                    <div style="font-size: 24px;">{category.split()[0]}</div>
                    <div style="font-size: 20px; font-weight: 700; color: #8B0000;">{count}</div>
                    <div style="font-size: 12px; color: #666;">{category.split(' ', 1)[1] if ' ' in category else 'Articles'}</div>
                </div>
            """, unsafe_allow_html=True)
    
    # AI Summary Section
    st.markdown("---")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown('<div class="summary-title">📋 Daily Briefing</div>', unsafe_allow_html=True)
    
    with col2:
        generate_new = st.button("🔄 Regenerate Summary", key="regen_summary")
        if generate_new:
            st.cache_data.clear()
    
    with st.spinner("Generating daily briefing from latest headlines..."):
        summary, article_count = generate_summary(articles)
    
    st.markdown(f"""
        <div class="summary-box">
            <div class="summary-content">
                {summary}
            </div>
            <div style="text-align: right; margin-top: 20px; font-size: 14px; opacity: 0.9;">
                <span class="stat-badge">Based on {article_count} articles</span>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📋 Headlines", "📊 Analytics", "🔤 Keywords", "📈 Trends", "💡 Insights", "👥 Entities"
    ])
    
    with tab1:
        st.markdown('<h2 style="color: #8B0000;">Latest Headlines</h2>', unsafe_allow_html=True)
        
        # Sort options
        sort_by = st.selectbox("Sort by", ["Most Recent", "Sentiment (Positive first)", "Sentiment (Negative first)"])
        
        if sort_by == "Sentiment (Positive first)":
            filtered_articles.sort(key=lambda x: x['polarity'], reverse=True)
        elif sort_by == "Sentiment (Negative first)":
            filtered_articles.sort(key=lambda x: x['polarity'])
        
        # Display articles
        for idx, article in enumerate(filtered_articles):
            sentiment_class = f"sentiment-{article['sentiment'].lower()}"
            pub_time = article['published']
            category = article.get('category', '📰 General')
            
            st.markdown(f"""
                <div class="headline-card">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                        <span class="headline-title">
                            <span style="color: #8B0000; font-weight: 800;">#{idx + 1}</span> {article['title']}
                        </span>
                        <span style="background: linear-gradient(135deg, #8B0000 0%, #a01010 100%); 
                                     color: white; padding: 5px 12px; border-radius: 15px; 
                                     font-size: 12px; white-space: nowrap; margin-left: 10px;">
                            {category}
                        </span>
                    </div>
                    <div class="headline-meta">
                        <span class="meta-item">🕐 {pub_time}</span>
                        <span class="meta-item">
                            💭 Sentiment: <span class="{sentiment_class}">{article['sentiment']}</span>
                        </span>
                        <span class="meta-item" style="color: #8B0000;">
                            📊 Score: {article['polarity']:.3f}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Article actions in columns
            col_a, col_b, col_c = st.columns([1, 1, 2])
            
            with col_a:
                if st.button("📖 Read Article", key=f"read_{idx}"):
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={article["link"]}">', 
                              unsafe_allow_html=True)
                    st.write(f"[Open in new tab]({article['link']})")
            
            with col_b:
                if st.button("🔍 Get Context", key=f"context_{idx}"):
                    st.session_state[f'show_context_{idx}'] = True
            
            # Show context if requested
            if st.session_state.get(f'show_context_{idx}', False):
                with st.spinner("Gathering additional context..."):
                    topic = extract_main_topic(article['title'])
                    
                    # Create search query
                    search_query = f"{topic} politics news"
                    
                    try:
                        # Import web_search here to avoid errors if not available
                        from anthropic import Anthropic
                        
                        # Use a simple contextual summary
                        st.markdown(f"""
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 10px; 
                                    border-left: 4px solid #8B0000; margin: 10px 0;">
                            <h4 style="color: #8B0000; margin-bottom: 10px;">📰 Article Context</h4>
                            <p><strong>Main Topic:</strong> {topic}</p>
                            <p><strong>Category:</strong> {category}</p>
                            <p><strong>Sentiment:</strong> {article['sentiment']} ({article['polarity']:.2f})</p>
                            <p style="margin-top: 10px;">
                                <a href="{article['link']}" target="_blank" 
                                   style="color: #8B0000; text-decoration: underline;">
                                    Read full article on NYT →
                                </a>
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                    except Exception as e:
                        st.info(f"**Topic:** {topic} | **Category:** {category}")
            
            st.markdown("---")
    
    with tab2:
        st.markdown('<h2 style="color: #8B0000;">Sentiment Analysis</h2>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Sentiment pie chart
            sentiment_counts = pd.DataFrame([
                {'Sentiment': 'Positive', 'Count': positive_count},
                {'Sentiment': 'Neutral', 'Count': neutral_count},
                {'Sentiment': 'Negative', 'Count': negative_count}
            ])
            
            fig_pie = px.pie(
                sentiment_counts, 
                values='Count', 
                names='Sentiment',
                title='Sentiment Distribution',
                color='Sentiment',
                color_discrete_map={
                    'Positive': '#2d8659',
                    'Neutral': '#8B8B8B',
                    'Negative': '#8B0000'
                },
                hole=0.4
            )
            fig_pie.update_layout(
                font=dict(family="Inter, sans-serif"),
                title_font=dict(size=20, color='#8B0000', family="Playfair Display, serif")
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # Sentiment polarity distribution
            polarities = [a['polarity'] for a in filtered_articles]
            fig_hist = go.Figure(data=[go.Histogram(
                x=polarities, 
                nbinsx=20,
                marker_color='#8B0000',
                marker_line_color='#6b0000',
                marker_line_width=1.5
            )])
            fig_hist.update_layout(
                title='Sentiment Polarity Distribution',
                xaxis_title='Polarity Score',
                yaxis_title='Number of Articles',
                showlegend=False,
                font=dict(family="Inter, sans-serif"),
                title_font=dict(size=20, color='#8B0000', family="Playfair Display, serif"),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        
        # Timeline view
        if filtered_articles:
            df_timeline = []
            for article in filtered_articles:
                if article['published_parsed']:
                    df_timeline.append({
                        'datetime': datetime(*article['published_parsed'][:6]),
                        'title': article['title'],
                        'sentiment': article['sentiment'],
                        'polarity': article['polarity']
                    })
            
            if df_timeline:
                df_timeline = pd.DataFrame(df_timeline)
                df_timeline['hour'] = df_timeline['datetime'].dt.floor('H')
                
                hourly_sentiment = df_timeline.groupby(['hour', 'sentiment']).size().reset_index(name='count')
                
                fig_timeline = px.bar(
                    hourly_sentiment,
                    x='hour',
                    y='count',
                    color='sentiment',
                    title='Articles Over Time (by Sentiment)',
                    color_discrete_map={
                        'Positive': '#2d8659',
                        'Neutral': '#8B8B8B',
                        'Negative': '#8B0000'
                    }
                )
                fig_timeline.update_layout(
                    font=dict(family="Inter, sans-serif"),
                    title_font=dict(size=20, color='#8B0000', family="Playfair Display, serif"),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_timeline, use_container_width=True)
    
    with tab3:
        st.markdown('<h2 style="color: #8B0000;">Keyword Analysis</h2>', unsafe_allow_html=True)
        
        keywords = extract_keywords(filtered_articles, top_n=30)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Top keywords bar chart
            if keywords:
                kw_df = pd.DataFrame(keywords, columns=['Keyword', 'Frequency'])
                fig_kw = px.bar(
                    kw_df.head(15),
                    x='Frequency',
                    y='Keyword',
                    orientation='h',
                    title='Top 15 Keywords',
                    color='Frequency',
                    color_continuous_scale=['#ffcccc', '#8B0000']
                )
                fig_kw.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    font=dict(family="Inter, sans-serif"),
                    title_font=dict(size=20, color='#8B0000', family="Playfair Display, serif"),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_kw, use_container_width=True)
        
        with col2:
            # Word cloud-style scatter
            if keywords:
                kw_df = pd.DataFrame(keywords[:30], columns=['Keyword', 'Frequency'])
                fig_scatter = px.scatter(
                    kw_df,
                    x=range(len(kw_df)),
                    y='Frequency',
                    text='Keyword',
                    size='Frequency',
                    title='Keyword Bubble View',
                    color='Frequency',
                    color_continuous_scale=['#ffcccc', '#8B0000']
                )
                fig_scatter.update_traces(textposition='top center')
                fig_scatter.update_layout(
                    showlegend=False, 
                    xaxis={'visible': False},
                    font=dict(family="Inter, sans-serif"),
                    title_font=dict(size=20, color='#8B0000', family="Playfair Display, serif"),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_scatter, use_container_width=True)
        
        # Keywords table
        st.subheader("All Keywords")
        if keywords:
            kw_df = pd.DataFrame(keywords, columns=['Keyword', 'Frequency'])
            st.dataframe(kw_df, use_container_width=True)
    
    with tab4:
        st.markdown('<h2 style="color: #8B0000;">Article Trends</h2>', unsafe_allow_html=True)
        
        # Average sentiment over time
        if filtered_articles:
            df_trends = []
            for article in filtered_articles:
                if article['published_parsed']:
                    df_trends.append({
                        'datetime': datetime(*article['published_parsed'][:6]),
                        'polarity': article['polarity']
                    })
            
            if df_trends:
                df_trends = pd.DataFrame(df_trends)
                df_trends = df_trends.sort_values('datetime')
                df_trends['rolling_avg'] = df_trends['polarity'].rolling(window=5, min_periods=1).mean()
                
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(
                    x=df_trends['datetime'],
                    y=df_trends['polarity'],
                    mode='markers',
                    name='Individual Articles',
                    marker=dict(size=8, opacity=0.5, color='#a01010')
                ))
                fig_trend.add_trace(go.Scatter(
                    x=df_trends['datetime'],
                    y=df_trends['rolling_avg'],
                    mode='lines',
                    name='5-Article Moving Average',
                    line=dict(color='#8B0000', width=3)
                ))
                fig_trend.update_layout(
                    title='Sentiment Trend Over Time',
                    xaxis_title='Time',
                    yaxis_title='Sentiment Polarity',
                    hovermode='x unified',
                    font=dict(family="Inter, sans-serif"),
                    title_font=dict(size=20, color='#8B0000', family="Playfair Display, serif"),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_trend, use_container_width=True)
        
        # Publication frequency
        col1, col2 = st.columns(2)
        
        with col1:
            if filtered_articles:
                df_freq = []
                for article in filtered_articles:
                    if article['published_parsed']:
                        df_freq.append({
                            'hour': datetime(*article['published_parsed'][:6]).hour
                        })
                
                if df_freq:
                    df_freq = pd.DataFrame(df_freq)
                    hour_counts = df_freq['hour'].value_counts().sort_index()
                    
                    fig_hours = px.bar(
                        x=hour_counts.index,
                        y=hour_counts.values,
                        title='Articles by Hour of Day',
                        labels={'x': 'Hour', 'y': 'Number of Articles'},
                        color=hour_counts.values,
                        color_continuous_scale=['#ffcccc', '#8B0000']
                    )
                    fig_hours.update_layout(
                        font=dict(family="Inter, sans-serif"),
                        title_font=dict(size=20, color='#8B0000', family="Playfair Display, serif"),
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_hours, use_container_width=True)
    
    with tab5:
        st.markdown('<h2 style="color: #8B0000;">Key Insights</h2>', unsafe_allow_html=True)
        
        # Calculate insights
        avg_polarity = sum(a['polarity'] for a in filtered_articles) / len(filtered_articles) if filtered_articles else 0
        most_positive = max(filtered_articles, key=lambda x: x['polarity']) if filtered_articles else None
        most_negative = min(filtered_articles, key=lambda x: x['polarity']) if filtered_articles else None
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
                <div class="insight-card">
                    <h3 style="color: #8B0000; margin-bottom: 15px;">📊 Sentiment Overview</h3>
                    <p style="font-size: 16px; line-height: 1.8;">
                        The average sentiment polarity across all headlines is 
                        <span class="stat-badge">{:.3f}</span>
                        <br><br>
                        This indicates a <strong>{}</strong> tone overall in today's political coverage.
                    </p>
                </div>
            """.format(avg_polarity, 
                      "positive" if avg_polarity > 0.1 else "negative" if avg_polarity < -0.1 else "neutral"),
                      unsafe_allow_html=True)
            
            if most_positive:
                st.markdown(f"""
                    <div class="insight-card" style="margin-top: 20px;">
                        <h3 style="color: #2d8659; margin-bottom: 15px;">✨ Most Positive Headline</h3>
                        <p style="font-size: 15px; font-weight: 600; color: #1a1a1a;">
                            "{most_positive['title']}"
                        </p>
                        <p style="margin-top: 10px; color: #666;">
                            Polarity Score: <span class="stat-badge" style="background: #2d8659;">
                            {most_positive['polarity']:.3f}</span>
                        </p>
                    </div>
                """, unsafe_allow_html=True)
        
        with col2:
            top_keywords = extract_keywords(filtered_articles, top_n=5)
            keyword_list = ", ".join([f"<strong>{kw[0]}</strong>" for kw in top_keywords])
            
            st.markdown(f"""
                <div class="insight-card">
                    <h3 style="color: #8B0000; margin-bottom: 15px;">🔤 Trending Topics</h3>
                    <p style="font-size: 16px; line-height: 1.8;">
                        The most frequently mentioned keywords today are:<br><br>
                        {keyword_list}
                        <br><br>
                        These topics dominate the current political discourse.
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            if most_negative:
                st.markdown(f"""
                    <div class="insight-card" style="margin-top: 20px;">
                        <h3 style="color: #8B0000; margin-bottom: 15px;">⚠️ Most Negative Headline</h3>
                        <p style="font-size: 15px; font-weight: 600; color: #1a1a1a;">
                            "{most_negative['title']}"
                        </p>
                        <p style="margin-top: 10px; color: #666;">
                            Polarity Score: <span class="stat-badge">{most_negative['polarity']:.3f}</span>
                        </p>
                    </div>
                """, unsafe_allow_html=True)
        
        # Additional insights
        st.markdown("---")
        st.markdown('<h3 style="color: #8B0000; margin-top: 30px;">📈 Coverage Patterns</h3>', 
                   unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            sentiment_ratio = (positive_count / len(filtered_articles) * 100) if filtered_articles else 0
            st.markdown(f"""
                <div class="insight-card" style="text-align: center;">
                    <h4 style="color: #2d8659; margin-bottom: 10px;">Positive Coverage</h4>
                    <p style="font-size: 32px; font-weight: 700; color: #2d8659; margin: 10px 0;">
                        {sentiment_ratio:.1f}%
                    </p>
                    <p style="color: #666; font-size: 14px;">of total articles</p>
                </div>
            """, unsafe_allow_html=True)
        
        with col2:
            neutral_ratio = (neutral_count / len(filtered_articles) * 100) if filtered_articles else 0
            st.markdown(f"""
                <div class="insight-card" style="text-align: center;">
                    <h4 style="color: #8B8B8B; margin-bottom: 10px;">Neutral Coverage</h4>
                    <p style="font-size: 32px; font-weight: 700; color: #8B8B8B; margin: 10px 0;">
                        {neutral_ratio:.1f}%
                    </p>
                    <p style="color: #666; font-size: 14px;">of total articles</p>
                </div>
            """, unsafe_allow_html=True)
        
        with col3:
            negative_ratio = (negative_count / len(filtered_articles) * 100) if filtered_articles else 0
            st.markdown(f"""
                <div class="insight-card" style="text-align: center;">
                    <h4 style="color: #8B0000; margin-bottom: 10px;">Negative Coverage</h4>
                    <p style="font-size: 32px; font-weight: 700; color: #8B0000; margin: 10px 0;">
                        {negative_ratio:.1f}%
                    </p>
                    <p style="color: #666; font-size: 14px;">of total articles</p>
                </div>
            """, unsafe_allow_html=True)
    
    with tab6:
        st.markdown('<h2 style="color: #8B0000;">Entity Tracking</h2>', unsafe_allow_html=True)
        st.markdown("Track mentions of key political figures, locations, and organizations in today's headlines.")
        
        # Extract entities
        politicians, locations, organizations = extract_entities(filtered_articles)
        
        # Display in three columns
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown('<h3 style="color: #8B0000;">👤 Political Figures</h3>', unsafe_allow_html=True)
            
            if politicians:
                # Create bar chart
                pol_df = pd.DataFrame(list(politicians.items())[:10], columns=['Name', 'Mentions'])
                fig_pol = px.bar(
                    pol_df,
                    x='Mentions',
                    y='Name',
                    orientation='h',
                    title='Top Politicians Mentioned',
                    color='Mentions',
                    color_continuous_scale=['#ffcccc', '#8B0000']
                )
                fig_pol.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    font=dict(family="Inter, sans-serif"),
                    title_font=dict(size=16, color='#8B0000'),
                    height=400,
                    showlegend=False
                )
                st.plotly_chart(fig_pol, use_container_width=True)
                
                # List view
                for name, count in list(politicians.items())[:5]:
                    st.markdown(f"""
                        <div style="background: #f8f9fa; padding: 10px; margin: 5px 0; 
                                    border-radius: 8px; display: flex; justify-content: space-between;">
                            <span style="font-weight: 600;">{name}</span>
                            <span class="stat-badge" style="font-size: 12px;">{count} mentions</span>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No political figures mentioned in filtered articles")
        
        with col2:
            st.markdown('<h3 style="color: #8B0000;">🌍 Locations</h3>', unsafe_allow_html=True)
            
            if locations:
                # Create bar chart
                loc_df = pd.DataFrame(list(locations.items())[:10], columns=['Location', 'Mentions'])
                fig_loc = px.bar(
                    loc_df,
                    x='Mentions',
                    y='Location',
                    orientation='h',
                    title='Top Locations Mentioned',
                    color='Mentions',
                    color_continuous_scale=['#ffcccc', '#8B0000']
                )
                fig_loc.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    font=dict(family="Inter, sans-serif"),
                    title_font=dict(size=16, color='#8B0000'),
                    height=400,
                    showlegend=False
                )
                st.plotly_chart(fig_loc, use_container_width=True)
                
                # List view
                for name, count in list(locations.items())[:5]:
                    st.markdown(f"""
                        <div style="background: #f8f9fa; padding: 10px; margin: 5px 0; 
                                    border-radius: 8px; display: flex; justify-content: space-between;">
                            <span style="font-weight: 600;">{name}</span>
                            <span class="stat-badge" style="font-size: 12px;">{count} mentions</span>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No locations mentioned in filtered articles")
        
        with col3:
            st.markdown('<h3 style="color: #8B0000;">🏛️ Organizations</h3>', unsafe_allow_html=True)
            
            if organizations:
                # Create bar chart
                org_df = pd.DataFrame(list(organizations.items())[:10], columns=['Organization', 'Mentions'])
                fig_org = px.bar(
                    org_df,
                    x='Mentions',
                    y='Organization',
                    orientation='h',
                    title='Top Organizations Mentioned',
                    color='Mentions',
                    color_continuous_scale=['#ffcccc', '#8B0000']
                )
                fig_org.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    font=dict(family="Inter, sans-serif"),
                    title_font=dict(size=16, color='#8B0000'),
                    height=400,
                    showlegend=False
                )
                st.plotly_chart(fig_org, use_container_width=True)
                
                # List view
                for name, count in list(organizations.items())[:5]:
                    st.markdown(f"""
                        <div style="background: #f8f9fa; padding: 10px; margin: 5px 0; 
                                    border-radius: 8px; display: flex; justify-content: space-between;">
                            <span style="font-weight: 600;">{name}</span>
                            <span class="stat-badge" style="font-size: 12px;">{count} mentions</span>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No organizations mentioned in filtered articles")
        
        # Entity co-occurrence insights
        st.markdown("---")
        st.markdown('<h3 style="color: #8B0000;">🔗 Quick Insights</h3>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if politicians:
                top_politician = list(politicians.items())[0]
                st.markdown(f"""
                    <div class="insight-card">
                        <h4 style="color: #8B0000;">Most Mentioned Figure</h4>
                        <p style="font-size: 24px; font-weight: 700; color: #8B0000; margin: 10px 0;">
                            {top_politician[0]}
                        </p>
                        <p>Mentioned in <strong>{top_politician[1]}</strong> headlines</p>
                    </div>
                """, unsafe_allow_html=True)
        
        with col2:
            if locations:
                top_location = list(locations.items())[0]
                st.markdown(f"""
                    <div class="insight-card">
                        <h4 style="color: #8B0000;">Top Location in Focus</h4>
                        <p style="font-size: 24px; font-weight: 700; color: #8B0000; margin: 10px 0;">
                            {top_location[0]}
                        </p>
                        <p>Mentioned in <strong>{top_location[1]}</strong> headlines</p>
                    </div>
                """, unsafe_allow_html=True)
    
    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.sidebar.markdown(f"**Feed source:** {feed_title}")
    
    # Export functionality
    st.sidebar.markdown('<h3 style="color: #8B0000;">📥 Export Data</h3>', unsafe_allow_html=True)
    if st.sidebar.button("Download as CSV"):
        df_export = pd.DataFrame([
            {
                'Title': a['title'],
                'Link': a['link'],
                'Published': a['published'],
                'Sentiment': a['sentiment'],
                'Polarity': a['polarity']
            }
            for a in filtered_articles
        ])
        csv = df_export.to_csv(index=False)
        st.sidebar.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"nyt_politics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
