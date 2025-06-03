import streamlit as st
import sqlite3
import pandas as pd
import random
import os

# --- Sidebar chọn DB ---
st.sidebar.title("⚙️ Cài đặt Database")

# Tìm tất cả file .db trong cùng thư mục
db_files = [f for f in os.listdir() if f.endswith(".db")]
default_db = "quote.db"
if default_db not in db_files:
    db_files.insert(0, default_db)

# Dropdown chọn file .db
selected_db = st.sidebar.selectbox("🗂️ Chọn Database", db_files, index=db_files.index(default_db))

# Hiện DB đang dùng
st.sidebar.markdown(f"**📌 Đang dùng:** `{selected_db}`")

# Kết nối DB được chọn
@st.cache_resource
def get_conn(db_file):
    return sqlite3.connect(db_file, check_same_thread=False)

conn = get_conn(selected_db)
cursor = conn.cursor()

# Tạo bảng nếu chưa tồn tại
cursor.execute('''
    CREATE TABLE IF NOT EXISTS quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT,
        speaker TEXT,
        note TEXT,
        date TEXT,
        tag TEXT
    )
''')
conn.commit()

# Thêm quote mới
def add_quote(content, speaker, note, date, tag):
    cursor.execute('''
        INSERT INTO quotes (content, speaker, note, date, tag)
        VALUES (?, ?, ?, ?, ?)
    ''', (content, speaker, note, date, tag))
    conn.commit()

# Cập nhật quote
def update_quote(quote_id, field, new_value):
    cursor.execute(f'''
        UPDATE quotes SET {field} = ? WHERE id = ?
    ''', (new_value, quote_id))
    conn.commit()

# Lấy toàn bộ quote
def get_all_quotes():
    return pd.read_sql_query("SELECT * FROM quotes", conn)

# Random quote
def get_random_quote():
    df = get_all_quotes()
    if df.empty:
        return None
    return df.sample(1).iloc[0]

# --- Giao diện chính ---
st.title("📚 Quote Database Manager")
# Tab UI
tab4, tab1, tab2, tab3, tab5, tab6 = st.tabs([
    "🎲 Random Quote",
    "➕ Thêm Quote", 
    "📋 Danh sách", 
    "✏️ Sửa Quote", 
    "📤 Chuyển Quote",
    "🗑️ Xóa Quote"
])
with tab4:
    st.subheader("🎲")

    if "random_quote" not in st.session_state:
        st.session_state.random_quote = get_random_quote()

    quote = st.session_state.random_quote

    if quote is None:
        st.info("Chưa có quote nào trong database.")
    else:
        dau = f"({quote['date']})" if quote['date'] else ""
        content_md = quote['content'].replace('\n', '  \n')

        st.markdown(f"""
        <div style='font-size: 22px; line-height: 1.6; font-weight: bold;'>
        {content_md}
        </div>
        <div style='font-size: 18px; margin-top: 10px;'>
        - <i>{quote['speaker']} {quote['note']}</i> {dau}<br><br>
        🏷️ <code>{quote['tag']}</code>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🎲 Quote khác"):
        st.session_state.random_quote = get_random_quote()

with tab1:
    st.subheader("➕ Thêm Quote mới")
    content = st.text_area("Nội dung", height=100)
    speaker = st.text_input("Người nói")
    note = st.text_area("Chú thích")
    date = st.text_input("Date")
    tag = st.text_input("Tag")
    if st.button("Thêm"):
        if content.strip() == "":
            st.warning("Nội dung không được để trống.")
        else:
            add_quote(content, speaker, note, date, tag)
            st.success("Đã thêm quote.")

with tab2:
    st.subheader("📋 Tất cả Quote")
    df = get_all_quotes()

    # Filter
    col1, col2 = st.columns(2)
    with col1:
        tag_filter = st.text_input("Lọc theo Tag")
    with col2:
        speaker_filter = st.text_input("Lọc theo Người nói")

    if tag_filter:
        df = df[df["tag"].str.contains(tag_filter, case=False, na=False)]
    if speaker_filter:
        df = df[df["speaker"].str.contains(speaker_filter, case=False, na=False)]

    st.dataframe(df, use_container_width=True)

with tab3:
    st.subheader("✏️ Cập nhật Quote")
    quote_id = st.number_input("ID của Quote cần sửa", min_value=1, step=1)
    field = st.selectbox("Trường muốn sửa", ["content", "speaker", "note", "date", "tag"])
    new_value = st.text_area("Giá trị mới", height=100)
    if st.button("Cập nhật"):
        update_quote(quote_id, field, new_value)
        st.success("Đã cập nhật.")

with tab5:
    st.subheader("📤 Chuyển Quote sang DB khác")

    df = get_all_quotes()
    if df.empty:
        st.info("Không có quote nào để chuyển.")
    else:
        # Lọc quote để chọn
        quote_ids = st.multiselect(
            "Chọn Quote để chuyển",
            options=df["id"].tolist(),
            format_func=lambda x: f"ID {x} - {df[df['id']==x]['content'].values[0][:50]}..."
        )

        if not quote_ids:
            st.stop()

        # DB đích
        available_dbs = [f for f in os.listdir() if f.endswith(".db") and f != selected_db]
        if not available_dbs:
            st.warning("Không có database đích khác trong thư mục.")
            st.stop()

        target_db = st.selectbox("Chọn DB đích", available_dbs)

        move_mode = st.radio("Chế độ", ["📋 Sao chép", "✂️ Di chuyển"], horizontal=True)

        if st.button("📤 Thực hiện chuyển"):
            target_conn = sqlite3.connect(target_db, check_same_thread=False)
            target_cursor = target_conn.cursor()

            # Tạo bảng nếu chưa có
            target_cursor.execute('''
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT,
                    speaker TEXT,
                    note TEXT,
                    date TEXT,
                    tag TEXT
                )
            ''')

            # Lấy quote và chèn
            for qid in quote_ids:
                row = df[df["id"] == qid].iloc[0]
                target_cursor.execute('''
                    INSERT INTO quotes (content, speaker, note, date, tag)
                    VALUES (?, ?, ?, ?, ?)
                ''', (row["content"], row["speaker"], row["note"], row["date"], row["tag"]))

                if move_mode == "✂️ Di chuyển":
                    cursor.execute("DELETE FROM quotes WHERE id = ?", (qid,))

            target_conn.commit()
            if move_mode == "✂️ Di chuyển":
                conn.commit()
            target_conn.close()

            st.success(f"Đã {'di chuyển' if move_mode == '✂️ Di chuyển' else 'sao chép'} {len(quote_ids)} quote sang `{target_db}`.")

with tab6:
    st.subheader("🗑️ Xóa Quote")

    df = get_all_quotes()
    if df.empty:
        st.info("Không có quote nào để xóa.")
    else:
        quote_ids_to_delete = st.multiselect(
            "Chọn Quote để xóa",
            options=df["id"].tolist(),
            format_func=lambda x: f"ID {x} - {df[df['id']==x]['content'].values[0][:50]}..."
        )

        if quote_ids_to_delete:
            confirm = st.checkbox("Tôi xác nhận muốn xóa những quote đã chọn.")
            if st.button("❌ Xóa"):
                if confirm:
                    cursor.executemany(
                        "DELETE FROM quotes WHERE id = ?",
                        [(qid,) for qid in quote_ids_to_delete]
                    )
                    conn.commit()
                    st.success(f"Đã xóa {len(quote_ids_to_delete)} quote.")
                else:
                    st.warning("Bạn cần xác nhận trước khi xóa.")
