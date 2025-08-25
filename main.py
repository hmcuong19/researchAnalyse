import streamlit as st
import pandas as pd
import requests
from io import BytesIO
import json
import time

# Giả định bạn có API key cho Grok API từ xAI. Tham khảo https://console.grok.x.ai để lấy API key.
# Code này sử dụng requests để gọi API chat completions của Grok.

st.title("Phân loại Bài Báo Liên Quan Đến AI Từ File Excel")

api_key = st.text_input("Nhập Grok API Key của bạn:", type="password")

uploaded_file = st.file_uploader("Upload file Excel", type=['xls', 'xlsx'])

if uploaded_file and api_key:
    try:
        df = pd.read_excel(uploaded_file, header=None)  # Đọc mà không có header
        # Lấy từ hàng 5 (index 4) đến hàng 3008 (index 3007), cột A (index 0)
        links_series = df.iloc[4:3008, 0]
        # Bỏ qua hàng trống hoặc không phải string (link không hợp lệ)
        links = [link for link in links_series if isinstance(link, str) and link.strip() != '']
        
        st.write(f"Tìm thấy {len(links)} link hợp lệ.")
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Prompt mặc định dựa trên yêu cầu trước
        default_prompt = """
        Từ link bài báo sau: {url}
        Tìm hiểu thông tin từ tiêu đề và abstract, phân loại nếu bài báo liên quan tới AI (học máy, học sâu, trí tuệ nhân tạo, v.v.).
        Nếu liên quan, trả về dạng markdown theo cấu trúc: 
        | Tên đề tài | Năm | Tên tạp chí | Phân loại rank tạp chí Q1, Q2, Q3, Q4 |
        Nếu không liên quan hoặc không có rank, bỏ qua (không trả về gì).
        Chỉ trả về bảng markdown, không thêm text khác.
        """
        
        for i, url in enumerate(links):
            try:
                # Gọi API Grok để xử lý từng link
                prompt = default_prompt.format(url=url)
                
                response = requests.post(
                    "https://api.grok.x.ai/v1/chat/completions",  # Giả định endpoint, kiểm tra docs chính thức
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "grok-beta",  # Hoặc model phù hợp
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.5,
                        "max_tokens": 512
                    }
                )
                
                if response.status_code == 200:
                    content = response.json()['choices'][0]['message']['content']
                    # Giả định content là bảng markdown, parse nó
                    if content.strip().startswith('|') and 'AI' in content:  # Kiểm tra nếu có kết quả
                        # Parse markdown table to dict
                        lines = content.strip().split('\n')
                        if len(lines) >= 3:  # Header, separator, data
                            data = lines[2].strip('| ').split(' | ')
                            if len(data) == 4:
                                results.append({
                                    "Tên đề tài": data[0],
                                    "Năm": data[1],
                                    "Tên tạp chí": data[2],
                                    "Phân loại rank tạp chí": data[3]
                                })
                else:
                    st.warning(f"Lỗi gọi API cho link {url}: {response.status_code}")
                
                # Cập nhật progress
                progress = (i + 1) / len(links)
                progress_bar.progress(progress)
                status_text.text(f"Đang xử lý {i+1}/{len(links)} links...")
                time.sleep(1)  # Để tránh rate limit, điều chỉnh nếu cần
                
            except Exception as e:
                st.warning(f"Lỗi xử lý link {url}: {str(e)}")
        
        if results:
            result_df = pd.DataFrame(results)
            st.write("Kết quả:")
            st.dataframe(result_df)
            
            # Chuẩn bị file CSV để download
            output = BytesIO()
            result_df.to_csv(output, index=False, encoding='utf-8-sig')
            output.seek(0)
            
            st.download_button(
                label="Download CSV",
                data=output,
                file_name="ket_qua_phân_loai_AI.csv",
                mime="text/csv"
            )
        else:
            st.info("Không tìm thấy bài báo nào liên quan đến AI có rank tạp chí.")
    
    except Exception as e:
        st.error(f"Lỗi đọc file: {str(e)}")
