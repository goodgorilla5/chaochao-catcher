import streamlit as st
import pandas as pd
import re
import requests
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 農會與市場對照定義
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}
# 更新後的市場規則
MARKET_RULES = {
    "A1": "一市",
    "A2": "二市",
    "T1": "台中",
    "K1": "高雄",
    "F1": "三重市場",
    "F2": "板橋市場"
}

# 品種對照表
VARIETY_MAP = {
    "F22": "蜜棗",
    "FP1": "珍珠芭",
    "FP2": "紅心",
    "FP3": "帝王芭",
    "FP5": "水晶無籽",
    "FI3": "其他"
}
SORTED_V_NAMES = ["蜜棗", "珍珠芭", "紅心", "帝王芭", "水晶無籽"]

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請設定 github_token")
    st.stop()

# --- 核心解析邏輯 ---
def deep_parse(content):
    # 擴大正則表達式以涵蓋所有市場代碼
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
            
            # 提取流水號並判定市場
            serial = rec[:m.start()].strip().replace(" ", "")
            m_prefix = serial[:2] 
            market_name = MARKET_RULES.get(m_prefix, "其他")

            data_part = rec[m.end():]
            if '+' not in data_part: continue
            parts = data_part.split('+')
            
            pieces = int(parts[0][-3:].strip())
            weight = int(parts[1].strip())
            p_str = parts[2].strip().split()[0]
            price = int(p_str[:-1]) if p_str else 0
            
            t_str = parts[3].strip().split()[0]
            total_val = int(t_str) if t_str else 0
            
            buyer_raw = parts[-1].strip()
            buyer_match = re.search(r'^\d+', buyer_raw)
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
        r = requests.get("https://api.github.com/repos/goodgorilla5/chaochao-catcher/contents/", headers=headers)
        files = [f for f in r.json() if f['name'].lower().endswith('.scp')]
        for f_info in files:
            res = requests.get(f_info['download_url'], headers=headers)
            all_rows.extend(deep_parse(res.content.decode("big5", errors="ignore")))
        full_df = pd.DataFrame(all_rows)
        if not full_df.empty:
            full_df = full_df.drop_duplicates(subset=["流水號", "日期", "小代", "件數", "總價", "買家"], keep='first')
        return full_df
    except: return pd.DataFrame()

# --- 主程式 ---
df = fetch_data()

# --- 側邊欄：顯示與市場設定 ---
st.sidebar.header("🏢 市場篩選")
selected_markets = []
# 建立市場清單，側邊欄只顯示中文名稱
unique_market_names = ["一市", "二市", "台中", "高雄", "三重市場", "板橋市場"]
for m_name in unique_market_names:
    default_val = True if m_name in ["一市", "二市"] else False
    if st.sidebar.checkbox(f"開啟 {m_name}", value=default_val):
        selected_markets.append(m_name)

st.sidebar.markdown("---")
st.sidebar.header("🎨 顯示設定")
show_serial = st.sidebar.checkbox("顯示流水號", value=False)
show_grade = st.sidebar.checkbox("顯示等級", value=False)
show_total = st.sidebar.checkbox("顯示總價", value=False)

st.title("🍎 農會行情大數據庫")

if not df.empty:
    # --- 1. 第一層：農會、品種、排序 ---
    r1_c1, r1_c2, r1_c3 = st.columns([1, 1, 1])
    with r1_c1:
        target_farm = st.selectbox("🏥 選擇農會", list(FARMER_MAP.keys()))
    with r1_c2:
        v_list = df[df['農會']==target_farm]['品種'].unique()
        v_options = [v for v in SORTED_V_NAMES if v in v_list]
        target_v = st.selectbox("🍐 選擇品種", v_options) if v_options else st.selectbox("🍐 選擇品種", v_list)
    with r1_c3:
        sort_option = st.selectbox(
            "🔃 排序方式",
            ["價格：由高至低", "價格：由低至高", "日期：由新到舊", "日期：由舊至新"]
        )

    # --- 2. 第二層：日期區間 ---
    max_date = df['日期'].max()
    date_range = st.date_input("📅 選擇日期區間", value=[max_date, max_date])

    # --- 3. 第三層：搜尋小代與買家 ---
    r3_c1, r3_c2 = st.columns(2)
    with r3_c1:
        s_sub = st.text_input("🔍 搜尋小代")
    with r3_c2:
        s_buy = st.text_input("👤 搜尋買家")

    # --- 核心過濾邏輯 ---
    f_df = df[
        (df['農會'] == target_farm) & 
        (df['品種'] == target_v) & 
        (df['市場'].isin(selected_markets))
    ].copy()
    
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        f_df = f_df[(f_df['日期'] >= start_date) & (f_df['日期'] <= end_date)]

    if s_sub: f_df = f_df[f_df['小代'].str.contains(s_sub)]
    if s_buy: f_df = f_df[f_df['買家'].str.contains(s_buy)]

    # 執行排序
    if sort_option == "日期：由新到舊":
        f_df = f_df.sort_values(["日期", "單價"], ascending=[False, False])
    elif sort_option == "日期：由舊至新":
        f_df = f_df.sort_values(["日期", "單價"], ascending=[True, False])
    elif sort_option == "價格：由高至低":
        f_df = f_df.sort_values("單價", ascending=False)
    elif sort_option == "價格：由低至高":
        f_df = f_df.sort_values("單價", ascending=True)

    # --- 表格顯示 ---
    display_cols = ["顯示日期", "市場", "小代", "件數", "公斤", "單價", "買家"]
    if show_grade: display_cols.insert(display_cols.index("市場")+1, "等級")
    if show_total: display_cols.insert(display_cols.index("單價") + 1, "總價")
    if show_serial: display_cols.insert(0, "流水號")
    
    st.dataframe(f_df[display_cols].rename(columns={"顯示日期": "日期"}), 
                 use_container_width=True, height=450, hide_index=True)

    # --- 統計摘要 ---
    st.divider()
    if not f_df.empty:
        t_pcs, t_kg, t_val = f_df['件數'].sum(), f_df['公斤'].sum(), f_df['總價'].sum()
        avg_p = t_val / t_kg if t_kg > 0 else 0
        st.markdown(f"##### 📉 {target_farm} ({target_v}) 摘要")
        m_cols = st.columns(6)
        metrics = [
            ("總件數", f"{int(t_pcs)} 件"), ("總公斤", f"{int(t_kg)} kg"),
            ("最高價", f"{f_df['單價'].max()} 元"), ("最低價", f"{f_df['單價'].min()} 元"),
            ("平均單價", f"{avg_p:.1f} 元"), ("區間總額", f"{int(t_val):,} 元")
        ]
        for i, (l, v) in enumerate(metrics):
            with m_cols[i]:
                st.markdown(f'<div style="background-color:#f0f2f6;padding:8px;border-radius:5px;text-align:center;">'
                            f'<p style="margin:0;font-size:12px;color:#555;">{l}</p>'
                            f'<p style="margin:0;font-size:15px;font-weight:bold;color:#111;">{v}</p></div>', unsafe_allow_html=True)
else:
    st.warning("😭 暫無資料或未勾選市場。")