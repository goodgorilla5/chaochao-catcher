import streamlit as st
import pandas as pd
import re
import requests
import time
from datetime import datetime

st.set_page_config(page_title="燕巢台北市場助手", layout="wide")

# --- 核心解析邏輯 (恢復您最信任的日期錨點與空格合併) ---
def process_logic(content):
    # 這裡保留 split('    ') 四個空格的邏輯
    raw_lines = content.split('    ')
    final_rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in raw_lines:
        if "F22" in line and "S00076" in line:
            try:
                # 尋找日期錨點 (如 11502091)
                # 使用您程式中原本的正則表達式，這是最準確的
                date_match = re.search(r"(\d{7,8}1)\s+\d{2}S00076", line)
                if date_match:
                    date_pos = date_match.start()
                    # 合併流水號空格：將日期前方的字串去除多餘空白
                    serial = line[:date_pos].strip().replace(" ", "")
                    
                    remaining = line[date_pos:]
                    s_pos = remaining.find("S00076")
                    level = grade_map.get(remaining[s_pos-2], remaining[s_pos-2])
                    sub_id = remaining[s_pos+6:s_pos+9]
                    
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].replace(" ", "") or 0)
                    weight = int(nums[1].replace(" ", "") or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    # 原本邏輯：取最後一位之前的數字
                    price = int(price_raw[:-1] if price_raw else 0)
                    
                    # 買家欄位 (nums[5])
                    buyer = nums[5].strip()[:4] if len(nums) > 5 else "未知"

                    final_rows.append({
                        "流水號": serial, 
                        "等級": level, 
                        "小代": sub_id, 
                        "件數": pieces, 
                        "公斤": weight, 
                        "單價": price, 
                        "買家": buyer
                    })
            except: 
                continue
                
    # --- 關鍵修正：剔除重複流水號資料 ---
    if final_rows:
        df_temp = pd.DataFrame(final_rows)
        # 只顯示一個相同流水號的資料，保留第一筆
        df_temp = df_temp.drop_duplicates(subset="流水號", keep="first")
        return df_temp.to_dict('records')
    
    return final_rows

st.title("🍎 燕巢-台北行情查詢")

# --- 日期選擇區 ---
picked_date = st.date_input("📅 選擇查詢日期", datetime.now())
roc_year = picked_date.year - 1911
file_name = f"{roc_year}{picked_date.strftime('%m%d')}.SCP"

# --- 倉庫路徑 ---
timestamp = int(time.time())
RAW_URL = f"https://raw.githubusercontent.com/goodgorilla5/chaochao-catcher/main/{file_name}?t={timestamp}"

@st.cache_data(ttl=60)
def fetch_data(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.content.decode("big5", errors="ignore")
    except: return None
    return None

content = fetch_data(RAW_URL)

# --- 顯示與操作區 ---
if content:
    st.success(f"✅ 已載入 {file_name} 行情資料")
    data = process_logic(content)
    if data:
        df = pd.DataFrame(data)
        st.divider()
        
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            search_query = st.text_input("🔍 搜尋小代", placeholder="輸入如 627")
        with c2:
            sort_order = st.selectbox("排序價格", ["-- 選擇排序 --", "價格：由高至低", "價格：由低至高"])
        with c3:
            show_serial = st.checkbox("顯示流水號", value=False)

        if search_query:
            df = df[df['小代'].str.contains(search_query)]
        
        if sort_order == "價格：由高至低":
            df = df.sort_values(by="單價", ascending=False)
        elif sort_order == "價格：由低至高":
            df = df.sort_values(by="單價", ascending=True)

        display_cols = ["等級", "小代", "件數", "公斤", "單價", "買家"]
        if show_serial:
            display_cols.insert(0, "流水號")

        st.dataframe(
            df[display_cols], 
            use_container_width=True, 
            height=600,
            column_config={"單價": st.column_config.NumberColumn("單價", format="%d 元")}
        )
        
        st.metric(f"{file_name} 總件數", f"{df['件數'].sum()} 件")
    else:
        st.info("查無符合 F22 芭樂的行情資料。")
else:
    st.warning(f"😭 找不到 {file_name} 的雲端資料")
    with st.expander("手動上傳備案"):
        manual_file = st.file_uploader("請點此上傳 SCP 檔案", type=['scp', 'txt'])
        if manual_file:
            m_content = manual_file.read().decode("big5", errors="ignore")
            m_data = process_logic(m_content)
            if m_data:
                st.dataframe(pd.DataFrame(m_data), use_container_width=True)