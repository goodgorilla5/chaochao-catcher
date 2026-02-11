import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 農會對照
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請至 Streamlit 後台 Secrets 設定 github_token")
    st.stop()

def parse_farmer_data(content):
    # 改用更寬鬆的切割：只要是連續空格 (2個以上) 或換行就切開
    chunks = re.split(r'\s{2,}|\n', content)
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for chunk in chunks:
        chunk = chunk.strip()
        # 只要包含 F22 (蜜棗) 且包含 S00 市場標記
        if "F22" in chunk and "S00" in chunk and "+" in chunk:
            try:
                # 1. 定位 S00 錨點
                s_idx = chunk.find("S00")
                if s_idx < 10: continue

                # 2. 根據您的法則：S00 往前推 10 碼是日期與等級
                # 位置：[流水號...][日期8碼][等級2碼][S00...]
                # 等級就在 S00 的前 2 碼
                level_code = chunk[s_idx-2] # 取得 1, 2 或 3
                level = grade_map.get(level_code, level_code)

                # 日期就在等級的前 8 碼 (11502111)
                date_str_raw = chunk[s_idx-10 : s_idx-2].strip()
                display_date = f"{date_str_raw[:3]}/{date_str_raw[3:5]}/{date_str_raw[5:7]}"
                date_for_obj = date_str_raw[:7]

                # 流水號就是日期之前的所有字元，直接去空格
                serial = chunk[:s_idx-10].strip().replace(" ", "")

                # 3. 判定農會
                farm_name = "其他"
                for name, code in FARMER_MAP.items():
                    if code in chunk:
                        farm_name = name
                        break
                
                # 4. 提取小代 (S00XXX 之後的 3 碼)
                sub_id = chunk[s_idx+6 : s_idx+9].strip()

                # 5. 提取數據段 (+ 號連接的部分)
                parts = chunk.split('+')
                pieces = int(parts[0][-3:].strip() or 0)
                weight = int(parts[1].strip() or 0)
                # 單價去掉最後一碼 0
                p_raw = parts[2].strip().split(' ')[0]
                price = int(p_raw[:-1] if p_raw else 0)
                total_val = int(parts[3].strip() or 0)
                buyer = parts[-1].strip()[:4]

                rows.append({
                    "農會": farm_name, "日期編碼": date_for_obj, "顯示日期": display_date,
                    "流水號": serial, "等級": level, "小代": sub_id,
                    "件數": pieces, "公斤": weight, "單價": price, "總價": total_val, "買家": buyer
                })
            except: continue
    return rows

@st.cache_data(ttl=60)
def fetch_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    REPO = "goodgorilla5/chaochao-catcher"
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/contents/", headers=headers)
        files = [f for f in r.json() if f['name'].lower().endswith('.scp')]
        
        def process_file(file_info):
            res = requests.get(file_info['download_url'], headers=headers)
            return parse_farmer_data(res.content.decode("big5", errors="ignore"))

        with concurrent.futures.ThreadPoolExecutor() as exe:
            results = list(exe.map(process_file, files))
        for res in results: all_rows.extend(res)
        
        df = pd.DataFrame(all_rows)
        if not df.empty:
            df = df.drop_duplicates(subset=["流水號", "小代", "單價"])
            df['date_obj'] = pd.to_datetime(df['日期編碼'].apply(lambda x: str(int(x[:3])+1911)+x[3:]), format='%Y%m%d')
            return df.sort_values("單價", ascending=False)
    except: pass
    return pd.DataFrame()

# --- 主介面 ---
st.title("🍎 農會蜜棗行情大數據庫")
df = fetch_data()

if not df.empty:
    farm = st.selectbox("🏥 選擇農會", options=["燕巢", "大社", "阿蓮"])
    
    # 篩選
    f_df = df[df['農會'] == farm].copy()
    
    # 日期選擇
    dates = sorted(f_df['date_obj'].dt.date.unique(), reverse=True)
    target_date = st.selectbox("📅 選擇日期", options=dates)
    f_df = f_df[f_df['date_obj'].dt.date == target_date]

    st.dataframe(f_df[["顯示日期", "小代", "件數", "公斤", "單價", "買家"]].rename(columns={"顯示日期":"日期"}), 
                 use_container_width=True, hide_index=True)

    # 統計
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總件數", f"{int(f_df['件數'].sum())}")
    c2.metric("總公斤", f"{int(f_df['公斤'].sum())}")
    c3.metric("最高價", f"{f_df['單價'].max()}")
    c4.metric("平均價", f"{f_df['總價'].sum()/f_df['公斤'].sum():.1f}" if f_df['公斤'].sum()>0 else 0)
else:
    st.warning("😭 找不到資料，請確認 GitHub 倉庫內有 SCP 檔案。")