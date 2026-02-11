import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 農會與市場代碼對照表
FARMER_MAP = {
    "燕巢": "S00076",
    "大社": "S00250",
    "阿蓮": "S00098"
}

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請至 Streamlit 後台 Secrets 設定 github_token")
    st.stop()

# --- 核心解析邏輯 (S00 錨點統合版) ---
def process_logic(content):
    # 統一將換行處理掉，並以 4 個以上空格切分筆數
    parts = re.split(r'\s{4,}', content)
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in parts:
        line = line.strip()
        # 關鍵過濾：必須包含 F22 (蜜棗) 且包含市場標籤 S00
        if "F22" in line and "S00" in line:
            try:
                # 1. 判定農會
                belong_to = "未知"
                for name, code in FARMER_MAP.items():
                    if code in line:
                        belong_to = name
                        break
                if belong_to == "未知": continue

                # 2. 定位 S00 錨點
                m_pos = line.find("S00")
                if m_pos < 10: continue 

                # 3. 提取等級 (S00 往前 2 位，取第一碼)
                # 例如 ...21S00... 取 '2'
                level_code = line[m_pos-2]
                level = grade_map.get(level_code, level_code)

                # 4. 提取日期 (S00 往前 10 位至 2 位之間是日期 11502111)
                # 我們直接抓這區間的數字
                date_part = line[m_pos-10:m_pos-2].strip()
                raw_date_str = date_part[:7] # 取前 7 位民國年

                # 5. 處理流水號 (S00 往前 10 位之前的內容，不論多長，全部去空格)
                serial_raw = line[:m_pos-10].strip()
                serial = serial_raw.replace(" ", "")

                # 6. 提取小代 (市場代碼 S00XXX 之後的 3 位)
                sub_id = line[m_pos+6:m_pos+9].strip()

                # 7. 數值提取 (根據 + 號)
                nums = line.split('+')
                pieces = int(nums[0][-3:].strip() or 0)
                weight = int(nums[1].strip() or 0)
                price_part = nums[2].strip().split(' ')[0]
                price = int(price_part[:-1] if price_part else 0)
                total_price = int(nums[3].strip() or 0)
                buyer = nums[-1].strip()[:4] # 最後一個 + 號後為買家

                rows.append({
                    "農會": belong_to,
                    "日期編碼": raw_date_str,
                    "顯示日期": f"{raw_date_str[:3]}/{raw_date_str[3:5]}/{raw_date_str[5:7]}",
                    "流水號": serial, "等級": level, "小代": sub_id, 
                    "件數": pieces, "公斤": weight, "單價": price, 
                    "總價": total_price, "買家": buyer
                })
            except: continue
    return rows

@st.cache_data(ttl=60)
def fetch_all_github_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    REPO_OWNER = "goodgorilla5"
    REPO_NAME = "chaochao-catcher"
    API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"
    
    try:
        r = requests.get(API_URL, headers=headers)
        if r.status_code != 200: return pd.DataFrame()
        # 抓取倉庫內所有 .SCP 檔案
        files = [f for f in r.json() if f['name'].lower().endswith('.scp')]
        
        def download_and_parse(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            if res.status_code == 200:
                return process_logic(res.content.decode("big5", errors="ignore"))
            return []
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(download_and_parse, files))
        
        for r_list in results: all_rows.extend(r_list)
        df = pd.DataFrame(all_rows)
        if not df.empty:
            df = df.drop_duplicates(subset="流水號", keep='first')
            # 轉換日期物件用於排序
            df['date_obj'] = pd.to_datetime(df['日期編碼'].apply(lambda x: str(int(x[:3])+1911)+x[3:]), format='%Y%m%d')
            df = df.sort_values(by=["date_obj", "單價"], ascending=[False, False])
        return df
    except: return pd.DataFrame()

# --- 主介面 ---
st.title("🍎 農會蜜棗行情大數據庫")
df = fetch_all_github_data()

if not df.empty:
    # 第一層過濾：選擇農會
    target_farm = st.selectbox("🏥 選擇農會", options=["燕巢", "大社", "阿蓮"], index=0)
    
    # 日期區間
    min_d, max_d = df['date_obj'].min().date(), df['date_obj'].max().date()
    date_range = st.date_input("📅 選擇日期區間", value=(max_d, max_d), min_value=min_d, max_value=max_d)
    
    # 搜尋欄位
    sc1, sc2 = st.columns(2)
    with sc1: search_sub = st.text_input("🔍 搜尋小代", placeholder="輸入代號")
    with sc2: search_buyer = st.text_input("👤 搜尋買家", placeholder="輸入代號")

    # 側邊欄
    st.sidebar.header("🎨 顯示設定")
    show_level = st.sidebar.checkbox("顯示等級", value=False)
    show_total_p = st.sidebar.checkbox("顯示總價", value=False)

    # 執行過濾
    f_df = df[df['農會'] == target_farm].copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        f_df = f_df[(f_df['date_obj'].dt.date >= date_range[0]) & (f_df['date_obj'].dt.date <= date_range[1])]
    if search_sub: f_df = f_df[f_df['小代'].str.contains(search_sub)]
    if search_buyer: f_df = f_df[f_df['買家'].str.contains(search_buyer)]

    # 顯示表格
    display_cols = ["顯示日期", "小代", "件數", "公斤", "單價", "買家"]
    if show_level: display_cols.insert(1, "等級")
    if show_total_p: display_cols.insert(display_cols.index("單價")+1, "總價")
    
    st.dataframe(f_df[display_cols].rename(columns={"顯示日期": "日期"}), 
                 use_container_width=True, height=450, hide_index=True)

    # 底部統計 (微縮字體)
    st.divider()
    if not f_df.empty:
        t_pcs, t_kg, t_val = f_df['件數'].sum(), f_df['公斤'].sum(), f_df['總價'].sum()
        avg_p = t_val / t_kg if t_kg > 0 else 0
        st.markdown(f"##### 📉 {target_farm}區 - 數據摘要")
        cols = st.columns(6)
        m_list = [("總件數", f"{t_pcs} 件"), ("總公斤", f"{t_kg} kg"), ("最高價", f"{f_df['單價'].max()} 元"),
                  ("最低價", f"{f_df['單價'].min()} 元"), ("平均單價", f"{avg_p:.2f} 元"), ("區間總價", f"{t_val:,} 元")]
        for i, (l, v) in enumerate(m_list):
            with cols[i]:
                st.markdown(f'<div style="background-color:#f0f2f6;padding:10px;border-radius:5px;text-align:center;">'
                            f'<p style="margin:0;font-size:12px;color:#555;">{l}</p>'
                            f'<p style="margin:0;font-size:15px;font-weight:bold;color:#111;">{v}</p></div>', unsafe_allow_html=True)
    else:
        st.info(f"💡 目前選擇的條件下無 F22 蜜棗交易紀錄。")

else:
    st.warning("😭 倉庫中目前沒有任何 .SCP 檔案或讀取失敗。")