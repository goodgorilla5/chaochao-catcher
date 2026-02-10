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
    st.error("❌ 請檢查 Streamlit Secrets 中的 github_token 設定")
    st.stop()

# --- 核心解析：應對長字串格式 ---
def parse_scp_content(content):
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    # 因為你的檔案是一整行連在一起的，我們用 "A11" 或 "A21" 這種流水號開頭來拆分
    # 或者更簡單：直接尋找所有的 "S00076" 標籤
    # 我們將字串依照 "    " (四個空格) 拆分成每一筆
    entries = content.split('    ')
    
    for entry in entries:
        if "S00076" in entry and "F22" in entry:
            try:
                # 定位市場代碼
                s_pos = entry.find("S00076")
                
                # 1. 抓取日期 (從 S00076 往前數第 9 位到第 2 位)
                date_part = entry[s_pos-9 : s_pos-2]
                if not date_part.isdigit(): continue
                
                formatted_date = f"{date_part[:3]}/{date_part[3:5]}/{date_part[5:7]}"
                
                # 2. 流水號 (取該筆資料的前 30 碼)
                serial = entry[:30].strip()

                # 3. 等級與小代
                level_code = entry[s_pos-2]
                level = grade_map.get(level_code, level_code)
                sub_id = entry[s_pos+6:s_pos+9]
                
                # 4. 解析數據區 (件數+重量+單價)
                # 格式範例: 003+00018+01400+000002520+6000+4218
                parts = entry.split('+')
                if len(parts) >= 3:
                    # 件數：第一個加號前的最後 3 位
                    pieces = int(re.sub(r'\D', '', parts[0][-3:]))
                    # 公斤：第一個加號與第二個加號之間
                    weight = int(re.sub(r'\D', '', parts[1]))
                    # 單價：第二個加號後面的數字 (取前 5 位或空格前)
                    price_str = parts[2].strip().split(' ')[0]
                    price = int(re.sub(r'\D', '', price_str))
                    # 買家：最後一節
                    buyer = parts[-1].strip()[:4]

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
        
        # 抓取所有 SCP 檔案
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
            # 根據流水號去重
            df = df.drop_duplicates(subset="流水號")
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df
    except:
        return pd.DataFrame()

# --- 主畫面 ---
st.title("📊 燕巢-台北行情大數據庫")

df = fetch_all_data()

if not df.empty:
    st.sidebar.header("🛠️ 數據篩選")
    
    # 日期多選
    all_dates = sorted(df['日期'].unique(), reverse=True)
    sel_dates = st.sidebar.multiselect("📅 選擇日期", all_dates)
    
    # 小代搜尋
    search_sub = st.sidebar.text_input("🔍 搜尋小代 (如 627)")
    
    # 流水號顯示開關
    show_serial = st.sidebar.checkbox("顯示原始流水號", value=False)

    # 過濾
    f_df = df.copy()
    if sel_dates:
        f_df = f_df[f_df['日期'].isin(sel_dates)]
    if search_sub:
        f_df = f_df[f_df['小代'].str.contains(search_sub)]

    # 指標
    c1, c2, c3 = st.columns(3)
    c1.metric("件數總計", f"{f_df['件數'].sum()} 件")
    c2.metric("區間最高單價", f"{f_df['單價'].max()} 元")
    c3.metric("資料筆數", f"{len(f_df)} 筆")

    st.divider()
    
    # 顯示欄位控制
    cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial:
        cols.insert(0, "流水號")
    
    st.dataframe(f_df[cols], use_container_width=True, height=600)
else:
    st.warning("⚠️ 檔案內容讀取失敗，請確認 GitHub 中的檔案內容為正確的行情資料。")