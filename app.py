import streamlit as st
import pandas as pd
import re
import requests
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 農會與市場對照定義
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}
MARKET_RULES = {"A1": "一市", "A2": "二市", "F1": "三重", "F2": "板橋", "T1": "台中", "K1": "高雄"}
MARKET_ORDER = ["一市", "二市", "三重", "板橋", "台中", "高雄"}

# 品種對照表
VARIETY_MAP = {"F22": "蜜棗", "FP1": "珍珠芭", "FP2": "紅心", "FP3": "帝王芭", "FP5": "水晶無籽", "FI3": "其他"}
SORTED_V_NAMES = ["蜜棗", "珍珠芭", "紅心", "帝王芭", "水晶無籽"]

# 從 Secrets 讀取 Token
try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請在 Streamlit Cloud 設定中配置 github_token")
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
            
            raw_date = m.group(1)
            level_code = m.group(2)[0]
            market_anchor = m.group(3)
            serial = rec[:m.start()].strip().replace(" ", "")
            m_prefix = serial[:2] 
            market_name = MARKET_RULES.get(m_prefix, "其他")

            data_part = rec[m.end():]
            if '+' not in data_part: continue
            parts = data_part.split('+')
            
            pieces = int(parts[0][-3:].strip())
            weight = int(parts[1].strip())
            price = int(parts[2].strip().split()[0][:-1]) if parts[2].strip() else 0
            total_val = int(parts[3].strip().split()[0]) if parts[3].strip() else 0
            
            buyer_match = re.search(r'^\d+', parts[-1].strip())
            buyer = buyer_match.group() if buyer_match else ""

            v_code_match = re.search(r'(F22|FP1|FP2|FP3|FP5|FI3)', parts[0])
            v_code = v_code_match.group(1) if v_code_match else "F22"
            v_name = VARIETY_MAP.get(v_code, v_code)

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
        full_df = pd.DataFrame(all_rows)
        if not full_df.empty:
            full_df = full_df.drop_duplicates(subset=["流水號", "日期", "小代", "件數", "總價", "買家"], keep='first')
        return full_df
    except: return pd.DataFrame()

# --- 讀取資料 ---
df = fetch_data()

# --- 側邊欄：分區過濾 ---
st.sidebar.title("🛠️ 篩選控制台")

# 1. 市場篩選 (預設開啟一二市)
st.sidebar.subheader("🏢 選擇市場")
selected_markets = []
for m in MARKET_ORDER:
    is_on = st.sidebar.checkbox(m, value=(m in ["一市", "二市"]))
    if is_on: selected_markets.append(m)

st.sidebar.markdown("---")

# 2. 常用小代 (這就是您要的功能)
st.sidebar.subheader("⭐ 常用小代快選")
fav_subs = []
if st.sidebar.checkbox("633", value=False): fav_subs.append("633")
if st.sidebar.checkbox("627", value=False): fav_subs.append("627")
if st.sidebar.checkbox("626", value=False): fav_subs.append("626")

st.sidebar.markdown("---")

# 3. 顯示開關
st.sidebar.subheader("🎨 顯示設定")
show_serial = st.sidebar.checkbox("顯示流水號", value=False)
show_grade = st.sidebar.checkbox("顯示等級", value=False)
show_total = st.sidebar.checkbox("顯示總價", value=False)

# --- 主畫面顯示 ---
st.title("🍎 農會行情大數據庫")

if not df.empty:
    # 第一排：農會、品種、排序
    c1, c2, c3 = st.columns(3)
    with c1:
        target_farm = st.selectbox("🏥 選擇農會", list(FARMER_MAP.keys()))
    with c2:
        v_list = df[df['農會']==target_farm]['品種'].unique()
        v_options = [v for v in SORTED_V_NAMES if v in v_list]
        target_v = st.selectbox("🍐 選擇品種", v_options) if v_options else st.selectbox("🍐 選擇品種", v_list)
    with c3:
        sort_option = st.selectbox("🔃 排序方式", ["價格：由高至低", "價格：由低至高", "日期：由新到舊", "日期：由舊至新"])

    # 第二排：日期與搜尋
    c4, c5, c6 = st.columns([1.5, 1, 1])
    with c4:
        max_date = df['日期'].max()
        date_range = st.date_input("📅 選擇日期區聯", value=[max_date, max_date])
    with c5:
        s_sub = st.text_input("🔍 搜尋其他小代")
    with c6:
        s_buy = st.text_input("👤 搜尋買家")

    # --- 過濾邏輯 ---
    f_df = df[(df['農會'] == target_farm) & (df['品種'] == target_v) & (df['市場'].isin(selected_markets))].copy()
    
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        f_df = f_df[(f_df['日期'] >= date_range[0]) & (f_df['日期'] <= date_range[1])]

    # 關鍵：小代過濾 (常用勾選 OR 手動輸入)
    if fav_subs or s_sub:
        if fav_subs and not s_sub:
            f_df = f_df[f_df['小代'].isin(fav_subs)]
        elif s_sub and not fav_subs:
            f_df = f_df[f_df['小代'].str.contains(s_sub)]
        else:
            f_df = f_df[f_df['小代'].isin(fav_subs) | f_df['小代'].str.contains(s_sub)]

    if s_buy: f_df = f_df[f_df['買家'].str.contains(s_buy)]

    # 排序邏輯
    asc_map = {"價格：由高至低": [False], "價格：由低至高": [True], "日期：由新到舊": [False, False], "日期：由舊至新": [True, False]}
    sort_cols = ["單價"] if "價格" in sort_option else ["日期", "單價"]
    f_df = f_df.sort_values(sort_cols, ascending=asc_map[sort_option])

    # 表格欄位定義
    display_cols = ["顯示日期", "市場", "小代", "件數", "公斤", "單價", "買家"]
    if show_grade: display_cols.insert(2, "等級")
    if show_total: display_cols.append("總價")
    if show_serial: display_cols.insert(0, "流水號")
    
    st.dataframe(f_df[display_cols].rename(columns={"顯示日期": "日期"}), use_container_width=True, height=500, hide_index=True)

    # 底部摘要
    if not f_df.empty:
        st.divider()
        t_pcs, t_kg, t_val = f_df['件數'].sum(), f_df['公斤'].sum(), f_df['總價'].sum()
        avg_p = t_val / t_kg if t_kg > 0 else 0
        st.info(f"📊 統計摘要｜總件數：{int(t_pcs)}｜總公斤：{int(t_kg)}｜平均單價：{avg_p:.1f}｜總額：{int(t_val):,}")
else:
    st.warning("⚠️ 沒找到資料，請檢查 GitHub 檔案或篩選條件。")