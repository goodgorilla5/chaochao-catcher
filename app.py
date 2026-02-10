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

# --- 核心解析：針對長流水號精準切片 ---
def parse_scp_content(content):
    # 使用 4 個空格分割每一筆紀錄
    lines = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in lines:
        # 確保是燕巢(S00076)且包含芭樂(F22)或相關代碼
        if "S00076" in line:
            try:
                # 1. 定位 S00076 標籤
                s_pos = line.find("S00076")
                
                # 2. 抓取日期：S00076 前方的 7 位數字 (例如 1150210)
                # 根據 A11150210... 格式，日期出現在 S00076 前 9 到前 2 位
                date_part = line[s_pos-9 : s_pos-2]
                
                if date_part.isdigit() and len(date_part) == 7:
                    formatted_date = f"{date_part[:3]}/{date_part[3:5]}/{date_part[5:7]}"
                    
                    # 3. 流水號：取整行前 30 碼作為唯一 ID (用於去重)
                    serial = line[:30].strip().replace(" ", "")

                    # 4. 等級與小代 (位置相對於 S00076)
                    level_code = line[s_pos-2]
                    level = grade_map.get(level_code, level_code)
                    sub_id = line[s_pos+6:s_pos+9]
                    
                    # 5. 數據區 (件數+重量+單價)
                    # 格式如: 003+00018+01400+000002520+6000+4218
                    nums = line.split('+')
                    # 件數：加號前最後三碼
                    pieces = int(re.sub(r'\D', '', nums[0][-3:]))
                    # 重量：第一個加號後
                    weight = int(re.sub(r'\D', '', nums[1]))
                    # 單價：第二個加號後，拿掉非數字
                    price_raw = nums[2].split(' ')[0]
                    price = int(re.sub(r'\D', '', price_raw))
                    # 買家：最後一個加號後
                    buyer = nums[-1].strip()[:4]

                    rows.append({
                        "流水號": serial, "日期": formatted_date, "等級": level, 
                        "小代": sub_id, "件數": pieces, "公斤": weight, 
                        "單價": price, "買家": buyer
                    })
            except: continue
    return rows

@st.cache_data(ttl=300)
def fetch_all_data():
    all_data = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        
        file_list = [f for f in r.json() if f['name'].upper().endswith(('.SCP', '.TXT'))]
        
        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                text = res.content.decode("big5", errors="ignore")
                # 排除 HTML 壞檔
                if "<html" in text.lower(): return []
                return parse_scp_content(text)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(download_and_parse, file_list))
        
        for res in results: all_data.extend(res)
        df = pd.DataFrame(all_data)
        if not df.empty:
            df = df.drop_duplicates(subset="流水號")
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df
    except: return pd.DataFrame()

# --- UI 介面 ---
st.title("📊 燕巢-台北行情大數據庫")

df_all = fetch_all_data()

if not df_all.empty:
    st.sidebar.header("🛠️ 數據篩選")
    all_dates = sorted(df_all['日期'].unique(), reverse=True)
    selected_dates = st.sidebar.multiselect("📅 選擇日期 (預設全部)", all_dates)
    search_sub = st.sidebar.text_input("🔍 搜尋小代")
    show_serial = st.sidebar.checkbox("顯示原始流水號", value=False)

    filtered_df = df_all.copy()
    if selected_dates: filtered_df = filtered_df[filtered_df['日期'].isin(selected_dates)]
    if search_sub: filtered_df = filtered_df[filtered_df['小代'].str.contains(search_sub)]

    c1, c2, c3 = st.columns(3)
    c1.metric("總件數", f"{filtered_df['件數'].sum()} 件")
    c2.metric("最高單價", f"{filtered_df['單價'].max()} 元")
    c3.metric("資料筆數", f"{len(filtered_df)} 筆")

    # 控制隱藏流水號
    display_cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial: display_cols.insert(0, "流水號")
    
    st.dataframe(filtered_df[display_cols], use_container_width=True, height=600)
else:
    st.warning("⚠️ 雲端目前尚未有正確解析的資料。請確認 GitHub 中的 SCP 檔案已更新為正確版本。")