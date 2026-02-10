def process_logic(content):
    raw_lines = content.split('    ')
    final_rows = []
    grade_map = {"1": "特", "2": "優", "3": "良"}
    
    for line in raw_lines:
        if "F22" in line and "S00076" in line:
            try:
                # 1. 找到 S00076 的位置作為基準點
                s_pos = line.find("S00076")
                
                # 2. 往回找日期：通常日期會出現在 S00076 前面一點點
                # 我們用正則表達式抓取 7 位數字 (民國日期)
                date_match = re.search(r"(\d{7})", line[max(0, s_pos-20):s_pos])
                if date_match:
                    real_date_str = date_match.group(1) # 抓到 1150210
                    formatted_date = f"{real_date_str[:3]}/{real_date_str[3:5]}/{real_date_str[5:7]}"
                    
                    # 3. 抓取整段流水號 (從頭到日期結束)
                    # 依照你提供的範例，流水號非常長，我們抓前 30 碼作為唯一 ID
                    serial = line[:line.find(real_date_str)+15].strip().replace(" ", "")

                    # 4. 抓取其餘欄位
                    level = grade_map.get(line[s_pos-2], line[s_pos-2])
                    sub_id = line[s_pos+6:s_pos+9]
                    
                    nums = line.split('+')
                    pieces = int(nums[0][-3:].strip() or 0)
                    weight = int(nums[1].strip() or 0)
                    price_raw = nums[2].strip().split(' ')[0]
                    price = int(price_raw[:-1] if price_raw else 0)
                    buyer = nums[5].strip()[:4]

                    final_rows.append({
                        "流水號": serial, 
                        "日期": formatted_date, 
                        "等級": level, 
                        "小代": sub_id, 
                        "件數": pieces, 
                        "公斤": weight, 
                        "單價": price, 
                        "買家": buyer
                    })
            except: continue
    return final_rows