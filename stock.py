import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

# ==========================================
# 1. 常數與股票名單設定
# ==========================================
US_STOCKS = {
    "NVIDIA (NVDA)": "NVDA", 
    "Apple (AAPL)": "AAPL", 
    "Microsoft (MSFT)": "MSFT",
    "Tesla (TSLA)": "TSLA", 
    "Amazon (AMZN)": "AMZN", 
    "Alphabet / Google (GOOGL)": "GOOGL",
    "Meta (META)": "META", 
    "Broadcom (AVGO)": "AVGO", 
    "Berkshire Hathaway (BRK-B)": "BRK-B",
    "Eli Lilly (LLY)": "LLY"
}

TW_STOCKS = {
    "台積電 (2330.TW)": "2330.TW", 
    "鴻海 (2317.TW)": "2317.TW", 
    "聯發科 (2454.TW)": "2454.TW",
    "廣達 (2382.TW)": "2382.TW", 
    "台達電 (2308.TW)": "2308.TW", 
    "富邦金 (2881.TW)": "2881.TW",
    "國泰金 (2882.TW)": "2882.TW", 
    "中信金 (2891.TW)": "2891.TW", 
    "中華電 (2412.TW)": "2412.TW",
    "緯創 (3231.TW)": "3231.TW"
}

# ==========================================
# 2. 核心計算函式與資料快取機制
# ==========================================
@st.cache_data(ttl=3600)
def fetch_stock_data(ticker, start, end):
    """快取機制，相同代碼一小時內不用重新呼叫 API"""
    stock = yf.Ticker(ticker)
    df = stock.history(start=start, end=end, interval="1d")
    if not df.empty:
        df.index = df.index.tz_localize(None)
    return df

@st.cache_data(ttl=3600)
def get_stock_news(ticker):
    """透過 Google News RSS 取得近期股票新聞"""
    try:
        # 將 ticker 加上 stock news 進行搜尋
        query = urllib.parse.quote(f"{ticker} stock news")
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=5)
        root = ET.fromstring(resp.read())
        
        news_list = []
        for item in root.findall('.//item')[:6]: # 取前 6 篇
            title = item.find('title').text if item.find('title') is not None else "無標題"
            link = item.find('link').text if item.find('link') is not None else "#"
            pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ""
            source = item.find('source').text if item.find('source') is not None else "Google News"
            
            # 解析日期格式
            formatted_time = pubDate
            try:
                dt = datetime.strptime(pubDate, "%a, %d %b %Y %H:%M:%S %Z")
                formatted_time = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass
                
            news_list.append({
                'title': title,
                'link': link,
                'publisher': source,
                'pub_time': formatted_time
            })
        return news_list
    except Exception as e:
        return []

def calculate_rsi(data: pd.DataFrame, window: int = 14) -> pd.Series:
    delta = data['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(data: pd.DataFrame, fast=12, slow=26, signal=9):
    exp1 = data['Close'].ewm(span=fast, adjust=False).mean()
    exp2 = data['Close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - signal_line
    return macd, signal_line, macd_hist

def calculate_bollinger_bands(data: pd.DataFrame, window=20, num_of_std=2):
    sma = data['Close'].rolling(window=window).mean()
    rstd = data['Close'].rolling(window=window).std()
    upper = sma + num_of_std * rstd
    lower = sma - num_of_std * rstd
    return sma, upper, lower

def get_momentum_status(rsi):
    if pd.isna(rsi): return "未知"
    if rsi < 30: return "🟢 超賣 (逢低進場潛力)"
    elif rsi > 70: return "🔴 超買 (注意回檔風險)"
    else: return "🟡 正常動能"

# ==========================================
# 3. Streamlit 網頁介面開發
# ==========================================
st.set_page_config(page_title="台美股智慧掃描器", layout="wide", page_icon="📈", initial_sidebar_state="expanded")

# --- 左側選單 (Sidebar) ---
st.sidebar.title("🧭 系統主選單")
menu_selection = st.sidebar.radio("前往頁面", ["📊 智慧動能掃描與分析", "⚙️ 系統設定 (施工中)"])
st.sidebar.markdown("---")

if menu_selection == "⚙️ 系統設定 (施工中)":
    st.title("⚙️ 系統設定")
    st.info("此功能正在開發中，未來可以由此設定進階的 RSI 參數或是串接交易 API。")
    st.stop()

st.title("📈 台美股智慧掃描器")
st.markdown("支援**多標的清單掃描**、**大盤動能過濾**與結合**成交量**的深度圖表分析。")

st.sidebar.header("🔍 篩選與控制面板")

# 選擇市場與股票
market = st.sidebar.radio("選擇市場板塊", ["美股熱門 Top 10", "台股熱門 Top 10", "自訂輸入代碼"])

if market == "美股熱門 Top 10":
    stock_dict = US_STOCKS
    # 美股：綠漲紅跌
    color_up, color_down = "green", "red"
elif market == "台股熱門 Top 10":
    stock_dict = TW_STOCKS
    # 台股：紅漲綠跌
    color_up, color_down = "red", "green"
else:
    stock_dict = {}
    color_up, color_down = "red", "green" # 自訂代碼預設採用紅漲綠跌

if market == "自訂輸入代碼":
    ticker_symbol = st.sidebar.text_input("輸入股票代碼 (例: AAPL, 2330.TW)", "NVDA").upper()
    selected_name = ticker_symbol
else:
    selected_name = st.sidebar.selectbox("選擇深度解析標的", list(stock_dict.keys()))
    ticker_symbol = stock_dict[selected_name]

# --- 圖表指標設定 ---
st.sidebar.markdown("---")
st.sidebar.subheader("📈 圖表指標設定")
show_ma = st.sidebar.multiselect("顯示均線 (MA)", ["5MA", "20MA", "60MA"], default=["5MA", "20MA"])
show_bb = st.sidebar.checkbox("顯示布林通道 (Bollinger Bands)", value=False)
sub_indicator = st.sidebar.radio("底部副圖指標", ["RSI", "MACD"])

# --- 時間範圍 ---
st.sidebar.markdown("---")
timeframe_options = ["近 1 週", "近 1 個月", "近半年", "近 1 年", "近 5 年", "自訂區間"]
selected_timeframe = st.sidebar.selectbox("選擇技術分析區間", timeframe_options, index=2)

end_date = datetime.today().date()
if selected_timeframe == "近 1 週": start_date = end_date - timedelta(days=7)
elif selected_timeframe == "近 1 個月": start_date = end_date - timedelta(days=30)
elif selected_timeframe == "近半年": start_date = end_date - timedelta(days=180)
elif selected_timeframe == "近 1 年": start_date = end_date - timedelta(days=365)
elif selected_timeframe == "近 5 年": start_date = end_date - timedelta(days=365*5)
else:
    c1, c2 = st.sidebar.columns(2)
    start_date = c1.date_input("起始日", end_date - timedelta(days=30))
    end_date = c2.date_input("結束日", end_date)

# 抓取資料的前置緩衝期 (計算指標用)
fetch_start = start_date - timedelta(days=90)
fetch_end = end_date + timedelta(days=1)

# ==========================================
# 4. 主要分頁渲染 (Tabs)
# ==========================================
tab_screener, tab_analysis = st.tabs(["🔥 總覽與掃描 (Screener)", "📊 個股深度解析 (Analysis)"])

# --- 分頁：Screener ---
with tab_screener:
    st.subheader(f"🔍 {market} - 即時動能掃描清單")
    st.markdown("快速瀏覽市場焦點，自動計算當日表現與動能狀態。利用欄位排序可找出市場熱點！")
    
    if market == "自訂輸入代碼":
        st.info("自訂代碼模式不包含預設清單，請直接切換至「個股深度解析」分頁閱讀圖表。")
    else:
        with st.spinner("正在背景掃描並分析 10 檔股票數據，請稍候... (資料已採用快取，首次載入較久)"):
            screener_data = []
            for name, ticker in stock_dict.items():
                # 只抓取過去一個月的資料來抓最新兩天算漲跌幅
                df_scan = fetch_stock_data(ticker, (end_date - timedelta(days=40)).strftime('%Y-%m-%d'), (end_date + timedelta(days=1)).strftime('%Y-%m-%d'))
                if not df_scan.empty and len(df_scan) >= 2:
                    df_scan['RSI'] = calculate_rsi(df_scan)
                    
                    latest = df_scan.iloc[-1]
                    prev = df_scan.iloc[-2]
                    
                    close_price = latest['Close']
                    pct_change = ((close_price - prev['Close']) / prev['Close']) * 100
                    latest_rsi = latest['RSI']
                    
                    screener_data.append({
                        "股票名稱": name,
                        "代碼": ticker,
                        "最新收盤價": round(close_price, 2),
                        "單日漲跌 (% )": round(pct_change, 2),
                        "RSI (14)": round(latest_rsi, 2),
                        "動能狀態": get_momentum_status(latest_rsi)
                    })
            
            if screener_data:
                sdf = pd.DataFrame(screener_data)
                # 利用 Streamlit 內建 st.dataframe 提供互動式排序功能
                st.dataframe(sdf, hide_index=True, use_container_width=True)
            else:
                st.warning("查無清單資料，可能是 API 網路異常。")

# --- 分頁：個股深度解析 ---
with tab_analysis:
    with st.spinner(f'正在為您載入 {selected_name} 的詳細資料與新聞...'):
        df = fetch_stock_data(ticker_symbol, fetch_start.strftime('%Y-%m-%d'), fetch_end.strftime('%Y-%m-%d'))

    if df.empty:
        st.error(f"❌ 無法抓取 `{ticker_symbol}` 的資料，請確認代碼正常。")
    else:
        # 計算各種指標
        df['RSI'] = calculate_rsi(df)
        df['MACD'], df['Signal'], df['MACD_Hist'] = calculate_macd(df)
        df['5MA'] = df['Close'].rolling(window=5).mean()
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['60MA'] = df['Close'].rolling(window=60).mean()
        df['BB_Mid'], df['BB_Upper'], df['BB_Lower'] = calculate_bollinger_bands(df)
        
        # 篩選實際要顯示的範圍
        mask = (df.index >= pd.to_datetime(start_date)) & (df.index <= pd.to_datetime(end_date) + pd.Timedelta(days=1))
        plot_df = df.loc[mask]
        
        if plot_df.empty or len(plot_df) < 2:
            st.warning("⚠️ 在您選擇的日期區間內資料不足，無法呈現圖表。")
        else:
            latest = plot_df.iloc[-1]
            prev = plot_df.iloc[-2]
            
            price_change = latest['Close'] - prev['Close']
            pct_change = (price_change / prev['Close']) * 100
            
            # --- 頂部指標卡片 (引入 Delta 與百分比) ---
            col1, col2, col3 = st.columns(3)
            
            # 在 Streamlit 中，預設 delta 正值是綠色，負值是紅色 (美股邏輯)
            # 若為台股，需反轉顏色 inverse (正值紅色，負值綠色)
            delta_color_option = "normal" if market == "美股熱門 Top 10" else "inverse"
            
            col1.metric(label=f"最新標的價格 ({selected_name})", 
                        value=f"${latest['Close']:.2f}", 
                        delta=f"{price_change:+.2f} ({pct_change:+.2f}%)",
                        delta_color=delta_color_option)
                        
            col2.metric(label="最新 RSI (14)", value=f"{latest['RSI']:.2f}")
            
            with col3:
                st.markdown("##### 焦點動態：")
                if latest['RSI'] < 30:
                    st.success("🟢 **超賣**：賣壓沉重但可能隨時反彈！")
                elif latest['RSI'] > 70:
                    st.error("🔴 **超買**：漲幅過熱，慎防獲利了結賣壓！")
                else:
                    st.info("🟡 **正常動能**：行情走勢平穩。")
                    
            st.markdown("---")

            # === Plotly 多層子圖表繪製 (Subplots) ===
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.03, 
                row_heights=[0.55, 0.2, 0.25]
            )

            # --- Row 1: K 線圖與均線 ---
            fig.add_trace(go.Candlestick(
                x=plot_df.index,
                open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
                name='K線',
                increasing_line_color=color_up, decreasing_line_color=color_down
            ), row=1, col=1)

            if "5MA" in show_ma:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['5MA'], mode='lines', name='5MA', line=dict(color='blue', width=1)), row=1, col=1)
            if "20MA" in show_ma:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['20MA'], mode='lines', name='20MA', line=dict(color='orange', width=2)), row=1, col=1)
            if "60MA" in show_ma:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['60MA'], mode='lines', name='60MA', line=dict(color='purple', width=2)), row=1, col=1)

            if show_bb:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_Upper'], mode='lines', line=dict(color='gray', width=1, dash='dash'), name='布林上軌'), row=1, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['BB_Lower'], mode='lines', fill='tonexty', fillcolor='rgba(128, 128, 128, 0.1)', line=dict(color='gray', width=1, dash='dash'), name='布林下軌'), row=1, col=1)

            # --- Row 2: 成交量 (Volume) ---
            # 判斷每根 K 線的紅綠來繪圖
            colors_vol = [color_up if row['Close'] >= row['Open'] else color_down for _, row in plot_df.iterrows()]
            fig.add_trace(go.Bar(
                x=plot_df.index, y=plot_df['Volume'], name='成交量', marker_color=colors_vol, opacity=0.8
            ), row=2, col=1)

            # --- Row 3: RSI 或 MACD ---
            if sub_indicator == "RSI":
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['RSI'], mode='lines', name='RSI', line=dict(color='purple', width=2)), row=3, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
                fig.update_yaxes(title_text="RSI", range=[0, 100], row=3, col=1)
            else:
                # MACD
                colors_macd = ['red' if val >= 0 else 'green' for val in plot_df['MACD_Hist']] # 台股MACD柱狀圖紅綠相反
                if market == "美股熱門 Top 10":
                    colors_macd = ['green' if val >= 0 else 'red' for val in plot_df['MACD_Hist']]
                    
                fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['MACD_Hist'], name='MACD 柱狀', marker_color=colors_macd), row=3, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], mode='lines', name='MACD', line=dict(color='blue')), row=3, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Signal'], mode='lines', name='Signal', line=dict(color='orange')), row=3, col=1)
                fig.update_yaxes(title_text="MACD", row=3, col=1)

            # 總體圖表版面設定
            fig.update_layout(
                title=f"{selected_name} 技術分析 (OHLC, Volume, {sub_indicator})",
                xaxis_rangeslider_visible=False,
                template="plotly_white",
                hovermode="x unified",  # 這能支援垂直對齊的十字線與 OHLC 動態資訊框
                height=750,
                showlegend=False,
                margin=dict(l=50, r=50, t=50, b=50)
            )
            
            # 取消 X 軸內部各子的網格線，僅保留最下方的日期
            fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='lightgray')
            fig.update_yaxes(gridcolor='lightgray', zerolinecolor='lightgray')
            
            st.plotly_chart(fig, width='stretch')

            # --- 新聞模組 ---
            st.markdown("---")
            st.markdown(f"### 📰 {ticker_symbol} 最近重大新聞")
            news_items = get_stock_news(ticker_symbol)
            if news_items:
                col1, col2 = st.columns(2) # 兩欄版面
                for i, item in enumerate(news_items):
                    target_col = col1 if i % 2 == 0 else col2
                    pub_time = item.get('pub_time', '未知時間')
                    
                    with target_col:
                        with st.container(border=True):
                            st.markdown(f"**[{item.get('title', '無標題')}]({item.get('link', '#')})**")
                            st.caption(f"來源: {item.get('publisher', '未知')} | 📅發布時間: {pub_time}")
            else:
                st.info("目前系統無法取得此標示的最新相關新聞。")
