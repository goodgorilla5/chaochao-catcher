import streamlit as st
import pandas as pd
import re
import requests
import concurrent.futures

# --- 定規配置 ---
FARMER_MAP = {"燕巢": "S00076", "大社": "S00250", "阿蓮": "S00098"}

def parse_scp_content(content):
    rows = []
    # 核心邏輯：尋找 [8碼日期][2碼等級]S00[3碼市場][3碼小代]
    # 例如：11502111  21S00250516
    # 我們鎖定 S00XXXXXX 作為掃描錨點
    
    # 1. 找出所有 S00 的位置
    matches = re.finditer(r'S00\d{6}', content)
    
    for m in matches:
        s_pos = m.start() # S00 開始的位置
        
        try:
            # 向前推 10 碼取得日期與等級
            anchor_start = s_pos - 10
            anchor_block = content[anchor_start : s_pos] # 例如 "11502111  21"
            
            # 提取日期 (前 8 碼)
            raw_date = anchor_block[:8].strip()
            if not raw_date.isdigit(): continue
            
            # 提取等級 (最後 2 碼的前一位)
            level_code = anchor_block[-2] # 取得 1, 2 或 3
            grade_map = {"1": "特", "2": "優", "3": "良"}
            level = grade_map.get(level_code, level_code)

            # 向後提取數據區 (從 S00 之後開始找第一個 + 號)
            data_segment = content[s_pos : s_pos + 100] # 抓一段足夠長的字串
            if "+" not in data_segment: continue
            
            # 取得品種 (S00 之後到第一個 + 號之間的部分)
            # 結構: S00250516 F22  002+...
            parts = data_segment.split('+')
            
            # 品種與小代
            header = parts[0] # "S00250516 F22  002"
            sub_id = header[6:9].strip()
            
            # 數據提取
            pieces = int(header[-3:].strip())
            weight = int(parts[1].strip())
            # 單價處理 (去掉最後一位 0)
            price_raw = parts[2].strip().split(' ')[0]
            price = int(price_raw[:-1]) if price_raw else 0
            total_val = int(parts[3].strip().split(' ')[0])
            
            # 判定農會
            farm_name = "其他"
            for name, code in FARMER_MAP.items():
                if code in header:
                    farm_name = name
                    break

            rows.append({
                "農會": farm_name,
                "日期": f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}",
                "等級": level,
                "小代": sub_id,
                "件數": pieces,
                "公斤": weight,
                "單價": price,
                "總價": total_val,
                "raw_date": raw_date[:7]
            })
        except:
            continue
    return rows

# --- Streamlit 整合部分 (其餘 Fetch 邏輯保持不變) ---
# ... (Fetch 邏輯與之前相同，僅更換 parse 函數) ...