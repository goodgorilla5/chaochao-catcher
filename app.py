import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="燕巢台北行情大數據庫", layout="wide")

REPO_OWNER = "goodgorilla5"
REPO_NAME = "chaochao-catcher"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請至 Streamlit Secrets 設定 github_token")
    st.stop()

# --- 核心解析：合併流水號並抓取資料 ---
def parse_scp_content(content):
    # 1. 先把整份內容的多餘空白縮減，但保留欄位間的區隔特徵
    # 針對流水號被斷開的問題，我們尋找像 "A11" 或 "A21" 開頭的特徵
    # 這裡採用更穩健的方法：將內容依照「真正」的間隔（通常是4個以上空格）切開
    raw_entries = re.split(r'\s{4,}', content)
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for entry in raw_entries:
        if "S00076" in entry and "F22" in entry:
            try:
                # 合併可能被斷開的流水號部分：
                # 假設格式是 [流水號] [日期...] [市場代碼]
                # 我們把 entry 內的所有空白暫時移除來提取核心資訊
                clean_entry = re.sub(r'\s+', ' ', entry.strip())
                parts = clean_entry.split(' ')
                
                # 流水號通常是第一段
                serial = parts[0]
                
                # 尋找日期：在 entry 中尋找 7 位數字且後面緊跟著 1 或 8 (代表早晚市)
                # 根據您的範例：...114  11502101  11S00076...
                date_match = re.search(r'(\d{7})[18]\s', entry)
                if date_match:
                    date_str = date_match.group(1)
                    formatted_date = f"{date_str[:3]}/{date_str[3:5]}/{date_str[5:7]}"
                else:
                    continue

                # 市場與等級標籤
                s_pos = entry.find("S00076")
                level_code = entry[s_pos-2]
                level = grade_map.get(level_code, level_code)
                sub_id = entry[s_pos+6:s_pos+9]
                
                # 數據區：件數+重量+單價
                nums = entry.split('+')
                if len(nums) >= 3:
                    pieces = int(re.sub(r'\D', '', nums[0][-3:]))
                    weight = int(re.sub(r'\D', '', nums[1]))
                    price_segment = nums[2].strip().split(' ')[0]
                    price = int(re.sub(r'\D', '', price_segment))
                    buyer = nums[-1].strip()[:4]

                    rows.append({
                        "流水號": serial,
                        "日期": formatted_date,
                        "等級": level,
                        "小代": sub_id,
                        "件數": pieces,
                        "公斤": weight,
                        "單價": price,
                        "買家": buyer
                    })
            except:
                continue
    return rows

@st.cache_data(ttl=300)
def fetch_all_data():
    all_data = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        
        files = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
        def process_file(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                text = res.content.decode("big5", errors="ignore")
                return parse_scp_content(text)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(process_file, files))
        
        for r_list in results:
            all_data.extend(r_list)
            
        df = pd.DataFrame(all_data)
        if not df.empty:
            # 【關鍵】剔除相同流水號的資料，只顯示一個
            df = df.drop_duplicates(subset="流水號", keep='first')
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df
    except:
        return pd.DataFrame()

# --- 主介面 ---
st.title("📊 燕巢-台北行情大數據庫")

df = fetch_all_data()

if not df.empty:
    st.sidebar.header("🛠️ 數據篩選")
    all_dates = sorted(df['日期'].unique(), reverse=True)
    sel_dates = st.sidebar.multiselect("📅 選擇日期", all_dates)
    search_sub = st.sidebar.text_input("🔍 搜尋小代")
    show_serial = st.sidebar.checkbox("顯示原始流水號", value=False)

    f_df = df.copy()
    if sel_dates: f_df = f_df[f_df['日期'].isin(sel_dates)]
    if search_sub: f_df = f_df[f_df['小代'].str.contains(search_sub)]

    c1, c2, c3 = st.columns(3)
    c1.metric("件數總計", f"{f_df['件數'].sum()} 件")
    c2.metric("最高價", f"{f_df['單價'].max()} 元")
    c3.metric("資料筆數", f"{len(f_df)} 筆")

    cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial: cols.insert(0, "流水號")
    
    st.dataframe(f_df[cols], use_container_width=True, height=600)
else:
    st.warning("⚠️ 目前雲端尚未有正確解析的資料。")