import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

st.set_page_config(page_title="燕巢台北行情大數據庫", layout="wide")

REPO_OWNER = "goodgorilla5"
REPO_NAME = "chaochao-catcher"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請檢查 Streamlit Secrets")
    st.stop()

def parse_scp_content(content):
    # 每一筆資料之間通常有 4 個空格，我們先切開
    entries = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for entry in entries:
        if "S00076" in entry:
            try:
                s_pos = entry.find("S00076")
                
                # --- 1. 精準抓取日期 ---
                # 在 S00076 往前 25 個字元的範圍內尋找「連續 7 位數字」
                search_area = entry[max(0, s_pos-25) : s_pos]
                date_match = re.search(r'(\d{7})', search_area)
                
                if date_match:
                    real_date = date_match.group(1) # 這才是真正的 1150210
                    formatted_date = f"{real_date[:3]}/{real_date[3:5]}/{real_date[5:7]}"
                else:
                    continue # 找不到日期就跳過，避免出現 881年

                # --- 2. 處理流水號 (合併空格並去重) ---
                # 抓取 S00076 之前的所有內容作為流水號區
                raw_serial_area = entry[:s_pos-2].strip()
                # 強制合併中間所有空格，確保 A111... 變成唯一 ID
                full_serial = re.sub(r'\s+', '', raw_serial_area)

                # --- 3. 抓取其他欄位 ---
                level_code = entry[s_pos-2]
                level = grade_map.get(level_code, level_code)
                sub_id = entry[s_pos+6:s_pos+9]
                
                # --- 4. 解析數據區 ---
                nums = entry.split('+')
                if len(nums) >= 3:
                    pieces = int(re.sub(r'\D', '', nums[0][-3:]))
                    weight = int(re.sub(r'\D', '', nums[1]))
                    price_val = nums[2].strip().split(' ')[0]
                    price = int(re.sub(r'\D', '', price_val))
                    buyer = nums[-1].strip()[:4]

                    rows.append({
                        "流水號": full_serial,
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
        
        for r_list in results: all_data.extend(r_list)
        df = pd.DataFrame(all_data)
        if not df.empty:
            # 【核心】強制合併空格後的流水號去重
            df = df.drop_duplicates(subset="流水號", keep='first')
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df
    except: return pd.DataFrame()

st.title("📊 燕巢-台北行情大數據庫")

df = fetch_all_data()

if not df.empty:
    st.sidebar.header("🛠️ 數據篩選")
    all_dates = sorted(df['日期'].unique(), reverse=True)
    sel_dates = st.sidebar.multiselect("📅 選擇日期", all_dates)
    search_sub = st.sidebar.text_input("🔍 搜尋小代")
    show_serial = st.sidebar.checkbox("顯示合併後的流水號 (除錯用)", value=False)

    f_df = df.copy()
    if sel_dates: f_df = f_df[f_df['日期'].isin(sel_dates)]
    if search_sub: f_df = f_df[f_df['小代'].str.contains(search_sub)]

    c1, c2, c3 = st.columns(3)
    c1.metric("件數總計", f"{f_df['件數'].sum()} 件")
    c2.metric("最高單價", f"{f_df['單價'].max()} 元")
    c3.metric("資料筆數", f"{len(f_df)} 筆")

    cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial: cols.insert(0, "流水號")
    st.dataframe(f_df[cols], use_container_width=True, height=600)
else:
    st.warning("⚠️ 解析失敗，請檢查檔案內容是否正確。")