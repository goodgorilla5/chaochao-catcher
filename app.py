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
MARKET_ORDER = ["一市", "二市", "三重", "板橋", "台中", "高雄"]
VARIETY_MAP = {"F22": "蜜棗", "FP1": "珍珠芭", "FP2": "紅心", "FP3": "帝王芭", "FP5": "水晶無籽", "FI3": "其他"}

# 從 Secrets 讀取 Token
try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請設定 github_token")
    st.stop()

# --- 核心解析邏輯 ---
def deep_parse(content):
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
            rows.append({"農會": farm, "日期": dt_obj, "顯示日期": f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}", "市場": market_name, "等級": grade_map.get(level_code, level_code), "小代": market_anchor[6:9], "件數": pieces, "公斤": weight, "單價": price, "總價": total_val, "買家": buyer, "品種": v_name})
        except: continue
    return rows

@st.cache_data(ttl=60)
def fetch_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(f"https://api.github.com/repos/goodgorilla5/chaochao-catcher/contents/", headers=headers)
        files = [f for f in r.json() if f['name'].lower().endswith('.scp')]
        for f_info in files:
            res = requests.get(f_info['download_url'], headers=headers)
            all_rows.extend(deep_parse(res.content.decode("big5", errors="ignore")))
        return pd.DataFrame(all_rows).drop_duplicates() if all_rows else pd.DataFrame()
    except: return pd.DataFrame()

df = fetch_data()

# --- 主畫面標題 ---
st.title("🍎 農會行情大數據庫")

# --- 初始化 Session State (用來記住選了哪個小代) ---
if 'selected_sub' not in st.session_state:
    st.session_state.selected_sub = "全部"

# --- 🚀 這是你要的「常用小代快選」按鈕區 🚀 ---
st.subheader("⭐ 常用小代快速篩選")
b1, b2, b3, b4 = st.columns(4)
with b1:
    if st.button("顯示全部 (重設)", use_container_width=True): st.session_state.selected_sub = "全部"
with b2:
    if st.button("【633】", use_container_width=True): st.session_state.selected_sub = "633"
with b3:
    if st.button("【627】", use_container_width=True): st.session_state.selected_sub = "627"
with b4:
    if st.button("【626】", use_container_width=True): st.session_state.selected_sub = "626"

st.info(f"📍 目前正在查看：**{st.session_state.selected_sub}**")
st.divider()

if not df.empty:
    # 基礎篩選
    c1, c2, c3 = st.columns(3)
    with c1: target_farm = st.selectbox("🏥 選擇農會", list(FARMER_MAP.keys()))
    with c2: target_v = st.selectbox("🍐 選擇品種", df[df['農會']==target_farm]['品種'].unique())
    with c3: sort_opt = st.selectbox("🔃 排序", ["單價：高至低", "日期：新至舊"])

    # 執行過濾
    selected_markets = [m for m in MARKET_ORDER if st.sidebar.checkbox(m, value=(m in ["一市", "二市"]))]
    f_df = df[(df['農會'] == target_farm) & (df['品種'] == target_v) & (df['市場'].isin(selected_markets))].copy()

    # 關鍵：根據剛才點的按鈕過濾小代
    if st.session_state.selected_sub != "全部":
        f_df = f_df[f_df['小代'] == st.session_state.selected_sub]

    # 排序與顯示
    f_df = f_df.sort_values("單價" if "單價" in sort_opt else "日期", ascending=False)
    st.dataframe(f_df[["顯示日期", "市場", "小代", "件數", "公斤", "單價", "買家"]], use_container_width=True, hide_index=True)