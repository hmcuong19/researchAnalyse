import streamlit as st
import pandas as pd
import requests
from io import BytesIO
import time
from bs4 import BeautifulSoup
import re

# Tiêu đề ứng dụng
st.title("Phân loại Bài Báo Liên Quan Đến AI Từ File Excel")

# Lấy API key từ Streamlit secrets
api_key = st.secrets.get("GROQ_API_KEY", None)
if not api_key:
    st.error("Vui lòng cấu hình GROQ_API_KEY trong .streamlit/secrets.toml")
    st.stop()

# Hàm cào tiêu đề và abstract từ link
def scrape_article_info(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Tìm tiêu đề (thường trong thẻ <title> hoặc <h1>)
            title_tag = soup.find('title') or soup.find('h1')
            title = title_tag.text.strip() if title_tag else "Unknown Title"
            
            # Tìm abstract (thường trong thẻ meta hoặc div với class cụ thể)
            abstract = "No abstract found"
            meta_abstract = soup.find('meta', attrs={'name': re.compile('description|abstract', re.I)})
            if meta_abstract and meta_abstract.get('content'):
                abstract = meta_abstract.get('content').strip()
            else:
                # Tìm trong div hoặc p có chứa từ khóa "abstract"
                for tag in soup.find_all(['div', 'p']):
                    if 'abstract' in tag.text.lower():
                        abstract = tag.text.strip()
                        break
            
            return title, abstract
        else:
            return None, None
    except Exception as e:
        return None, None

# Textbox cho phép chỉnh sửa prompt mặc định
default_prompt = """
Dựa trên thông tin sau:
Tiêu đề: {title}
Abstract: {abstract}
Phân loại nếu bài báo liên quan tới AI (học máy, học sâu, trí tuệ nhân tạo, v.v.). Nếu liên quan, trả về dạng markdown theo cấu trúc:
| Tên đề tài | Năm | Tên tạp chí | Phân loại rank tạp chí Q1, Q2, Q3, Q4 |
Nếu không liên quan hoặc không có rank, bỏ qua (không trả về gì).
Chỉ trả về bảng markdown, không thêm text khác.
"""
prompt = st.text_area("Chỉnh sửa prompt mặc định:", value=default_prompt, height=200)

# Upload file Excel
uploaded_file = st.file_uploader("Upload file Excel", type=['xls', 'xlsx'])

if uploaded_file:
    try:
        # Đọc file Excel mà không có header
        df = pd.read_excel(uploaded_file, header=None)
        # Lấy cột A (index 0), từ hàng 5 (index 4) đến hàng 3008 (index 3007)
        links_series = df.iloc[4:3008, 0]
        # Lọc bỏ hàng trống và link không hợp lệ
        links = [link for link in links_series if isinstance(link, str) and link.strip() != '']
        
        st.write(f"Tìm thấy {len(links)} link hợp lệ.")

        # Ô nhập số lượng link muốn xử lý
        max_links = len(links)
        num_links = st.number_input(
            "Số lượng link muốn xử lý (tối đa {}):".format(max_links),
            min_value=1,
            max_value=max_links,
            value=max_links,
            step=1
        )

        # Nút Start để bắt đầu phân tích
        if st.button("Start"):
            results = []
            error_links = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            # Giới hạn số lượng link theo input
            links_to_process = links[:min(num_links, max_links)]

            for i, url in enumerate(links_to_process):
                try:
                    # Cào tiêu đề và abstract
                    title, abstract = scrape_article_info(url)
                    if not title or not abstract:
                        error_links.append((url, "Không thể cào được tiêu đề hoặc abstract"))
                        continue

                    # Tạo prompt với tiêu đề và abstract
                    prompt_with_data = prompt.format(title=title, abstract=abstract)
                    
                    # Gọi Groq API
                    response = requests.post(
                        "https://api.groq.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "llama-3.1-70b-versatile",
                            "messages": [{"role": "user", "content": prompt_with_data}],
                            "temperature": 0.5,
                            "max_tokens": 512
                        }
                    )
                    
                    if response.status_code == 200:
                        content = response.json()['choices'][0]['message']['content']
                        # Kiểm tra nếu content là bảng markdown hợp lệ
                        if content.strip().startswith('|') and '|' in content:
                            lines = content.strip().split('\n')
                            if len(lines) >= 3:  # Header, separator, data
                                data = lines[2].strip('| ').split(' | ')
                                if len(data) == 4:
                                    results.append({
                                        "Tên đề tài": data[0].strip(),
                                        "Năm": data[1].strip(),
                                        "Tên tạp chí": data[2].strip(),
                                        "Phân loại rank tạp chí": data[3].strip()
                                    })
                    else:
                        error_links.append((url, f"API error: {response.status_code}"))

                    # Cập nhật tiến trình
                    progress = (i + 1) / len(links_to_process)
                    progress_bar.progress(progress)
                    status_text.text(f"Đang xử lý {i+1}/{len(links_to_process)} links...")
                    time.sleep(0.5)  # Tránh vượt quá giới hạn rate limit

                except Exception as e:
                    error_links.append((url, str(e)))

            if results:
                # Hiển thị kết quả
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
                    file_name="ket_qua_phan_loai_AI.csv",
                    mime="text/csv"
                )
            else:
                st.info("Không tìm thấy bài báo nào liên quan đến AI có rank tạp chí.")

            if error_links:
                st.write("Danh sách link lỗi:")
                error_df = pd.DataFrame(error_links, columns=["Link", "Lỗi"])
                st.dataframe(error_df)

    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {str(e)}")
else:
    st.info("Vui lòng upload file Excel để bắt đầu.")
