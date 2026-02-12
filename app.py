import streamlit as st
import pandas as pd
import re
import requests
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# ==========================================================
# 固定定義區
# ==========================================================
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}
MARKET_RULES = {"A1": "一市", "A2": "二市", "F1": "三重", "F2": "板橋", "T1": "台中", "K1": "高雄"}
MARKET_ORDER = ["一市", "二市", "三重", "板橋", "台中", "高雄"]
VARIETY_MAP = {"F22": "蜜棗", "FP1": "珍珠芭", "FP2": "紅心", "FP3": "帝王芭", "FP5": "水晶無籽", "FI3": "其他"}

# 您指定的常用小代號
FAV_SUB_CODES = ["全部顯示", "633", "627", "626", "手動搜尋"]

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請在 Streamlit Cloud 設定 github_token")
    st.stop()

# --- 解析邏輯 (維持不變，確保數據正確) ---
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
            rows.append({
                "農會": farm, "日期": dt_obj, "顯示日期": f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}",
                "市場": market_name, "等級": grade_map.get(level_code, level_code), "小代": market_anchor[6:9],
                "件數": pieces, "公斤": weight, "單價": price, "總價": total_val,
                "買家": buyer, "流水號": serial, "品種": v_name
            })
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
        return pd.DataFrame(all_rows).drop_duplicates(subset=["流水號", "日期", "小代", "件數", "總價"]) if all_rows else pd.DataFrame()
    except: return pd.DataFrame()

# --- 讀取資料 ---
df = fetch_data()

# --- 側邊欄：僅保留開關 ---
st.sidebar.title("基本設定")
selected_markets = [m for m in MARKET_ORDER if st.sidebar.checkbox(f"開啟 {m}", value=(m in ["一市", "二市"]))]
show_grade = st.sidebar.checkbox("顯示等級", value=False)
show_total = st.sidebar.checkbox("顯示總價", value=False)

# --- 主畫面顯示 ---
st.title("🍎 農會行情大數據庫")

if not df.empty:
    # 第一排：三大主要選單 (新增小代快選)
    r1, r2, r3 = st.columns(3)
    with r1:
        target_farm = st.selectbox("🏥 選擇農會", list(FARMER_MAP.keys()))
    with r2:
        v_list = df[df['農會']==target_farm]['品種'].unique()
        target_v = st.selectbox("🍐 選擇品種", v_list)
    with r3:
        # --- 固定定義的小代下拉選單 ---
        target_sub = st.selectbox("⭐ 常用小代快選", FAV_SUB_CODES)

    # 第二排：日期與搜尋
    c1, c2, c3 = st.columns([1.5, 1, 1])
    with c1:
        max_date = df['日期'].max()
        date_range = st.date_input("📅 選擇日期區間", value=[max_date, max_date])
    with c2:
        # 如果上方選擇「手動搜尋」，這個框才起作用，否則僅供參考
        s_sub = st.text_input("🔍 手動搜尋其他小代")
    with c3:
        s_buy = st.text_input("👤 搜尋買家代號")

    # --- 過濾邏輯 ---
    f_df = df[(df['農會'] == target_farm) & (df['品種'] == target_v) & (df['市場'].isin(selected_markets))].copy()
    
    # 日期過濾
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        f_df = f_df[(f_df['日期'] >= date_range[0]) & (f_df['日期'] <= date_range[1])]

    # 小代過濾：依照下拉選單的內容
    if target_sub == "手動搜尋":
        if s_sub: f_df = f_df[f_df['小代'].str.contains(s_sub)]
    elif target_sub != "全部顯示":
        f_df = f_df[f_df['小代'] == target_sub]

    # 買家搜尋
    if s_buy: f_df = f_df[f_df['買家'].str.contains(s_buy)]

    # 排序與顯示
    f_df = f_df.sort_values("單價", ascending=False)
    display_cols = ["顯示日期", "市場", "小代", "件數", "公斤", "單價", "買家"]
    if show_grade: display_cols.insert(2, "等級")
    if show_total: display_cols.append("總價")
    
    st.dataframe(f_df[display_cols].rename(columns={"顯示日期": "日期"}), use_container_width=True, height=500, hide_index=True)

    if not f_df.empty:
        st.divider()
        t_pcs, t_kg, t_val = f_df['件數'].sum(), f_df['公斤'].sum(), f_df['總價'].sum()
        avg_p = t_val / t_kg if t_kg > 0 else 0
        st.info(f"📊 統計摘要｜總件數：{int(t_pcs)}｜總公斤：{int(t_kg)}｜平均單價：{avg_p:.1f}｜總額：{int(t_val):,}")
else:
    st.warning("⚠️ 數據加載中或無資料，請檢查 GitHub 檔案。")