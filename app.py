import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures
from datetime import datetime

st.set_page_config(page_title="燕巢台北行情大數據庫", layout="wide")

# --- 設定區 ---
REPO_OWNER = "goodgorilla5"
REPO_NAME = "chaochao-catcher"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請檢查 Streamlit Secrets 中的 github_token")
    st.stop()

# --- 核心解析邏輯 ---
def process_logic(content):
    raw_lines = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in raw_lines:
        if "F22" in line and "S00076" in line:
            try:
                # 使用您最信任的日期與市場代碼錨點
                date_match = re.search(r"(\d{7,8}1)\s+\d{2}S00076", line)
                if date_match:
                    date_pos = date_match.start()
                    raw_date_str = date_match.group(1)[:7] # 提取如 1150210
                    
                    # 1. 流水號合併
                    serial = line[:date_pos].strip().replace(" ", "")
                    
                    # 2. 提取等級與小代
                    remaining = line[date_pos:]
                    s_pos = remaining.find("S00076")
                    level = grade_map.get(remaining[s_pos-2], remaining[s_pos-2])
                    sub_id = remaining[s_pos+6:s_pos+9]
                    
                    # 3. 提取數據區段 (例如 003+00018+01400+000002520+6000+4218)
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].replace(" ", "") or 0)
                    weight = int(nums[1].replace(" ", "") or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    price = int(price_raw[:-1] if price_raw else 0)
                    
                    # 直接從原始資料提取「總價」 (第四個欄位：000002520)
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
            except: continue
    return rows

@st.cache_data(ttl=60)
def fetch_all_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        
        # 抓取所有包含 .SCP 的檔案 (相容 T.SCP)
        files = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
        def load_file(f_info):
            res = requests.get(f_info['download_url'], headers=headers)
            return process_logic(res.content.decode("big5", errors="ignore")) if res.status_code == 200 else []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(load_file, files))
        
        for r_list in results: all_rows.extend(r_list)
        
        df = pd.DataFrame(all_rows)
        if not df.empty:
            # 1. 剔除重複流水號
            df = df.drop_duplicates(subset="流水號", keep='first')
            # 2. 建立排序列
            df['date_obj'] = pd.to_datetime(df['日期編碼'].apply(lambda x: str(int(x[:3])+1911)+x[3:]), format='%Y%m%d')
            df = df.sort_values(by=["date_obj", "單價"], ascending=[False, False])
        return df
    except: return pd.DataFrame()

# --- 介面 ---
st.title("📊 燕巢-台北行情大數據庫")
df = fetch_all_data()

if not df.empty:
    st.sidebar.header("🗓️ 查詢設定")
    min_d, max_d = df['date_obj'].min().date(), df['date_obj'].max().date()
    
    # 預設顯示最新日期
    date_range = st.sidebar.date_input("日期區間", value=(max_d, max_d), min_value=min_d, max_value=max_d)
    search_sub = st.sidebar.text_input("🔍 搜尋小代")
    show_serial = st.sidebar.checkbox("顯示流水號", value=False)

    # 過濾
    f_df = df.copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        f_df = f_df[(f_df['date_obj'].dt.date >= date_range[0]) & (f_df['date_obj'].dt.date <= date_range[1])]
    if search_sub:
        f_df = f_df[f_df['小代'].str.contains(search_sub)]

    # 數據統計
    total_kg = f_df['公斤'].sum()
    total_val = f_df['總價'].sum()
    avg_p = total_val / total_kg if total_kg > 0 else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("總件數", f"{f_df['件數'].sum()} 件")
    m2.metric("總公斤", f"{total_kg} kg")
    m3.metric("最高價", f"{f_df['單價'].max()} 元")
    m4.metric("最低價", f"{f_df['單價'].min()} 元")
    m5.metric("平均單價", f"{avg_p:.2f} 元")

    st.divider()

    # 表格
    cols = ["顯示日期", "等級", "小代", "件數", "公斤", "單價", "總價", "買家"]
    if show_serial: cols.insert(1, "流水號")
    
    st.dataframe(
        f_df[cols].rename(columns={"顯示日期":"日期"}), 
        use_container_width=True, 
        height=600,
        column_config={
            "單價": st.column_config.NumberColumn(format="%d"),
            "總價": st.column_config.NumberColumn(format="%d")
        }
    )
else:
    st.warning("倉庫中尚無資料。")