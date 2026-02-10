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
    st.error("❌ 密鑰設定錯誤，請檢查 Streamlit Secrets")
    st.stop()

def parse_scp_content(content):
    # 這裡放寬分割條件，嘗試用換行或多空格分割
    lines = re.split(r'\n|\r| {4,}', content)
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in lines:
        # 只要包含 S00076 (台北) 就嘗試解析
        if "S00076" in line:
            try:
                s_pos = line.find("S00076")
                # 抓取 S00076 前方的 7 位日期
                date_part = line[s_pos-9 : s_pos-2]
                
                if date_part.isdigit():
                    real_date_str = date_part
                    formatted_date = f"{real_date_str[:3]}/{real_date_str[3:5]}/{real_date_str[5:7]}"
                    serial = line[:30].strip().replace(" ", "")
                    level = grade_map.get(line[s_pos-2], line[s_pos-2])
                    sub_id = line[s_pos+6:s_pos+9]
                    
                    # 處理數據區
                    nums = line.split('+')
                    pieces = int(re.sub(r'\D', '', nums[0][-3:]) if len(nums)>0 else 0)
                    weight = int(re.sub(r'\D', '', nums[1]) if len(nums)>1 else 0)
                    price_match = re.search(r'(\d+)', nums[2]) if len(nums)>2 else None
                    price = int(price_match.group(1)) if price_match else 0
                    buyer = nums[5].strip()[:4] if len(nums)>5 else "未知"

                    rows.append({
                        "流水號": serial, "日期": formatted_date, "等級": level, 
                        "小代": sub_id, "件數": pieces, "公斤": weight, 
                        "單價": price, "買家": buyer
                    })
            except: continue
    return rows

@st.cache_data(ttl=60)
def fetch_all_data():
    all_data = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame(), []
        
        file_list = [f for f in r.json() if f['name'].upper().endswith(('.SCP', '.TXT'))]
        found_files = [f['name'] for f in file_list]
        
        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                text = res.content.decode("big5", errors="ignore")
                if "<!DOCTYPE" in text or "<html>" in text: return []
                return parse_scp_content(text)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(download_and_parse, file_list))
        
        for res in results: all_data.extend(res)
        df = pd.DataFrame(all_data)
        if not df.empty:
            df = df.drop_duplicates(subset="流水號")
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df, found_files
    except: return pd.DataFrame(), []

st.title("📊 燕巢-台北行情大數據庫")

df_all, found_files = fetch_all_data()

# 除錯資訊：顯示目前在雲端看到哪些檔案
with st.expander("📂 雲端檔案清單 (除錯用)"):
    st.write(f"目前偵測到 {len(found_files)} 個檔案：", found_files)

if not df_all.empty:
    st.sidebar.header("🛠️ 數據篩選")
    all_dates = sorted(df_all['日期'].unique(), reverse=True)
    selected_dates = st.sidebar.multiselect("📅 選擇日期", all_dates)
    search_sub = st.sidebar.text_input("🔍 搜尋小代")
    show_serial = st.sidebar.checkbox("顯示原始流水號", value=False)

    filtered_df = df_all.copy()
    if selected_dates: filtered_df = filtered_df[filtered_df['日期'].isin(selected_dates)]
    if search_sub: filtered_df = filtered_df[filtered_df['小代'].str.contains(search_sub)]

    c1, c2, c3 = st.columns(3)
    c1.metric("件數總計", f"{filtered_df['件數'].sum()} 件")
    c2.metric("最高單價", f"{filtered_df['單價'].max()} 元")
    c3.metric("資料筆數", f"{len(filtered_df)} 筆")

    display_cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial: display_cols.insert(0, "流水號")
    st.dataframe(filtered_df[display_cols], use_container_width=True, height=600)
else:
    st.warning("⚠️ 雖然看到了檔案，但內容解析不出行情數據。")
    st.info("請檢查檔案內容是否為純文字，而非網頁 HTML。")