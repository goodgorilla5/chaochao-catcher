import streamlit as st
import pandas as pd
import requests

st.title("🛠️ 系統除錯中")

# 測試 1：檢查 Secrets
if "github_token" not in st.secrets:
    st.error("❌ 錯誤：Streamlit Secrets 裡面找不到 github_token！請去後台設定。")
else:
    st.success("✅ Secrets 讀取成功！")
    
    # 測試 2：檢查 Token 是否有效
    headers = {"Authorization": f"token {st.secrets['github_token']}"}
    test_res = requests.get("https://api.github.com/user", headers=headers)
    if test_res.status_code == 200:
        st.success("✅ GitHub Token 有效，且連線正常！")
        st.info("如果還是黑畫面，請嘗試重新整理或清理瀏覽器快取。")
    else:
        st.error(f"❌ Token 無效或已被 GitHub 封鎖 (錯誤碼: {test_res.status_code})")
        st.write("請去 GitHub 重新產生一個 Token 並更新到 Secrets。")