import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 農會定義 (只保留燕巢、大社、阿蓮)
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請至 Streamlit 後台 Secrets 設定 github_token")
    st.stop()

def deep_parse(content):
    # 核心雷達：尋找 [8碼日期][空格][2碼等級]S00[市場+小代]
    pattern = re.compile(r'(\d{8})\s+(\d{2})(S00\d{6})')
    matches = list(pattern.finditer(content))
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for i in range(len(matches)):
        try:
            m = matches[i]
            s_pos = m.start()   # 日期起點
            raw_date = m.group(1)
            level_code = m.group(2)[0] # 1, 2, 3
            anchor = m.group(3)        # S00250516
            
            # 1. 提取流水號 (處理大社超長空白)
            prev_end = matches[i-1].end() if i > 0 else 0
            # 往前找，避開上一筆的數據段 (+號區)
            last_plus = content.rfind('+', prev_end, s_pos)
            search_from = last_plus + 35 if last_plus != -1 else prev_end
            serial = content[search_from:s_pos].strip().replace(" ", "").replace("\n", "").replace("\r", "")

            # 2. 數據段解析 (從錨點後尋找 + 號串)
            # 範例數據：S00250516 F22  003+00060+00220+000001320+ 000+8156
            data_area = content[m.end() : m.end() + 150]
            if '+' not in data_area: continue
            
            parts = data_area.split('+')
            
            # 品種：在第一個 + 前面搜尋有效品種代號
            variety_search = re.search(r'(F22|FP1|FP2|FP3|FP5|FI3)', parts[0])
            variety = variety_search.group(1) if variety_search else "F22"
            
            # 數值精確校準
            pieces = int(parts[0][-3:].strip()) # 第一個 + 前 3 碼
            weight = int(parts[1].strip())     # 第一個與第二個 + 之間
            
            # 單價修正 (00220 -> 220)
            p_raw = parts[2].strip().split()[0]
            price = int(p_raw[:-1]) if p_raw else 0
            
            # 總價修正 (0000013200 -> 13200)
            t_raw = parts[3].strip().split()[0]
            total = int(t_raw[:-1]) if t_raw else 0
            
            # 買家：最後一段
            buyer = parts[-1].strip()[:4]

            # 3. 判定農會
            farm = "其他"
            for name, code in FARMER_MAP.items():
                if code in anchor:
                    farm = name
                    break
            if farm == "其他": continue

            rows.append({
                "農會": farm, "日期": f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}",
                "等級": grade_map.get(level_code, level_code), "小代": anchor[6:9],
                "件數": pieces, "公斤": weight, "單價": price, "總價": total,
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
            all_rows.extend(deep_parse(res.content.decode("big5", errors="ignore")))
        df = pd.DataFrame(all_rows)
        if not df.empty:
            df = df.drop_duplicates(subset=["流水號", "小代", "單價"])
            return df.sort_values(["raw_date", "單價"], ascending=[False, False])
    except: pass
    return pd.DataFrame()

# --- 主介面 ---
st.title("🍎 農會行情大數據庫")
df = fetch_data()

if not df.empty:
    st.sidebar.header("🎨 顯示設定")
    show_serial = st.sidebar.checkbox("顯示流水號", value=False)
    show_total = st.sidebar.checkbox("顯示總價", value=False)

    target_farm = st.selectbox("🏥 選擇農會", list(FARMER_MAP.keys()))
    f_df = df[df['農會'] == target_farm].copy()
    
    v_list = sorted(f_df['品種'].unique())
    target_v = st.selectbox("🍐 選擇品種", v_list, index=v_list.index("F22") if "F22" in v_list else 0)
    f_df = f_df[f_df['品種'] == target_v]

    dates = sorted(f_df['raw_date'].unique(), reverse=True)
    sel_date = st.selectbox("📅 選擇日期", dates)
    
    sc1, sc2 = st.columns(2)
    with sc1: s_sub = st.text_input("🔍 搜尋小代")
    with sc2: s_buy = st.text_input("👤 搜尋買家")

    final_df = f_df[f_df['raw_date'] == sel_date]
    if s_sub: final_df = final_df[final_df['小代'].str.contains(s_sub)]
    if s_buy: final_df = final_df[final_df['買家'].str.contains(s_buy)]

    cols = ["日期", "等級", "小代", "件數", "公斤", "單價", "買家"]
    if show_serial: cols.insert(0, "流水號")
    if show_total: cols.insert(cols.index("單價")+1, "總價")
    
    st.dataframe(final_df[cols], use_container_width=True, height=450, hide_index=True)

    # --- 統計資訊區 (回歸您最喜歡的卡片樣式) ---
    st.divider()
    if not final_df.empty:
        t_pcs, t_kg, t_val = final_df['件數'].sum(), final_df['公斤'].sum(), final_df['總價'].sum()
        avg_p = t_val / t_kg if t_kg > 0 else 0
        st.markdown(f"##### 📉 {target_farm} - {target_v} 數據摘要")
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
    st.warning("😭 倉庫中無有效資料。")