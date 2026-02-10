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

# --- 核心解析：應對無換行長字串格式 ---
def parse_scp_content(content):
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    # 使用「四個空格」作為每一筆交易紀錄的切割點
    entries = content.split('    ')
    
    for entry in entries:
        # 只抓取包含台北市場 (S00076) 的紀錄
        if "S00076" in entry:
            try:
                # 定位市場代碼 S00076
                s_pos = entry.find("S00076")
                
                # 1. 抓取日期：S00076 往前數第 9 到第 2 位 (例如 1150210)
                date_part = entry[s_pos-9 : s_pos-2]
                if not date_part.isdigit() or len(date_part) != 7:
                    continue
                
                formatted_date = f"{date_part[:3]}/{date_part[3:5]}/{date_part[5:7]}"
                
                # 2. 流水號：取該筆紀錄的前 30 碼（包含日期雜訊也沒關係，只要唯一即可）
                serial = entry[:30].strip()

                # 3. 等級與小代
                # 等級在 S00076 往前 2 格
                level_code = entry[s_pos-2]
                level = grade_map.get(level_code, level_code)
                # 小代在 S00076 往後 6 格開始的 3 位
                sub_id = entry[s_pos+6:s_pos+9]
                
                # 4. 解析數據區 (件數+重量+單價)
                # 格式: 003+00018+01400+...
                parts = entry.split('+')
                if len(parts) >= 3:
                    # 件數：第一個加號前的最後 3 位
                    pieces = int(re.sub(r'\D', '', parts[0][-3:]))
                    # 公斤：第一個與第二個加號之間
                    weight = int(re.sub(r'\D', '', parts[1]))
                    # 單價：第二個加號後面的數字段
                    price_str = parts[2].strip().split(' ')[0]
                    price = int(re.sub(r'\D', '', price_str))
                    # 買家：最後一個加號後面的內容 (通常是後四碼)
                    buyer = parts[-1].strip()[:4]

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
        
        # 過濾出所有 SCP 檔案
        files = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
        def process_file(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                # 官網原始檔案編碼是 big5
                text = res.content.decode("big5", errors="ignore")
                # 排除 HTML 殘留檔
                if "<!DOCTYPE" in text or "<html>" in text:
                    return []
                return parse_scp_content(text)
            return []

        # 使用並行下載
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(process_file, files))
        
        for r_list in results:
            all_data.extend(r_list)
            
        df = pd.DataFrame(all_data)
        if not df.empty:
            # 依據流水號排除重複
            df = df.drop_duplicates(subset="流水號")
            # 排序：日期由新到舊，價格由高到低
            df = df.sort_values(by=["日期", "單價"], ascending=[False, False])
        return df
    except Exception as e:
        return pd.DataFrame()

# --- 網頁主畫面 ---
st.title("📊 燕巢-台北行情大數據庫")

# 獲取資料
df = fetch_all_data()

if not df.empty:
    st.sidebar.header("🛠️ 數據篩選")
    
    # 1. 日期多選
    all_dates = sorted(df['日期'].unique(), reverse=True)
    sel_dates = st.sidebar.multiselect("📅 選擇日期 (不選則顯示全部)", all_dates)
    
    # 2. 小代搜尋
    search_sub = st.sidebar.text_input("🔍 搜尋小代 (如 627)")
    
    # 3. 流水號開關
    show_serial = st.sidebar.checkbox("顯示原始流水號 (預設隱藏)", value=False)

    # 過濾邏輯
    f_df = df.copy()
    if sel_dates:
        f_df = f_df[f_df['日期'].isin(sel_dates)]
    if search_sub:
        f_df = f_df[f_df['小代'].str.contains(search_sub)]

    # 頂部統計指標
    c1, c2, c3 = st.columns(3)
    c1.metric("總件數", f"{f_df['件數'].sum()} 件")
    c2.metric("最高單價", f"{f_df['單價'].max()} 元")
    c3.metric("資料筆數", f"{len(f_df)} 筆")

    st.divider()
    
    # 欄位顯示設定
    cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial:
        cols.insert(0, "流水號")
    
    st.dataframe(f_df[cols], use_container_width=True, height=600)
else:
    st.warning("⚠️ 目前雲端尚未有可正確解析的資料。")
    st.info("請確認 GitHub 中的 .SCP 檔案是用書籤手動下載的版本。")