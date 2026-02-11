import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 農會定義與市場代碼對照
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

# --- 核心解析邏輯 (修正版) ---
def process_logic(content):
    # 檔案切分：有些檔案是用多個空格，有些是固定寬度，我們用正則表達式切分較保險
    raw_lines = re.split(r'\s{4,}', content) 
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in raw_lines:
        # 重點：只抓 F22 (蜜棗)，並過濾掉空行
        if "F22" in line and "+" in line:
            try:
                # 1. 判定農會歸屬
                belong_to = "未知"
                for name, code in FARMER_MAP.items():
                    if code in line:
                        belong_to = name
                        break
                
                # 2. 抓取日期 (包容 7 位或 8 位日期)
                date_match = re.search(r"(\d{7,8})", line)
                if not date_match: continue
                raw_date_str = date_match.group(1)[:7]

                # 3. 處理流水號：取市場代碼前的所有字元並去空格
                # 先找市場代碼 (例如 S00076)
                m_match = re.search(r"[S|T]\d{5}", line)
                if not m_match: continue
                m_pos = m_match.start()
                
                # 市場代碼前即為流水號區段
                serial = line[:m_pos-2].strip().replace(" ", "")
                
                # 4. 等級與小代
                # 等級通常在市場代碼前 2 位
                level_code = line[m_pos-2]
                level = grade_map.get(level_code, level_code)
                # 小代在市場代碼後 6 位開始的 3 碼
                sub_id = line[m_pos+6:m_pos+9].strip()
                
                # 5. 數值提取 (件數+公斤+單價+總價+...+)
                nums = line.split('+')
                pieces = int(nums[0][-3:].replace(" ", "") or 0)
                weight = int(nums[1].replace(" ", "") or 0)
                price_raw = nums[2].strip().split(' ')[0]
                price = int(price_raw[:-1] if price_raw else 0)
                total_price = int(nums[3].replace(" ", "") or 0)
                buyer = nums[5].strip()[:4] if len(nums) > 5 else ""

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
        files = [f for f in r.json() if f['name'].upper().endswith('.SCP')]
        
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
            df['date_obj'] = pd.to_datetime(df['日期編碼'].apply(lambda x: str(int(x[:3])+1911)+x[3:]), format='%Y%m%d')
            df = df.sort_values(by=["date_obj", "單價"], ascending=[False, False])
        return df
    except: return pd.DataFrame()

# --- 主介面 ---
st.title("🍎 農會蜜棗行情大數據庫")
df = fetch_all_github_data()

if not df.empty:
    # 農會單選 (隔離數據)
    target_farm = st.selectbox("🏥 選擇農會", options=["燕巢", "大社", "阿蓮"], index=0)
    
    # 日期與搜尋控制
    min_d, max_d = df['date_obj'].min().date(), df['date_obj'].max().date()
    date_range = st.date_input("📅 選擇日期區間", value=(max_d, max_d), min_value=min_d, max_value=max_d)
    
    sc1, sc2 = st.columns(2)
    with sc1: search_sub = st.text_input("🔍 搜尋小代")
    with sc2: search_buyer = st.text_input("👤 搜尋買家")

    st.sidebar.header("🎨 顯示設定")
    show_level = st.sidebar.checkbox("顯示等級", value=False)
    show_total_p = st.sidebar.checkbox("顯示總價", value=False)

    # 過濾
    f_df = df[df['農會'] == target_farm].copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        f_df = f_df[(f_df['date_obj'].dt.date >= date_range[0]) & (f_df['date_obj'].dt.date <= date_range[1])]
    if search_sub: f_df = f_df[f_df['小代'].str.contains(search_sub)]
    if search_buyer: f_df = f_df[f_df['買家'].str.contains(search_buyer)]

    # 表格
    display_cols = ["顯示日期", "小代", "件數", "公斤", "單價", "買家"]
    if show_level: display_cols.insert(1, "等級")
    if show_total_p: display_cols.insert(display_cols.index("單價")+1, "總價")
    
    st.dataframe(f_df[display_cols].rename(columns={"顯示日期": "日期"}), 
                 use_container_width=True, height=450, hide_index=True)

    # 底部統計 (HTML 微縮版)
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
        st.info(f"💡 目前 {target_farm} 無相關 F22 成交資料。")
else:
    st.warning("😭 讀取失敗：請檢查 GitHub 檔案或 Token 是否正確。")