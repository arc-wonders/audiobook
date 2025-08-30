import streamlit as st
from gtts import gTTS
import os, io, threading, time, requests

# -------------------------
# Keep Alive (for Render free tier)
# -------------------------
def keep_alive():
    def run():
        url = os.environ.get("RENDER_EXTERNAL_URL")
        if not url:
            return
        while True:
            try:
                requests.get(url, timeout=10)
                print("Keep-alive ping sent ✅")
            except Exception as e:
                print("Keep-alive ping failed:", e)
            time.sleep(600)  # ping every 10 minutes
    thread = threading.Thread(target=run, daemon=True)
    thread.start()

keep_alive()

# -------------------------
# Load Full Text
# -------------------------
with open("full_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

# -------------------------
# Parsing into Chapters & Sections
# -------------------------
chapters = {}
current_chapter = None
current_section = None

for line in text.splitlines():
    line = line.strip()
    if line.startswith("# Chapter"):  # Chapter heading
        current_chapter = line.replace("# ", "").strip()
        chapters[current_chapter] = {}
        current_section = None
    elif line.startswith("# Section") or line.startswith("##"):  # Subsection heading
        if current_chapter:
            current_section = line.replace("#", "").strip()
            chapters[current_chapter][current_section] = []
    elif line:  # Normal content
        if current_chapter:
            if current_section is None:
                # Put loose text under "Introduction"
                if "Introduction" not in chapters[current_chapter]:
                    chapters[current_chapter]["Introduction"] = []
                chapters[current_chapter]["Introduction"].append(line)
            else:
                chapters[current_chapter][current_section].append(line)

# Join collected lines
for ch in chapters:
    for sec in chapters[ch]:
        chapters[ch][sec] = "\n".join(chapters[ch][sec])

# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title="NCF Audiobook", layout="wide")
st.title("📖 NCF Audiobook Player")

chapter_choice = st.selectbox("📂 Choose a Chapter:", list(chapters.keys()))

if chapter_choice:
    section_choice = st.selectbox("📑 Choose a Section:", list(chapters[chapter_choice].keys()))

    if section_choice:
        section_text = chapters[chapter_choice][section_choice]

        st.subheader(f"{chapter_choice} - {section_choice}")
        st.write(section_text)

        # -------------------------
        # TTS Button
        # -------------------------
        if st.button("▶️ Listen to this Section"):
            tts = gTTS(text=section_text, lang="en")
            audio_bytes = io.BytesIO()
            tts.write_to_fp(audio_bytes)
            audio_bytes.seek(0)

            st.audio(audio_bytes, format="audio/mp3")
