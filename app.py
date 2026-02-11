import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 農會定義 (剔除高樹)
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請設定 github_token")
    st.stop()

# --- 核心解析邏輯 ---
def process_logic(content):
    # 這裡不使用空格切分，而是搜尋符合 [日期+等級+S00] 的特徵區塊
    # 特徵：8位數字 + 空格 + 2位數字 + S00
    pattern = re.compile(r'(\d{8})\s+(\d{2})S00')
    matches = list(pattern.finditer(content))
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for i in range(len(matches)):
        try:
            m = matches[i]
            s_pos = m.start()   # 匹配到的起始點 (日期的位置)
            raw_date = m.group(1)
            level_code = m.group(2)[0] # 取得 11, 21, 31 的第一碼
            
            # 1. 提取流水號：從上一筆結束到這一筆日期開始
            prev_end = matches[i-1].end() if i > 0 else 0
            # 往前找上一筆的結束點 (通常是買家代號後)
            serial_segment = content[prev_end : s_pos].strip()
            # 清理流水號中的所有空格
            serial = serial_segment.replace(" ", "").replace("\n", "").replace("\r", "")

            # 2. 提取市場與小代 (從 S00 開始)
            anchor_pos = content.find("S00", s_pos)
            market_code = content[anchor_pos : anchor_pos+6]
            sub_id = content[anchor_pos+6 : anchor_pos+9].strip()
            
            # 3. 判定農會
            belong_to = "其他"
            for name, code in FARMER_MAP.items():
                if code == market_code:
                    belong_to = name
                    break
            if belong_to == "其他": continue

            # 4. 提取數據段 (從小代後找第一個 + 號)
            data_part = content[anchor_pos+9 : anchor_pos+120]
            if '+' not in data_part: continue
            
            nums = data_part.split('+')
            pieces = int(nums[0][-3:].strip())
            weight = int(nums[1].strip())
            # 單價：取前 4 位 (自動修正 03400 -> 340)
            price_raw = nums[2].strip().split()[0]
            price = int(price_raw[:4])
            total_price = int(nums[3].strip().split()[0])
            buyer = nums[-1].strip()[:4]
            
            # 品種判定
            variety = nums[0].strip().split()[-1] if len(nums[0].strip().split()) > 1 else "F22"

            rows.append({
                "農會": belong_to, "日期": f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}",
                "等級": grade_map.get(level_code, level_code), "小代": sub_id,
                "件數": pieces, "公斤": weight, "單價": price, "總價": total_price,
                "買家": buyer, "流水號": serial, "品種": variety, "raw_date": raw_date[:7]
            })
        except: continue
    return rows

@st.cache_data(ttl=60)
def fetch_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get("https://api.github.com/repos/goodgorilla5/chaochao-catcher/contents/", headers=headers)
        files = [f for f in r.json() if f['name'].lower().endswith('.scp')]
        for f_info in files:
            res = requests.get(f_info['download_url'], headers=headers)
            all_rows.extend(process_logic(res.content.decode("big5", errors="ignore")))
        return pd.DataFrame(all_rows)
    except: return pd.DataFrame()

# --- 主介面 ---
st.title("🍎 農會行情大數據庫")
df = fetch_data()

if not df.empty:
    # 側邊欄控制
    st.sidebar.header("🎨 顯示設定")
    show_serial = st.sidebar.checkbox("顯示流水號", value=False)
    
    # 選擇農會
    target_farm = st.selectbox("🏥 選擇農會", list(FARMER_MAP.keys()))
    f_df = df[df['農會'] == target_farm].copy()
    
    # 選擇品種 (預設 F22)
    v_list = sorted(f_df['品種'].unique())
    target_v = st.selectbox("🍐 選擇品種", v_list, index=v_list.index("F22") if "F22" in v_list else 0)
    f_df = f_df[f_df['品種'] == target_v]

    # 日期與搜尋
    dates = sorted(f_df['raw_date'].unique(), reverse=True)
    sel_date = st.selectbox("📅 選擇日期", dates)
    
    c1, c2 = st.columns(2)
    with c1: search_sub = st.text_input("🔍 搜尋小代")
    with c2: search_buy = st.text_input("👤 搜尋買家")

    # 過濾
    final_df = f_df[f_df['raw_date'] == sel_date]
    if search_sub: final_df = final_df[final_df['小代'].str.contains(search_sub)]
    if search_buy: final_df = final_df[final_df['買家'].str.contains(search_buy)]

    # 表格顯示
    disp_cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial: disp_cols.insert(0, "流水號")
    
    st.dataframe(final_df[disp_cols], use_container_width=True, height=400, hide_index=True)

    # --- 統計資訊區 (您喜歡的指標樣式) ---
    st.divider()
    if not final_df.empty:
        t_pcs, t_kg, t_val = final_df['件數'].sum(), final_df['公斤'].sum(), final_df['總價'].sum()
        avg_p = t_val / t_kg if t_kg > 0 else 0
        st.markdown(f"##### 📉 {target_farm} 數據摘要")
        m_cols = st.columns(6)
        metrics = [
            ("總件數", f"{int(t_pcs)} 件"), ("總公斤", f"{int(t_kg)} kg"),
            ("最高價", f"{final_df['單價'].max()} 元"), ("最低價", f"{final_df['單價'].min()} 元"),
            ("平均單價", f"{avg_p:.1f} 元"), ("區間總價", f"{int(t_val):,} 元")
        ]
        for i, (l, v) in enumerate(metrics):
            with m_cols[i]:
                st.markdown(f'<div style="background-color:#f0f2f6;padding:10px;border-radius:5px;text-align:center;">'
                            f'<p style="margin:0;font-size:12px;color:#555;">{l}</p>'
                            f'<p style="margin:0;font-size:16px;font-weight:bold;color:#111;">{v}</p></div>', unsafe_allow_html=True)
else:
    st.warning("😭 讀取失敗，請確認倉庫內有 .SCP 檔案。")