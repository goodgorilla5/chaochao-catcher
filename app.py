import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="燕巢台北行情大數據庫", layout="wide")

# --- GitHub 設定區 ---
REPO_OWNER = "goodgorilla5"
REPO_NAME = "chaochao-catcher"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請至 Streamlit 後台 Secrets 設定 github_token")
    st.stop()

# --- 核心解析邏輯 ---
def process_logic(content):
    raw_lines = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in raw_lines:
        if "F22" in line and "S00076" in line:
            try:
                date_match = re.search(r"(\d{7,8}1)\s+\d{2}S00076", line)
                if date_match:
                    date_pos = date_match.start()
                    raw_date_str = date_match.group(1)[:7]
                    serial = line[:date_pos].strip().replace(" ", "")
                    
                    remaining = line[date_pos:]
                    s_pos = remaining.find("S00076")
                    level = grade_map.get(remaining[s_pos-2], remaining[s_pos-2])
                    sub_id = remaining[s_pos+6:s_pos+9]
                    
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].replace(" ", "") or 0)
                    weight = int(nums[1].replace(" ", "") or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    price = int(price_raw[:-1] if price_raw else 0)
                    total_price = int(nums[3].replace(" ", "") or 0)
                    buyer = nums[5].strip()[:4] if len(nums) > 5 else ""

                    rows.append({
                        "日期編碼": raw_date_str,
                        "顯示日期": f"{raw_date_str[:3]}/{raw_date_str[3:5]}/{raw_date_str[5:7]}",
                        "流水號": serial, 
                        "等級": level, 
                        "小代": sub_id, 
                        "件數": pieces, 
                        "公斤": weight, 
                        "單價": price, 
                        "總價": total_price,
                        "買家": buyer
                    })
            except: 
                continue
    return rows

@st.cache_data(ttl=60)
def fetch_all_github_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        files = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                text = res.content.decode("big5", errors="ignore")
                return process_logic(text)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(download_and_parse, files))
        
        for r_list in results: all_rows.extend(r_list)
        df = pd.DataFrame(all_rows)
        if not df.empty:
            df = df.drop_duplicates(subset="流水號", keep='first')
            df['date_obj'] = pd.to_datetime(df['日期編碼'].apply(lambda x: str(int(x[:3])+1911)+x[3:]), format='%Y%m%d')
            df = df.sort_values(by=["date_obj", "單價"], ascending=[False, False])
        return df
    except:
        return pd.DataFrame()

# --- 讀取資料 ---
df = fetch_all_github_data()

st.title("🍎 燕巢-台北行情大數據庫")

if not df.empty:
    # --- 1. 表格上方：查詢控制區 ---
    min_d, max_d = df['date_obj'].min().date(), df['date_obj'].max().date()
    
    # 手機排版優化：控制區排成兩欄
    ctrl_c1, ctrl_c2 = st.columns([2, 1])
    with ctrl_c1:
        date_range = st.date_input("📅 選擇查詢區間", value=(max_d, max_d), min_value=min_d, max_value=max_d)
    with ctrl_c2:
        search_sub = st.text_input("🔍 搜尋小代 (如 627)", placeholder="輸入代號")

    # 側邊欄僅保留「顯示設定」
    st.sidebar.header("🎨 顯示設定")
    show_level = st.sidebar.checkbox("顯示等級", value=False)
    show_total_p = st.sidebar.checkbox("顯示總價", value=False)
    show_serial = st.sidebar.checkbox("顯示原始流水號", value=False)

    # 過濾邏輯
    f_df = df.copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        f_df = f_df[(f_df['date_obj'].dt.date >= date_range[0]) & (f_df['date_obj'].dt.date <= date_range[1])]
    if search_sub:
        f_df = f_df[f_df['小代'].str.contains(search_sub)]

    # --- 2. 行情表格顯示 ---
    display_cols = ["顯示日期", "小代", "件數", "公斤", "單價", "買家"]
    if show_level: display_cols.insert(1, "等級")
    if show_total_p:
        idx = display_cols.index("單價") + 1
        display_cols.insert(idx, "總價")
    if show_serial: display_cols.insert(0, "流水號")
    
    st.dataframe(
        f_df[display_cols].rename(columns={"顯示日期": "日期"}), 
        use_container_width=True, 
        height=500, # 稍微調低高度，讓下方統計資訊露出
        column_config={
            "單價": st.column_config.NumberColumn(format="%d"),
            "總價": st.column_config.NumberColumn(format="%d")
        }
    )

    # --- 3. 表格下方：統計資訊區 ---
    st.divider()
    t_pcs, t_kg, t_val = f_df['件數'].sum(), f_df['公斤'].sum(), f_df['總價'].sum()
    avg_p = t_val / t_kg if t_kg > 0 else 0

    # 使用較小的 columns 字體
    st.markdown("##### 📉 區間數據摘要")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("總件數", f"{t_pcs} 件")
    m2.metric("總公斤", f"{t_kg} kg")
    m3.metric("最高價", f"{f_df['單價'].max()} 元")
    m4.metric("最低價", f"{f_df['單價'].min()} 元")
    m5.metric("平均單價", f"{avg_p:.2f} 元")
    m6.metric("區間總價", f"{t_val:,} 元")

else:
    st.warning("😭 目前雲端倉庫中沒有可讀取的資料。")