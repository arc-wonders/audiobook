import streamlit as st
from gtts import gTTS
import os

# Load text file
with open("full_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

# --- Parsing logic ---
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
                # put loose text under "Introduction"
                if "Introduction" not in chapters[current_chapter]:
                    chapters[current_chapter]["Introduction"] = []
                chapters[current_chapter]["Introduction"].append(line)
            else:
                chapters[current_chapter][current_section].append(line)

# join text
for ch in chapters:
    for sec in chapters[ch]:
        chapters[ch][sec] = "\n".join(chapters[ch][sec])
# --- Streamlit UI ---
st.title("📖 NCF Audiobook Player")

chapter_choice = st.selectbox("Choose a Chapter:", list(chapters.keys()))

if chapter_choice:
    section_choice = st.selectbox("Choose a Section:", list(chapters[chapter_choice].keys()))

    if section_choice:
        section_text = chapters[chapter_choice][section_choice]
        st.subheader(f"{chapter_choice} - {section_choice}")
        st.write(section_text)

        # TTS Button
        if st.button("▶️ Listen to this Section"):
            tts = gTTS(text=section_text, lang="en")
            audio_file = "temp_audio.mp3"
            tts.save(audio_file)

            audio_bytes = open(audio_file, "rb").read()
            st.audio(audio_bytes, format="audio/mp3")
