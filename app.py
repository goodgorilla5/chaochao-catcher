import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# --- GitHub 設定區 ---
REPO_OWNER = "goodgorilla5"
REPO_NAME = "chaochao-catcher"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"

# 農會定義
FARMER_MAP = {
    "燕巢": "S00076",
    "大社": "S00250",
    "阿蓮": "S00098"
}

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
        # 重點 1：只抓 F22 (蜜棗)
        if "F22" in line:
            try:
                # 判定農會歸屬
                belong_to = "未知"
                for name, code in FARMER_MAP.items():
                    if code in line:
                        belong_to = name
                        break
                
                # 若不在我們設定的三個農會內，跳過
                if belong_to == "未知": continue

                date_match = re.search(r"(\d{7,8}1)\s+\d{2}[S|T]\d{5}", line)
                if date_match:
                    date_pos = date_match.start()
                    raw_date_str = date_match.group(1)[:7]
                    
                    # 處理流水號 (移除所有空格以包容不同農會格式)
                    serial = line[:date_pos].strip().replace(" ", "")
                    
                    # 定位等級與小代
                    remaining = line[date_pos:]
                    # 尋找市場代碼位置
                    m_match = re.search(r"[S|T]\d{5}", remaining)
                    m_pos = m_match.start()
                    level = grade_map.get(remaining[m_pos-2], remaining[m_pos-2])
                    sub_id = remaining[m_pos+6:m_pos+9]
                    
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].replace(" ", "") or 0)
                    weight = int(nums[1].replace(" ", "") or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    price = int(price_raw[:-1] if price_raw else 0)
                    total_price = int(nums[3].replace(" ", "") or 0)
                    buyer = nums[5].strip()[:4] if len(nums) > 5 else ""

                    rows.append({
                        "農會": belong_to,
                        "日期編碼": raw_date_str,
                        "顯示日期": f"{raw_date_str[:3]}/{raw_date_str[3:5]}/{raw_date_str[5:7]}",
                        "流水號": serial, "等級": level, "小代": sub_id, 
                        "件數": pieces, "公斤": weight, "單價": price, 
                        "總價": total_price, "買家": buyer
                    })
            except: continue
    return rows

@st.cache_data(ttl=60)
def fetch_all_github_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        # 重點 2：包容所有日期開頭的 .SCP 檔
        files = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                return process_logic(res.content.decode("big5", errors="ignore"))
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
    except: return pd.DataFrame()

# --- 主介面 ---
df = fetch_all_github_data()
st.title("🍎 農會蜜棗行情大數據庫")

if not df.empty:
    # --- 頂部控制區 ---
    # 重點 3：農會單選切換 (預設燕巢)
    target_farm = st.selectbox("🏥 選擇農會", options=["燕巢", "大社", "阿蓮"], index=0)
    
    min_d, max_d = df['date_obj'].min().date(), df['date_obj'].max().date()
    date_range = st.date_input("📅 選擇日期區間", value=(max_d, max_d), min_value=min_d, max_value=max_d)
    
    search_c1, search_c2 = st.columns(2)
    with search_c1: search_sub = st.text_input("🔍 搜尋小代", placeholder="輸入代號")
    with search_c2: search_buyer = st.text_input("👤 搜尋買家", placeholder="輸入代號")

    # 側邊欄：顯示設定
    st.sidebar.header("🎨 顯示設定")
    show_level = st.sidebar.checkbox("顯示等級", value=False)
    show_total_p = st.sidebar.checkbox("顯示總價", value=False)

    # --- 過濾邏輯 (層層篩選) ---
    f_df = df[df['農會'] == target_farm].copy() # 1. 先濾農會
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        f_df = f_df[(f_df['date_obj'].dt.date >= date_range[0]) & (f_df['date_obj'].dt.date <= date_range[1])]
    if search_sub: f_df = f_df[f_df['小代'].str.contains(search_sub)]
    if search_buyer: f_df = f_df[f_df['買家'].str.contains(search_buyer)]

    # --- 表格顯示 ---
    display_cols = ["顯示日期", "小代", "件數", "公斤", "單價", "買家"]
    if show_level: display_cols.insert(1, "等級")
    if show_total_p: display_cols.insert(display_cols.index("單價")+1, "總價")
    
    st.dataframe(
        f_df[display_cols].rename(columns={"顯示日期": "日期"}), 
        use_container_width=True, height=450, hide_index=True,
        column_config={"單價": st.column_config.NumberColumn(format="%d"), "總價": st.column_config.NumberColumn(format="%d")}
    )

    # --- 底部統計摘要 (微縮版) ---
    st.divider()
    if not f_df.empty:
        t_pcs, t_kg, t_val = f_df['件數'].sum(), f_df['公斤'].sum(), f_df['總價'].sum()
        avg_p = t_val / t_kg if t_kg > 0 else 0
        st.markdown(f"##### 📉 {target_farm}區 - 數據摘要")
        cols = st.columns(6)
        m_list = [("總件數", f"{t_pcs} 件"), ("總公斤", f"{t_kg} kg"), ("最高價", f"{f_df['單價'].max()} 元"),
                  ("最低價", f"{f_df['單價'].min()} 元"), ("平均單價", f"{avg_p:.2f} 元"), ("區間總價", f"{t_val:,} 元")]
        for i, (l, v) in enumerate(m_list):
            with cols[i]:
                st.markdown(f'<div style="background-color:#f0f2f6;padding:10px;border-radius:5px;text-align:center;">'
                            f'<p style="margin:0;font-size:13px;color:#555;">{l}</p>'
                            f'<p style="margin:0;font-size:16px;font-weight:bold;color:#111;">{v}</p></div>', unsafe_allow_html=True)
    else:
        st.info(f"💡 所選期間內，{target_farm}農會無蜜棗(F22)成交紀錄。")

else:
    st.warning("😭 目前雲端倉庫中沒有可讀取的資料。")