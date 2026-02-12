import streamlit as st
import pandas as pd
import re
import requests
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 固定定義
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}
MARKET_RULES = {"A1": "一市", "A2": "二市", "F1": "三重", "F2": "板橋", "T1": "台中", "K1": "高雄"}
MARKET_ORDER = ["一市", "二市", "三重", "板橋", "台中", "高雄"}
VARIETY_MAP = {"F22": "蜜棗", "FP1": "珍珠芭", "FP2": "紅心", "FP3": "帝王芭", "FP5": "水晶無籽", "FI3": "其他"}

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請設定 github_token")
    st.stop()

# --- 核心解析 (略，維持不變) ---
@st.cache_data(ttl=60)
def fetch_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(f"https://api.github.com/repos/goodgorilla5/chaochao-catcher/contents/", headers=headers)
        files = [f for f in r.json() if f['name'].lower().endswith('.scp')]
        for f_info in files:
            res = requests.get(f_info['download_url'], headers=headers)
            content = res.content.decode("big5", errors="ignore")
            # 解析邏輯... (此處省略部分代碼以節省空間，請沿用您原本的解析邏輯)
            # ... 
        return pd.DataFrame(all_rows).drop_duplicates() if all_rows else pd.DataFrame()
    except: return pd.DataFrame()

# 這裡為了演示，我們假設解析邏輯已在 fetch_data 完整實作
# --- 解析函數省略，請確保與您原本的 deep_parse 一致 ---
def deep_parse(content):
    # (此處請保留您原本完整的 deep_parse 內容)
    records = re.split(r'(?=[ATKF]\d{10,})', content) 
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    for rec in records:
        if not rec.strip(): continue
        try:
            m = re.search(r'(\d{8})\s+(\d{2})(S00\d{6})', rec)
            if not m: continue
            raw_date, level_code, market_anchor = m.group(1), m.group(2)[0], m.group(3)
            serial = rec[:m.start()].strip().replace(" ", "")
            market_name = MARKET_RULES.get(serial[:2], "其他")
            data_part = rec[m.end():]
            if '+' not in data_part: continue
            parts = data_part.split('+')
            pieces, weight = int(parts[0][-3:].strip()), int(parts[1].strip())
            price = int(parts[2].strip().split()[0][:-1]) if parts[2].strip() else 0
            total_val = int(parts[3].strip().split()[0]) if parts[3].strip() else 0
            buyer_match = re.search(r'^\d+', parts[-1].strip())
            buyer = buyer_match.group() if buyer_match else ""
            v_code_match = re.search(r'(F22|FP1|FP2|FP3|FP5|FI3)', parts[0])
            v_name = VARIETY_MAP.get(v_code_match.group(1), "蜜棗") if v_code_match else "蜜棗"
            dt_obj = datetime(int(raw_date[:3])+1911, int(raw_date[3:5]), int(raw_date[5:7])).date()
            farm = "其他"
            for name, code in FARMER_MAP.items():
                if code in market_anchor: farm = name; break
            if farm == "其他": continue
            rows.append({"農會": farm, "日期": dt_obj, "市場": market_name, "小代": market_anchor[6:9], "件數": pieces, "公斤": weight, "單價": price, "總價": total_val, "買家": buyer, "品種": v_name})
        except: continue
    return rows

df = fetch_data()

# --- 側邊欄：僅保留開關 ---
st.sidebar.title("基本設定")
selected_markets = [m for m in MARKET_ORDER if st.sidebar.checkbox(f"開啟 {m}", value=(m in ["一市", "二市"]))]

# --- 主畫面 ---
st.title("🍎 農會行情大數據庫")

if not df.empty:
    # 第一排：三大主要選單
    r1, r2, r3 = st.columns(3)
    with r1:
        target_farm = st.selectbox("🏥 選擇農會", list(FARMER_MAP.keys()))
    with r2:
        target_v = st.selectbox("🍐 選擇品種", df[df['農會']==target_farm]['品種'].unique())
    with r3:
        # --- 這裡是您要的功能：改用 Selectbox ---
        target_sub = st.selectbox(
            "⭐ 常用小代篩選",
            ["顯示全部", "633", "627", "626", "手動輸入"]
        )

    # 第二排：額外搜尋
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        max_date = df['日期'].max()
        date_range = st.date_input("📅 日期區間", value=[max_date, max_date])
    with c2:
        # 如果上面選了手動輸入，這裡才讓使用者打字，或者並存
        s_sub = st.text_input("🔍 手動輸入小代 (若上方選顯示全部則無效)")
    with c3:
        s_buy = st.text_input("👤 買家搜尋")

    # --- 過濾邏輯 ---
    f_df = df[(df['農會'] == target_farm) & (df['品種'] == target_v) & (df['市場'].isin(selected_markets))].copy()
    
    # 小代過濾：Selectbox 與 Text_input 聯動
    if target_sub != "顯示全部":
        if target_sub == "手動輸入":
            if s_sub: f_df = f_df[f_df['小代'].str.contains(s_sub)]
        else:
            f_df = f_df[f_df['小代'] == target_sub]

    if s_buy: f_df = f_df[f_df['買家'].str.contains(s_buy)]
    
    # 日期與表格顯示 (略)...
    st.dataframe(f_df, use_container_width=True, hide_index=True)
else:
    st.warning("⚠️ 數據加載中或無資料。")