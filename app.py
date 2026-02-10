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

# --- 核心解析邏輯：直接讀取第四欄總價 ---
def process_logic(content):
    # 根據您的檔案格式，紀錄間通常有 4 個空格
    raw_lines = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in raw_lines:
        # 只抓台北市場 S00076 且是芭樂 F22 的紀錄
        if "F22" in line and "S00076" in line:
            try:
                # 尋找您的精準日期錨點 (如 11502091)
                date_match = re.search(r"(\d{7,8}1)\s+\d{2}S00076", line)
                if date_match:
                    date_pos = date_match.start()
                    raw_date_str = date_match.group(1)[:7] # 提取如 1150210
                    
                    # 1. 流水號合併 (移除空格避免重複)
                    serial = line[:date_pos].strip().replace(" ", "")
                    
                    # 2. 定位等級與小代 (相對 S00076 位置)
                    remaining = line[date_pos:]
                    s_pos = remaining.find("S00076")
                    level = grade_map.get(remaining[s_pos-2], remaining[s_pos-2])
                    sub_id = remaining[s_pos+6:s_pos+9]
                    
                    # 3. 提取數據區段 (例如 003+00018+01400+000002520)
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].replace(" ", "") or 0)
                    weight = int(nums[1].replace(" ", "") or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    price = int(price_raw[:-1] if price_raw else 0)
                    
                    # 直接從原始資料抓取第四個區段作為「總價」
                    total_price = int(nums[3].replace(" ", "") or 0)
                    
                    # 買家欄位
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

# --- 從 GitHub 抓取所有資料 ---
@st.cache_data(ttl=60)
def fetch_all_github_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        
        # 抓取所有 .SCP 檔案
        files = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                text = res.content.decode("big5", errors="ignore")
                return process_logic(text)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(download_and_parse, files))
        
        for r_list in results: 
            all_rows.extend(r_list)
            
        df = pd.DataFrame(all_rows)
        if not df.empty:
            # 依據流水號去重
            df = df.drop_duplicates(subset="流水號", keep='first')
            # 轉換日期供內部排序與篩選
            df['date_obj'] = pd.to_datetime(df['日期編碼'].apply(lambda x: str(int(x[:3])+1911)+x[3:]), format='%Y%m%d')
            df = df.sort_values(by=["date_obj", "單價"], ascending=[False, False])
        return df
    except:
        return pd.DataFrame()

# --- 主介面 ---
df = fetch_all_github_data()

if not df.empty:
    st.sidebar.header("🗓️ 查詢範圍設定")
    
    # 獲取資料庫日期範圍
    min_d = df['date_obj'].min().date()
    max_d = df['date_obj'].max().date()
    
    # 預設日期區間設定為「最新的一天」
    date_range = st.sidebar.date_input(
        "選擇查詢區間",
        value=(max_d, max_d),
        min_value=min_d,
        max_value=max_d
    )

    st.sidebar.divider()
    search_sub = st.sidebar.text_input("🔍 搜尋小代 (如 627)")
    show_serial = st.sidebar.checkbox("顯示原始流水號", value=False)

    # 資料過濾邏輯
    f_df = df.copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        f_df = f_df[(f_df['date_obj'].dt.date >= start_date) & (f_df['date_obj'].dt.date <= end_date)]
    
    if search_sub:
        f_df = f_df[f_df['小代'].str.contains(search_sub)]

    # --- 數據統計計算 ---
    t_pcs = f_df['件數'].sum()
    t_kg = f_df['公斤'].sum()
    t_val = f_df['總價'].sum()
    avg_p = t_val / t_kg if t_kg > 0 else 0

    # --- 顯示標題與六大指標 ---
    st.title("📊 燕巢-台北行情大數據庫")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("總件數", f"{t_pcs} 件")
    m2.metric("總公斤", f"{t_kg} kg")
    m3.metric("最高價", f"{f_df['單價'].max()} 元")
    m4.metric("最低價", f"{f_df['單價'].min()} 元")
    m5.metric("平均單價", f"{avg_p:.2f} 元")
    m6.metric("區間總價", f"{t_val:,} 元")

    st.divider()

    # --- 行情表格顯示 ---
    display_cols = ["顯示日期", "等級", "小代", "件數", "公斤", "單價", "總價", "買家"]
    if show_serial:
        display_cols.insert(1, "流水號")
    
    st.dataframe(
        f_df[display_cols].rename(columns={"顯示日期": "日期"}), 
        use_container_width=True, 
        height=600,
        column_config={
            "單價": st.column_config.NumberColumn(format="%d"),
            "總價": st.column_config.NumberColumn(format="%d")
        }
    )
else:
    st.warning("😭 目前雲端倉庫中沒有可讀取的資料。")