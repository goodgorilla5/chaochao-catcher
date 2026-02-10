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

# --- 核心解析邏輯 (完全沿用您最信任的邏輯) ---
def process_logic(content):
    raw_lines = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in raw_lines:
        if "F22" in line and "S00076" in line:
            try:
                # 您的原始精準定位邏輯
                date_match = re.search(r"(\d{7,8}1)\s+\d{2}S00076", line)
                if date_match:
                    date_pos = date_match.start()
                    # 抓取日期字串並格式化
                    raw_date_str = date_match.group(1)[:7]
                    formatted_date = f"{raw_date_str[:3]}/{raw_date_str[3:5]}/{raw_date_str[5:7]}"
                    
                    # 合併流水號空格
                    serial = line[:date_pos].strip().replace(" ", "")
                    
                    remaining = line[date_pos:]
                    s_pos = remaining.find("S00076")
                    level = grade_map.get(remaining[s_pos-2], remaining[s_pos-2])
                    sub_id = remaining[s_pos+6:s_pos+9]
                    
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].replace(" ", "") or 0)
                    weight = int(nums[1].replace(" ", "") or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    # 處理單價（移除最後一位可能是校驗碼或空格的字元）
                    price = int(price_raw[:-1] if price_raw else 0)
                    buyer = nums[5].strip()[:4] if len(nums) > 5 else ""

                    rows.append({
                        "日期": formatted_date,
                        "流水號": serial, 
                        "等級": level, 
                        "小代": sub_id, 
                        "件數": pieces, 
                        "公斤": weight, 
                        "單價": price, 
                        "買家": buyer
                    })
            except: continue
    return rows

# --- 自動讀取 GitHub 所有 SCP 檔案 ---
@st.cache_data(ttl=300)
def fetch_all_github_data():
    all_data = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        
        # 找出所有 SCP 結尾的檔案
        files = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                content = res.content.decode("big5", errors="ignore")
                return process_logic(content)
            return []

        # 並行下載以提高速度
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(download_and_parse, files))
        
        for r_list in results:
            all_data.extend(r_list)
            
        df = pd.DataFrame(all_data)
        if not df.empty:
            # --- 關鍵功能：剔除重複流水號 ---
            df = df.drop_duplicates(subset="流水號", keep='first')
            # 轉換日期格式以便排序
            df['date_obj'] = pd.to_datetime(df['日期'].apply(lambda x: str(int(x.split('/')[0])+1911)+x[3:].replace('/','')), format='%Y%m%d')
            df = df.sort_values(by="date_obj", ascending=False)
        return df
    except:
        return pd.DataFrame()

# --- 主畫面 ---
st.title("📊 燕巢-台北行情大數據庫")

df = fetch_all_github_data()

if not df.empty:
    st.sidebar.header("🗓️ 查詢範圍設定")
    
    # --- 新增功能：日期區間搜尋 ---
    min_date = df['date_obj'].min()
    max_date = df['date_obj'].max()
    
    date_range = st.sidebar.date_input(
        "選擇行情日期區間",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    st.sidebar.divider()
    search_sub = st.sidebar.text_input("🔍 搜尋小代 (如 627)")
    show_serial = st.sidebar.checkbox("顯示原始流水號", value=False)

    # 過濾邏輯
    if len(date_range) == 2:
        start_date, end_date = date_range
        mask = (df['date_obj'].dt.date >= start_date) & (df['date_obj'].dt.date <= end_date)
        f_df = df.loc[mask].copy()
    else:
        f_df = df.copy()

    if search_sub:
        f_df = f_df[f_df['小代'].str.contains(search_sub)]

    # 統計資訊
    c1, c2, c3 = st.columns(3)
    c1.metric("所選區間總件數", f"{f_df['件數'].sum()} 件")
    c2.metric("區間最高單價", f"{f_df['單價'].max()} 元")
    c3.metric("資料筆數 (已去重)", f"{len(f_df)} 筆")

    # 顯示表格
    display_cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial:
        display_cols.insert(1, "流水號")
    
    st.dataframe(f_df[display_cols], use_container_width=True, height=600)

else:
    st.warning("😭 目前雲端倉庫中沒有可讀取的 SCP 檔案。")
    st.info("請確認 GitHub 倉庫 goodgorilla5/chaochao-catcher 中已有上傳 SCP 檔。")