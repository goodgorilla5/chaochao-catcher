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
    st.error("❌ 請檢查 Streamlit Secrets 設定")
    st.stop()

def parse_scp_content(content):
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    # 使用您的資料特徵：以 S00076 作為绝对錨點
    for match in re.finditer(r'S00076', content):
        try:
            s_idx = match.start()
            
            # 1. 抓取日期：S00076 往前 11 到 5 位 (精準切片，不靠搜尋)
            # 例如：...114  11502101  11S00076... 
            # 位置會落在這 7 位數字上
            raw_date = content[s_idx-11 : s_idx-4]
            if not (raw_date.isdigit() and len(raw_date) == 7):
                continue
            
            formatted_date = f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}"

            # 2. 處理流水號：抓取 S00076 往前 60 位到日期前，並移除所有空格
            # 這樣不論流水號中間有沒有空格，都會結合成同一個唯一 ID
            raw_serial_part = content[max(0, s_idx-60) : s_idx-11].strip()
            full_serial = re.sub(r'\s+', '', raw_serial_part)

            # 3. 提取其他資訊 (相對 S00076 位置)
            level_code = content[s_idx-2]
            level = grade_map.get(level_code, level_code)
            sub_id = content[s_idx+6 : s_idx+9]
            
            # 4. 提取數據 (件數+重量+單價)
            # 以 S00076 後方的 + 號區段為準
            data_segment = content[s_idx+10 : s_idx+80].split('    ')[0]
            nums = data_segment.split('+')
            
            if len(nums) >= 3:
                pieces = int(re.sub(r'\D', '', nums[0][-3:]))
                weight = int(re.sub(r'\D', '', nums[1]))
                price_part = nums[2].strip().split(' ')[0]
                price = int(re.sub(r'\D', '', price_part))
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
            # 【核心】根據移除空格後的完整流水號進行去重
            df = df.drop_duplicates(subset="流水號", keep='first')
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df
    except:
        return pd.DataFrame()

# --- 主畫面 ---
st.title("📊 燕巢-台北行情大數據庫")

df = fetch_all_data()

if not df.empty:
    st.sidebar.header("🛠️ 數據篩選")
    all_dates = sorted(df['日期'].unique(), reverse=True)
    sel_dates = st.sidebar.multiselect("📅 選擇日期", all_dates)
    search_sub = st.sidebar.text_input("🔍 搜尋小代")
    show_serial = st.sidebar.checkbox("顯示合併後的流水號", value=False)

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
    st.warning("⚠️ 目前讀取到的資料格式仍無法解析，請檢查檔案內容。")