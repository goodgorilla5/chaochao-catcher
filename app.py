import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 頁面設定 ---
st.set_page_config(page_title="農會行情大數據庫", layout="wide")

# 農會對照 (剔除高樹)
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}

try:
    GITHUB_TOKEN = st.secrets["github_token"]
except:
    st.error("❌ 請設定 github_token")
    st.stop()

# --- 核心解析邏輯 (流水號切點法) ---
def deep_parse(content):
    # 1. 強制從流水號開頭 (A或T開頭，後面接111...) 進行切割
    # 這樣保證每一段都是從 A111... 開始，到下一筆 A111 前結束
    records = re.split(r'(?=[AT]\d{10,})', content)
    rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for rec in records:
        if not rec.strip(): continue
        try:
            # 2. 定位日期與市場 (S00)
            # 規律：8碼日期 + 空格 + 2碼等級 + S00
            m = re.search(r'(\d{8})\s+(\d{2})(S00\d{6})', rec)
            if not m: continue
            
            raw_date = m.group(1)
            level_code = m.group(2)[0]
            market_anchor = m.group(3) # S00250516
            
            # 3. 提取流水號：就是這段記錄最開頭到日期之前的部分
            serial = rec[:m.start()].strip().replace(" ", "")

            # 4. 數據段解析 (精確對應 + 號)
            # rec 後半部範例：002+00012+02300+000002760+6000+4304
            data_part = rec[m.end():]
            if '+' not in data_part: continue
            
            parts = data_part.split('+')
            
            # 數值校準
            pieces = int(parts[0][-3:].strip())
            weight = int(parts[1].strip())
            # 單價/總價 (截掉末位 0)
            price = int(parts[2].strip()[:-1]) if parts[2].strip() else 0
            total = int(parts[3].strip()[:-1]) if parts[3].strip() else 0
            
            # 買家：最後一個 + 號後面的純數字 (排除掉後面可能連帶的下一筆雜質)
            buyer_raw = parts[-1].strip()
            buyer = re.search(r'^\d+', buyer_raw).group() if re.search(r'^\d+', buyer_raw) else ""

            # 品種搜尋
            v_match = re.search(r'(F22|FP1|FP2|FP3|FP5|FI3)', parts[0])
            variety = v_match.group(1) if v_match else "F22"

            # 判定農會
            farm = "其他"
            for name, code in FARMER_MAP.items():
                if code in market_anchor: farm = name; break
            if farm == "其他": continue

            rows.append({
                "農會": farm, "日期": f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}",
                "等級": grade_map.get(level_code, level_code), "小代": market_anchor[6:9],
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
            df = df.drop_duplicates(subset=["流水號", "小代", "單價", "買家"])
            return df.sort_values(["raw_date", "單價"], ascending=[False, False])
    except: pass
    return pd.DataFrame()

# --- 主介面 ---
st.title("🍎 農會行情大數據庫")
df = fetch_data()

if not df.empty:
    st.sidebar.header("🎨 顯示設定")
    show_serial = st.sidebar.checkbox("顯示流水號", value=False)
    
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
    st.dataframe(final_df[cols], use_container_width=True, height=450, hide_index=True)

    # 統計區
    st.divider()
    if not final_df.empty:
        t_pcs, t_kg, t_val = final_df['件數'].sum(), final_df['公斤'].sum(), final_df['總價'].sum()
        avg_p = t_val / t_kg if t_kg > 0 else 0
        st.markdown(f"##### 📉 {target_farm} ({target_v}) 數據摘要")
        m_cols = st.columns(6)
        metrics = [("總件數", f"{int(t_pcs)} 件"), ("總公斤", f"{int(t_kg)} kg"),
                   ("最高價", f"{final_df['單價'].max()} 元"), ("最低價", f"{final_df['單價'].min()} 元"),
                   ("平均單價", f"{avg_p:.1f} 元"), ("區間總價", f"{int(t_val):,} 元")]
        for i, (l, v) in enumerate(metrics):
            with m_cols[i]:
                st.markdown(f'<div style="background-color:#f0f2f6;padding:10px;border-radius:5px;text-align:center;">'
                            f'<p style="margin:0;font-size:12px;color:#555;">{l}</p>'
                            f'<p style="margin:0;font-size:16px;font-weight:bold;color:#111;">{v}</p></div>', unsafe_allow_html=True)
else:
    st.warning("😭 倉庫中無有效資料。")