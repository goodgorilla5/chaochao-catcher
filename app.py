import streamlit as st
import pandas as pd
import re
import requests
import time
from datetime import datetime
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="燕巢台北行情大數據庫", layout="wide")

# --- 設定區 ---
REPO_OWNER = "goodgorilla5"
REPO_NAME = "chaochao-catcher"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"

# 讀取剛剛測試成功的 Token
try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 找不到 github_token！請至 Streamlit 後台 Secrets 設定。")
    st.stop()

# --- 核心解析邏輯 ---
def parse_scp_content(content):
    raw_lines = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in raw_lines:
        if "F22" in line and "S00076" in line:
            try:
                s_pos = line.find("S00076")
                # 抓取 7 位日期 (民國日期)
                date_match = re.search(r"(\d{7})", line[max(0, s_pos-20):s_pos])
                if date_match:
                    real_date_str = date_match.group(1)
                    formatted_date = f"{real_date_str[:3]}/{real_date_str[3:5]}/{real_date_str[5:7]}"
                    
                    # 使用超長流水號作為唯一 ID
                    date_idx = line.find(real_date_str)
                    serial = line[:date_idx+15].strip().replace(" ", "")

                    level = grade_map.get(line[s_pos-2], line[s_pos-2])
                    sub_id = line[s_pos+6:s_pos+9]
                    
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].strip() or 0)
                    weight = int(nums[1].strip() or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    price = int(re.sub(r'\D', '', price_raw) if price_raw else 0)
                    buyer = nums[5].strip()[:4]

                    rows.append({
                        "流水號": serial, "日期": formatted_date, "等級": level, 
                        "小代": sub_id, "件數": pieces, "公斤": weight, 
                        "單價": price, "買家": buyer
                    })
            except: continue
    return rows

# --- 抓取 GitHub 所有檔案 ---
@st.cache_data(ttl=300)
def fetch_all_data():
    all_data = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        
        file_list = [f for f in r.json() if f['name'].upper().endswith(('.SCP', '.TXT'))]
        if not file_list: return pd.DataFrame()

        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                # 判斷是否為真正的行情檔 (排除之前下載錯的 HTML)
                text_content = res.content.decode("big5", errors="ignore")
                if "<!DOCTYPE" in text_content or "<html>" in text_content:
                    return []
                return parse_scp_content(text_content)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(download_and_parse, file_list))
        
        for r in results: all_data.extend(r)
        
        df = pd.DataFrame(all_data)
        if not df.empty:
            df = df.drop_duplicates(subset="流水號", keep="first")
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df
    except:
        return pd.DataFrame()

# --- 網頁介面 ---
st.title("📊 燕巢-台北行情大數據庫")

with st.spinner('連線成功！正在合併雲端資料...'):
    df_all = fetch_all_data()

if not df_all.empty:
    st.sidebar.header("🛠️ 數據篩選")
    all_dates = sorted(df_all['日期'].unique(), reverse=True)
    selected_dates = st.sidebar.multiselect("📅 選擇日期 (不選則顯示全部)", all_dates)
    search_sub = st.sidebar.text_input("🔍 搜尋小代")
    
    filtered_df = df_all.copy()
    if selected_dates:
        filtered_df = filtered_df[filtered_df['日期'].isin(selected_dates)]
    if search_sub:
        filtered_df = filtered_df[filtered_df['小代'].str.contains(search_sub)]

    # 顯示統計指標
    c1, c2, c3 = st.columns(3)
    c1.metric("件數總計", f"{filtered_df['件數'].sum()} 件")
    c2.metric("區間最高單價", f"{filtered_df['單價'].max()} 元")
    c3.metric("資料筆數", f"{len(filtered_df)} 筆")

    st.divider()
    st.dataframe(filtered_df, use_container_width=True, height=600)
else:
    st.warning("⚠️ 雖然連線正常，但 GitHub 內似乎沒有正確的行情檔案。")
    st.info("請檢查 GitHub 內的 .SCP 檔案內容是否正確（不可包含 HTML 標籤）。")