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
SORTED_V_NAMES = ["蜜棗", "珍珠芭", "紅心", "帝王芭", "水晶無籽"]

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請在 Streamlit Cloud 設定中配置 github_token")
    st.stop()

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
            rows.append({"農會": farm, "日期": dt_obj, "顯示日期": f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}", "市場": market_name, "等級": grade_map.get(level_code, level_code), "小代": market_anchor[6:9], "件數": pieces, "公斤": weight, "單價": price, "總價": total_val, "買家": buyer, "流水號": serial, "品種": v_name})
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
        return full_df.drop_duplicates(subset=["流水號", "日期", "小代", "件數", "總價"]) if not full_df.empty else full_df
    except: return pd.DataFrame()

df = fetch_data()

# --- 側邊欄 (優化排版) ---
st.sidebar.title("⚙️ 控制面板")

# 1. 市場篩選
st.sidebar.subheader("🏢 市場選擇")
all_market_selected = st.sidebar.checkbox("全選所有市場", value=False)
selected_markets = []
for m in MARKET_ORDER:
    # 如果點選全選，則所有 checkbox 強制為 True
    val = True if all_market_selected else (m in ["一市", "二市"])
    if st.sidebar.checkbox(m, value=val, key=f"mkt_{m}"):
        selected_markets.append(m)

st.sidebar.markdown("---") # 分隔線

# 2. 顯示設定
st.sidebar.subheader("👁️ 顯示欄位")
show_serial = st.sidebar.checkbox("顯示流水號", value=True) # 預設開啟
show_grade = st.sidebar.checkbox("顯示等級", value=False)
show_total = st.sidebar.checkbox("顯示總價", value=False)

# --- 主畫面 ---
st.title("🍎 農會行情大數據庫")

if not df.empty:
    c1, c2, c3 = st.columns(3)
    with c1: target_farm = st.selectbox("🏥 選擇農會", list(FARMER_MAP.keys()))
    with c2: 
        v_list = df[df['農會']==target_farm]['品種'].unique()
        target_v = st.selectbox("🍐 選擇品種", [v for v in SORTED_V_NAMES if v in v_list] if v_list.any() else v_list)
    with c3: 
        # 補回所有排序選項
        sort_opt = st.selectbox("🔃 排序方式", ["價格：由高至低", "價格：由低至高", "日期：由新到舊", "日期：由舊至新"])

    st.markdown("---")
    st.markdown("##### ⭐ 常用小代快選")
    fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 3])
    fav_subs = []
    with fc1: 
        if st.checkbox("633", key="f633"): fav_subs.append("633")
    with fc2: 
        if st.checkbox("627", key="f627"): fav_subs.append("627")
    with fc3: 
        if st.checkbox("626", key="f626"): fav_subs.append("626")
    with fc4: s_sub = st.text_input("🔍 手動輸入小代")

    c_d1, c_d2 = st.columns(2)
    with c_d1:
        max_dt = df['日期'].max()
        date_range = st.date_input("📅 日期區間", value=[max_dt, max_dt])
    with c_d2: s_buy = st.text_input("👤 買家搜尋")

    # 過濾邏輯
    f_df = df[(df['農會']==target_farm) & (df['品種']==target_v) & (df['市場'].isin(selected_markets))].copy()
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        f_df = f_df[(f_df['日期'] >= date_range[0]) & (f_df['日期'] <= date_range[1])]
    
    # 小代邏輯 (已修正拼字)
    if fav_subs or s_sub:
        if fav_subs and not s_sub: f_df = f_df[f_df['小代'].isin(fav_subs)]
        elif s_sub and not fav_subs: f_df = f_df[f_df['小代'].str.contains(s_sub)]
        else: f_df = f_df[f_df['小代'].isin(fav_subs) | f_df['小代'].str.contains(s_sub)]
    
    if s_buy: f_df = f_df[f_df['買家'].str.contains(s_buy)]

    # 排序邏輯修正
    if sort_opt == "價格：由高至低":
        f_df = f_df.sort_values("單價", ascending=False)
    elif sort_opt == "價格：由低至高":
        f_df = f_df.sort_values("單價", ascending=True)
    elif sort_opt == "日期：由新到舊":
        f_df = f_df.sort_values(["日期", "單價"], ascending=[False, False])
    elif sort_opt == "日期：由舊至新":
        f_df = f_df.sort_values(["日期", "單價"], ascending=[True, False])

    # 欄位顯示處理
    disp_cols = ["顯示日期", "市場", "小代", "件數", "公斤", "單價", "買家"]
    if show_grade: disp_cols.insert(2, "等級")
    if show_total: disp_cols.append("總價")
    if show_serial: disp_cols.insert(0, "流水號")
    
    st.dataframe(f_df[disp_cols].rename(columns={"顯示日期":"日期"}), use_container_width=True, height=400, hide_index=True)

    # --- 📊 區間行情彙總 ---
    if not f_df.empty:
        st.divider()
        t_pcs, t_kg, t_val = int(f_df['件數'].sum()), int(f_df['公斤'].sum()), int(f_df['總價'].sum())
        avg_p, max_p, min_p = t_val/t_kg if t_kg>0 else 0, f_df['單價'].max(), f_df['單價'].min()
        
        st.markdown("### 📈 區間行情彙總")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f"**最高價**：<span style='font-size:20px; color:#ff4b4b;'>{max_p}</span> 元", unsafe_allow_html=True)
            st.markdown(f"**最低價**：<span style='font-size:20px; color:#1f77b4;'>{min_p}</span> 元", unsafe_allow_html=True)
        with m2:
            st.markdown(f"**平均單價**：<span style='font-size:20px;'>{avg_p:.1f}</span> 元", unsafe_allow_html=True)
            st.markdown(f"**區間總價**：<span style='font-size:20px;'>{t_val:,}</span> 元", unsafe_allow_html=True)
        with m3:
            st.markdown(f"**總件數**：<span style='font-size:20px;'>{t_pcs}</span> 件", unsafe_allow_html=True)
            st.markdown(f"**總公斤**：<span style='font-size:20px;'>{t_kg}</span> kg", unsafe_allow_html=True)
else:
    st.warning("⚠️ 數據加載中或無資料。")