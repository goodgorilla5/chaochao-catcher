import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="燕巢台北行情大數據庫", layout="wide")

# --- 設定區 ---
REPO_OWNER = "goodgorilla5"
REPO_NAME = "chaochao-catcher"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請至 Streamlit 後台 Secrets 設定 github_token")
    st.stop()

# --- 核心解析：針對無換行長字串精準切片 ---
def parse_scp_content(content):
    # 根據您的檔案內容，每一筆紀錄是由四個空格隔開的
    entries = content.split('    ')
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for entry in entries:
        # 只抓台北市場 S00076 且是芭樂 F22 的紀錄
        if "S00076" in entry and "F22" in entry:
            try:
                # 定位市場標籤位置
                s_pos = entry.find("S00076")
                
                # 1. 抓取日期：S00076 往前 9 位到 2 位 (例如 1150210)
                date_part = entry[s_pos-9 : s_pos-2]
                if not date_part.isdigit() or len(date_part) != 7:
                    continue
                
                formatted_date = f"{date_part[:3]}/{date_part[3:5]}/{date_part[5:7]}"
                
                # 2. 流水號：取該紀錄的前 30 碼作為唯一 ID (用於去重)
                serial = entry[:30].strip().replace(" ", "")

                # 3. 等級：S00076 往前第 2 碼
                level_code = entry[s_pos-2]
                level = grade_map.get(level_code, level_code)
                
                # 4. 小代：S00076 往後第 6 碼開始的 3 位
                sub_id = entry[s_pos+6:s_pos+9]
                
                # 5. 解析數據區 (用 + 分割)
                # 格式如: 003+00018+01400+000002520+6000+4218
                nums = entry.split('+')
                if len(nums) >= 3:
                    # 件數：第一個加號前最後 3 位
                    pieces = int(re.sub(r'\D', '', nums[0][-3:]))
                    # 重量：第一個加號後
                    weight = int(re.sub(r'\D', '', nums[1]))
                    # 單價：第二個加號後
                    price_raw = nums[2].split(' ')[0]
                    price = int(re.sub(r'\D', '', price_raw))
                    # 買家：最後一節內容 (通常是四碼)
                    buyer = nums[-1].strip()[:4]

                    rows.append({
                        "流水號": serial, "日期": formatted_date, "等級": level, 
                        "小代": sub_id, "件數": pieces, "公斤": weight, 
                        "單價": price, "買家": buyer
                    })
            except Exception:
                continue
    return rows

@st.cache_data(ttl=300)
def fetch_all_data():
    all_data = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        
        # 抓取所有 .SCP 檔案
        file_list = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                # 官網檔案編碼是 big5，處理長字串
                text = res.content.decode("big5", errors="ignore")
                # 排除 HTML 網頁壞檔
                if "<html" in text.lower(): return []
                return parse_scp_content(text)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(download_and_parse, file_list))
        
        for res in results: all_data.extend(res)
        
        df = pd.DataFrame(all_data)
        if not df.empty:
            # 依據流水號去重，保證不重複計算
            df = df.drop_duplicates(subset="流水號")
            # 排序：日期(新->舊)、單價(高->低)
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df
    except: return pd.DataFrame()

# --- 主畫面介面 ---
st.title("📊 燕巢-台北行情大數據庫")

df_all = fetch_all_data()

if not df_all.empty:
    st.sidebar.header("🛠️ 數據篩選")
    all_dates = sorted(df_all['日期'].unique(), reverse=True)
    selected_dates = st.sidebar.multiselect("📅 選擇日期 (不選則顯示全部)", all_dates)
    search_sub = st.sidebar.text_input("🔍 搜尋小代 (例如 627)")
    show_serial = st.sidebar.checkbox("顯示原始流水號", value=False)

    filtered_df = df_all.copy()
    if selected_dates:
        filtered_df = filtered_df[filtered_df['日期'].isin(selected_dates)]
    if search_sub:
        filtered_df = filtered_df[filtered_df['小代'].str.contains(search_sub)]

    # 顯示統計指標
    c1, c2, c3 = st.columns(3)
    c1.metric("件數總計", f"{filtered_df['件數'].sum()} 件")
    c2.metric("最高單價", f"{filtered_df['單價'].max()} 元")
    c3.metric("資料總筆數", f"{len(filtered_df)} 筆")

    st.divider()
    
    # 控制顯示欄位
    display_cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial:
        display_cols.insert(0, "流水號")
        
    st.dataframe(filtered_df[display_cols], use_container_width=True, height=600)
    
else:
    st.warning("⚠️ 雲端目前尚未有正確解析的資料。")
    st.info("請確認 GitHub 中的 .SCP 檔案內容是否為正確的行情資料格式。")