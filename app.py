import streamlit as st
import pandas as pd
import re
import requests
from datetime import datetime
import concurrent.futures

st.set_page_config(page_title="燕巢台北行情資料庫", layout="wide")

REPO_OWNER = "goodgorilla5"
REPO_NAME = "chaochao-catcher"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"

# --- 解析邏輯 (保持原有解析邏輯) ---
def parse_scp_content(content):
    raw_lines = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    for line in raw_lines:
        if "F22" in line and "S00076" in line:
            try:
                date_match = re.search(r"(\d{7,8}1)\s+\d{2}S00076", line)
                if date_match:
                    date_pos = date_match.start()
                    serial = line[:date_pos].strip().replace(" ", "")
                    # 從流水號提取日期 (假設前 7 位是民國年月日)
                    record_date = f"{serial[:3]}/{serial[3:5]}/{serial[5:7]}"
                    
                    remaining = line[date_pos:]
                    s_pos = remaining.find("S00076")
                    level = grade_map.get(remaining[s_pos-2], remaining[s_pos-2])
                    sub_id = remaining[s_pos+6:s_pos+9]
                    
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].replace(" ", "") or 0)
                    weight = int(nums[1].replace(" ", "") or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    price = int(price_raw[:-1] if price_raw else 0)
                    buyer = nums[5].strip()[:4]

                    rows.append({
                        "流水號": serial, "日期": record_date, "等級": level, 
                        "小代": sub_id, "件數": pieces, "公斤": weight, 
                        "單價": price, "買家": buyer
                    })
            except: continue
    return rows

# --- 批次抓取 GitHub 所有檔案 ---
@st.cache_data(ttl=300)
def fetch_all_data():
    all_data = []
    try:
        # 1. 先獲取檔案列表
        r = requests.get(API_URL)
        if r.status_code != 200: return []
        
        files = [f['download_url'] for f in r.json() if f['name'].endswith(('.SCP', '.txt'))]
        
        # 2. 並行下載提升速度
        def download_and_parse(url):
            res = requests.get(url)
            return parse_scp_content(res.content.decode("big5", errors="ignore")) if res.status_code == 200 else []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(download_and_parse, files))
        
        for r in results: all_data.extend(r)
        
        # 3. 核心功能：利用流水號去重
        df = pd.DataFrame(all_data)
        if not df.empty:
            df = df.drop_duplicates(subset="流水號", keep="first")
            df = df.sort_values(by="流水號", ascending=False)
        return df
    except Exception as e:
        st.error(f"連線失敗: {e}")
        return pd.DataFrame()

# --- 介面設計 ---
st.title("📊 燕巢-台北行情大數據庫")

df_all = fetch_all_data()

if not df_all.empty:
    # --- 側邊欄篩選區 ---
    st.sidebar.header("🛠️ 篩選條件")
    
    # 日期區間篩選
    all_dates = sorted(df_all['日期'].unique(), reverse=True)
    date_range = st.sidebar.select_slider("選擇日期範圍", options=all_dates, value=(all_dates[-1], all_dates[0]))
    
    # 小代搜尋
    search_sub = st.sidebar.text_input("🔍 搜尋小代 (如 627)")
    
    # 過濾資料
    mask = (df_all['日期'] >= date_range[0]) & (df_all['日期'] <= date_range[1])
    filtered_df = df_all[mask]
    
    if search_sub:
        filtered_df = filtered_df[filtered_df['小代'].str.contains(search_sub)]

    # --- 數據統計卡片 ---
    c1, c2, c3 = st.columns(3)
    c1.metric("當前總件數", f"{filtered_df['件數'].sum()} 件")
    c2.metric("最高單價", f"{filtered_df['單價'].max()} 元")
    c3.metric("資料天數", f"{len(filtered_df['日期'].unique())} 天")

    # --- 資料表格 ---
    st.dataframe(filtered_df, use_container_width=True, height=500)
    
    # 匯出功能
    st.download_button("📥 下載目前篩選資料 (Excel格式)", 
                       filtered_df.to_csv(index=False).encode('utf-8-sig'),
                       "market_data.csv", "text/csv")
else:
    st.info("目前雲端倉庫中沒有有效的 SCP 檔案。")