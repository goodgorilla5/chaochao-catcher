# --- 📊 區間行情彙總 (縮小字體版) ---
    if not f_df.empty:
        st.divider()
        t_pcs = int(f_df['件數'].sum())
        t_kg = int(f_df['公斤'].sum())
        t_val = int(f_df['總價'].sum())
        avg_p = t_val / t_kg if t_kg > 0 else 0
        max_p = f_df['單價'].max()
        min_p = f_df['單價'].min()

        st.markdown("### 📈 區間行情彙總")
        
        # 使用 HTML 語法自訂字體大小 (18px 為標籤, 24px 為數字)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**最高價**：<span style='font-size:24px; color:#ff4b4b;'>{max_p}</span> 元", unsafe_allow_html=True)
            st.markdown(f"**最低價**：<span style='font-size:24px; color:#1f77b4;'>{min_p}</span> 元", unsafe_allow_html=True)
        with c2:
            st.markdown(f"**平均單價**：<span style='font-size:24px;'>{avg_p:.1f}</span> 元", unsafe_allow_html=True)
            st.markdown(f"**區間總價**：<span style='font-size:24px;'>{t_val:,}</span> 元", unsafe_allow_html=True)
        with c3:
            st.markdown(f"**總件數**：<span style='font-size:24px;'>{t_pcs}</span> 件", unsafe_allow_html=True)
            st.markdown(f"**總公斤**：<span style='font-size:24px;'>{t_kg}</span> kg", unsafe_allow_html=True)