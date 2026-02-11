import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

st.set_page_config(page_title="農會行情終極版", layout="wide")

# 農會定義
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098", "高樹": "T00493"}

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請設定 github_token")
    st.stop()

def deep_parse(content):
    rows = []
    # 雷達掃描規律：[8碼日期][任意空白][2碼等級][S00或T00][市場+小代 6碼]
    # 例如：11502111  11S00250
    pattern = re.compile(r'(\d{8})\s+(\d{2})([S|T]00\d{6})')
    
    # 找出所有符合規律的起點
    matches = list(pattern.finditer(content))
    
    for i in range(len(matches)):
        try:
            m = matches[i]
            raw_date = m.group(1)   # 11502111
            level_code = m.group(2) # 11, 21, 31
            anchor = m.group(3)     # S00250516
            
            # 1. 定位與流水號
            start_pos = m.start()
            # 流水號是這筆資料起點到前一筆資料終點之間的東西
            prev_end = matches[i-1].end() if i > 0 else 0
            # 往前找，如果中間有 '+' 號，代表那是上一筆的數據，要避開
            last_plus = content.rfind('+', prev_end, start_pos)
            search_from = last_plus + 30 if last_plus != -1 else prev_end
            serial = content[search_from:start_pos].strip().replace(" ", "")

            # 2. 數據段：從錨點後找第一個 '+' 開始
            data_area = content[m.end():m.end()+150]
            if '+' not in data_area: continue
            
            # 品種 (錨點後到第一個 + 號)
            variety = data_area.split('+')[0].strip()[:3]
            if variety not in ["F22", "FP1", "FP2", "FP3", "FP5", "FI3"]: continue

            # 數值
            parts = data_area.split('+')
            pieces = int(parts[0][-3:].strip())
            weight = int(parts[1].strip())
            price = int(parts[2].strip()[:4]) # 取前4碼並轉整數 (自動去掉最後的0)
            total = int(parts[3].strip().split()[0])
            buyer = parts[-1].strip()[:4]

            # 3. 判定農會
            farm = "其他"
            for name, code in FARMER_MAP.items():
                if code in anchor:
                    farm = name
                    break

            rows.append({
                "農會": farm, "日期": f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}",
                "等級": {"1":"特","2":"優","3":"良"}.get(level_code[0], level_code),
                "小代": anchor[6:9], "品種": variety, "件數": pieces,
                "公斤": weight, "單價": price, "總價": total, "買家": buyer,
                "流水號": serial, "raw_date": raw_date[:7]
            })
        except: continue
    return rows

@st.cache_data(ttl=60)
def fetch_github_data():
    all_rows = []
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get("https://api.github.com/repos/goodgorilla5/chaochao-catcher/contents/", headers=headers)
        for f in r.json():
            if f['name'].lower().endswith('.scp'):
                res = requests.get(f['download_url'], headers=headers)
                all_rows.extend(deep_parse(res.content.decode("big5", errors="ignore")))
        return pd.DataFrame(all_rows)
    except: return pd.DataFrame()

# --- 主介面 ---
st.title("🍎 農會行情大數據庫 (全自動校準版)")
df = fetch_github_data()

if not df.empty:
    farm_list = ["燕巢", "大社", "阿蓮", "高樹"]
    target_farm = st.selectbox("🏥 選擇農會", farm_list)
    
    # 篩選品種 (預設 F22 蜜棗)
    f_df = df[df['農會'] == target_farm].copy()
    v_list = sorted(f_df['品種'].unique())
    target_v = st.selectbox("🍐 選擇品種", v_list, index=v_list.index("F22") if "F22" in v_list else 0)
    
    f_df = f_df[f_df['品種'] == target_v]
    
    # 日期與搜尋
    dates = sorted(f_df['raw_date'].unique(), reverse=True)
    sel_date = st.selectbox("📅 日期", dates)
    search = st.text_input("🔍 搜尋小代/買家")
    
    final_df = f_df[f_df['raw_date'] == sel_date]
    if search:
        final_df = final_df[final_df['小代'].str.contains(search) | final_df['買家'].str.contains(search)]

    st.dataframe(final_df[["日期", "等級", "小代", "件數", "公斤", "單價", "買家", "流水號"]], use_container_width=True, hide_index=True)
    
    # 統計摘要
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("總公斤", f"{int(final_df['公斤'].sum())} kg")
    c2.metric("最高單價", f"{final_df['單價'].max()} 元")
    c3.metric("總金額", f"{int(final_df['總價'].sum()):,} 元")
else:
    st.warning("😭 倉庫中無有效資料或解析失敗。")