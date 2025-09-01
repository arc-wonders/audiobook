import streamlit as st
import os
import re
import json
import asyncio
import threading
import requests
import tempfile
import time 
import base64
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import hashlib

# TTS Libraries
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

# Configure Streamlit page
st.set_page_config(
    page_title="Free TTS Audiobook Reader - NCF 2023",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

class HealthCheck:
    """Health check system to keep Render service alive"""
    
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:8501')
        
    def start_health_check(self):
        """Start the health check thread"""
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._health_check_loop, daemon=True)
            self.thread.start()
    
    def stop_health_check(self):
        """Stop the health check thread"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1)
    
    def _health_check_loop(self):
        """Health check loop that pings every 8 minutes"""
        while self.is_running:
            try:
                time.sleep(480)  # 8 minutes
                if self.app_url and 'localhost' not in self.app_url:
                    response = requests.get(f"{self.app_url}/health", timeout=30)
                    if response.status_code == 200:
                        st.session_state['last_health_check'] = time.time()
            except Exception as e:
                # Silent fail - don't spam logs
                pass

# Global health check instance
health_checker = HealthCheck()

class AudiobookParser:
    """Parser for the NCF 2023 audiobook text file"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.content = {}
        self.metadata = {}
    
    def clean_text_for_speech(self, text: str) -> str:
        """Clean text for better TTS pronunciation"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Fix common abbreviations for speech
        replacements = {
            'NCF': 'National Curriculum Framework',
            'NEP': 'National Education Policy',
            'NCERT': 'National Council of Educational Research and Training',
            'ECCE': 'Early Childhood Care and Education',
            'TLM': 'Teaching Learning Material',
            'NSQF': 'National Skills and Qualifications Framework',
            'TWAU': 'The World Around Us',
            'R1': 'First Language',
            'R2': 'Second Language',
            'R3': 'Third Language',
        }
        
        for abbr, full_form in replacements.items():
            text = re.sub(r'\b' + abbr + r'\b', full_form, text)
        
        # Remove markdown formatting
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        
        # Fix numbered lists for speech
        text = re.sub(r'(\d+)\.\s+', r'Point \1: ', text)
        text = re.sub(r'([a-z])\)\s+', r'Item \1: ', text)
        
        return text.strip()
    
    def parse_text_file(self) -> Dict[str, str]:
        """Parse the text file matching the NCF format with single # headers"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            section_pattern = r'^# (.+)$'
            lines = content.split('\n')
            
            parsed_content = {}
            current_section = None
            section_text = []
            
            for line in lines:
                line_stripped = line.strip()
                
                section_match = re.match(section_pattern, line_stripped)
                if section_match:
                    if current_section and section_text:
                        content_text = '\n'.join(section_text).strip()
                        if content_text:
                            parsed_content[current_section] = content_text
                    
                    current_section = section_match.group(1).strip()
                    section_text = []
                    continue
                
                if current_section:
                    if line_stripped or section_text:
                        section_text.append(line)
            
            if current_section and section_text:
                content_text = '\n'.join(section_text).strip()
                if content_text:
                    parsed_content[current_section] = content_text
            
            self.metadata = {
                'total_sections': len(parsed_content),
                'sections': list(parsed_content.keys()),
                'word_counts': {section: len(content.split()) for section, content in parsed_content.items()}
            }
            
            self.content = parsed_content
            return parsed_content
        
        except FileNotFoundError:
            st.error(f"File not found: {self.file_path}")
            return {}
        except Exception as e:
            st.error(f"Error parsing file: {str(e)}")
            return {}

class FreeTTSClient:
    """Client for free TTS services"""
    
    def __init__(self):
        self.cache_dir = Path("audio_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        # Initialize pyttsx3 engine if available
        if PYTTSX3_AVAILABLE:
            try:
                self.pyttsx3_engine = pyttsx3.init()
                self.setup_pyttsx3_engine()
            except Exception as e:
                st.warning(f"pyttsx3 initialization failed: {e}")
                self.pyttsx3_engine = None
        else:
            self.pyttsx3_engine = None
    
    def setup_pyttsx3_engine(self):
        """Configure pyttsx3 engine settings"""
        if self.pyttsx3_engine:
            try:
                # Set speech rate
                self.pyttsx3_engine.setProperty('rate', 180)
                # Set volume
                self.pyttsx3_engine.setProperty('volume', 0.9)
            except Exception as e:
                st.warning(f"pyttsx3 setup failed: {e}")
    
    def get_cache_key(self, text: str, tts_type: str, voice: str = "") -> str:
        """Generate cache key"""
        content = f"{text}_{tts_type}_{voice}".encode('utf-8')
        return hashlib.md5(content).hexdigest()
    
    def get_cached_audio(self, cache_key: str) -> Optional[bytes]:
        """Get cached audio"""
        try:
            cache_file = self.cache_dir / f"{cache_key}.mp3"
            if cache_file.exists():
                return cache_file.read_bytes()
        except Exception as e:
            st.warning(f"Cache read error: {e}")
        return None
    
    def cache_audio(self, cache_key: str, audio_data: bytes):
        """Cache audio data"""
        try:
            cache_file = self.cache_dir / f"{cache_key}.mp3"
            cache_file.write_bytes(audio_data)
        except Exception as e:
            st.warning(f"Failed to cache audio: {str(e)}")
    
    def generate_gtts_audio(self, text: str, lang: str = 'en') -> Optional[bytes]:
        """Generate audio using gTTS"""
        if not GTTS_AVAILABLE:
            return None
        
        try:
            # Limit text length for gTTS
            if len(text) > 5000:
                text = text[:5000] + "..."
            
            tts = gTTS(text=text, lang=lang, slow=False)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tts.save(tmp_file.name)
                tmp_file.seek(0)
                audio_data = open(tmp_file.name, 'rb').read()
                
            # Clean up temp file
            os.unlink(tmp_file.name)
            return audio_data
            
        except Exception as e:
            st.error(f"gTTS error: {str(e)}")
            return None
    
    def generate_pyttsx3_audio(self, text: str) -> Optional[bytes]:
        """Generate audio using pyttsx3"""
        if not self.pyttsx3_engine:
            return None
        
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                self.pyttsx3_engine.save_to_file(text, tmp_file.name)
                self.pyttsx3_engine.runAndWait()
                
                # Convert to bytes
                with open(tmp_file.name, 'rb') as f:
                    audio_data = f.read()
                
            os.unlink(tmp_file.name)
            return audio_data
            
        except Exception as e:
            st.error(f"pyttsx3 error: {str(e)}")
            return None
    
    async def generate_edge_tts_audio(self, text: str, voice: str = "en-IN-NeerjaNeural") -> Optional[bytes]:
        """Generate audio using edge-tts"""
        if not EDGE_TTS_AVAILABLE:
            return None
        
        try:
            # Limit text length
            if len(text) > 5000:
                text = text[:5000] + "..."
                
            communicate = edge_tts.Communicate(text, voice)
            audio_data = b""
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            return audio_data
            
        except Exception as e:
            st.error(f"Edge TTS error: {str(e)}")
            return None
    
    def generate_tts(self, text: str, tts_type: str = "gtts", voice: str = "", use_cache: bool = True) -> Optional[bytes]:
        """Generate TTS audio with specified service"""
        # Check cache
        if use_cache:
            cache_key = self.get_cache_key(text, tts_type, voice)
            cached_audio = self.get_cached_audio(cache_key)
            if cached_audio:
                return cached_audio
        
        audio_data = None
        
        if tts_type == "gtts" and GTTS_AVAILABLE:
            audio_data = self.generate_gtts_audio(text)
        elif tts_type == "pyttsx3" and PYTTSX3_AVAILABLE:
            audio_data = self.generate_pyttsx3_audio(text)
        elif tts_type == "edge" and EDGE_TTS_AVAILABLE:
            # Run async function
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audio_data = loop.run_until_complete(self.generate_edge_tts_audio(text, voice))
            except Exception as e:
                st.error(f"Async error: {e}")
            finally:
                try:
                    loop.close()
                except:
                    pass
        
        if audio_data and use_cache:
            cache_key = self.get_cache_key(text, tts_type, voice)
            self.cache_audio(cache_key, audio_data)
        
        return audio_data

def get_available_tts_options() -> Dict[str, Dict]:
    """Get available TTS options with their capabilities"""
    options = {}
    
    if GTTS_AVAILABLE:
        options["gtts"] = {
            "name": "Google TTS (gTTS)",
            "description": "Free Google TTS, requires internet",
            "voices": ["English (en)", "Hindi (hi)"],
            "quality": "Good",
            "speed": "Medium"
        }
    
    if PYTTSX3_AVAILABLE:
        options["pyttsx3"] = {
            "name": "System TTS (pyttsx3)",
            "description": "Uses system TTS, works offline",
            "voices": ["System Default"],
            "quality": "Variable",
            "speed": "Fast"
        }
    
    if EDGE_TTS_AVAILABLE:
        options["edge"] = {
            "name": "Microsoft Edge TTS",
            "description": "High-quality neural voices, free",
            "voices": [
                "en-IN-NeerjaNeural (Indian Female)",
                "en-IN-PrabhatNeural (Indian Male)",
                "en-US-AriaNeural (US Female)",
                "en-US-GuyNeural (US Male)"
            ],
            "quality": "Excellent",
            "speed": "Medium"
        }
    
    return options

def display_tts_status():
    """Display TTS library installation status"""
    with st.expander("📋 TTS Library Status"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if GTTS_AVAILABLE:
                st.success("✅ gTTS Available")
            else:
                st.error("❌ gTTS Not Installed")
                st.code("pip install gtts")
        
        with col2:
            if PYTTSX3_AVAILABLE:
                st.success("✅ pyttsx3 Available")
            else:
                st.error("❌ pyttsx3 Not Installed")
                st.code("pip install pyttsx3")
        
        with col3:
            if EDGE_TTS_AVAILABLE:
                st.success("✅ edge-tts Available")
            else:
                st.error("❌ edge-tts Not Installed")
                st.code("pip install edge-tts")

def create_audio_player(audio_data: bytes, audio_format: str = "audio/mp3") -> str:
    """Create a mobile-friendly audio player"""
    # Convert audio to base64
    audio_b64 = base64.b64encode(audio_data).decode()
    
    # Create HTML audio player with mobile-friendly controls
    audio_html = f"""
    <div style="margin: 20px 0;">
        <audio controls style="width: 100%; height: 50px;" preload="auto">
            <source src="data:{audio_format};base64,{audio_b64}" type="{audio_format}">
            Your browser does not support the audio element.
        </audio>
    </div>
    """
    return audio_html

def main():
    st.title("📚 Free TTS Audiobook Reader - NCF 2023")
    st.markdown("*National Curriculum Framework for School Education 2023*")
    st.markdown("---")
    
    # Start health check
    if 'health_check_started' not in st.session_state:
        health_checker.start_health_check()
        st.session_state.health_check_started = True
    
    # Display TTS status
    display_tts_status()
    
    # Check if any TTS is available
    if not any([GTTS_AVAILABLE, PYTTSX3_AVAILABLE, EDGE_TTS_AVAILABLE]):
        st.error("❌ No TTS libraries found! Please install at least one:")
        st.code("pip install gtts pyttsx3 edge-tts")
        st.stop()
    
    # Initialize TTS client
    if 'tts_client' not in st.session_state:
        st.session_state.tts_client = FreeTTSClient()
    
    tts_client = st.session_state.tts_client
    
    # Load audiobook content
    file_path = "full_text.txt"
    if not os.path.exists(file_path):
        st.error(f"📄 Text file '{file_path}' not found!")
        st.info("Please ensure 'full_text.txt' is in the same directory as this app.")
        st.stop()
    
    if 'parsed_content' not in st.session_state:
        with st.spinner("📖 Loading NCF 2023 content..."):
            parser = AudiobookParser(file_path)
            st.session_state.parsed_content = parser.parse_text_file()
            st.session_state.metadata = parser.metadata
    
    parsed_content = st.session_state.parsed_content
    metadata = st.session_state.get('metadata', {})
    
    if not parsed_content:
        st.error("❌ Failed to parse the audiobook file!")
        st.stop()
    
    # Sidebar
    with st.sidebar:
        st.header("🎛️ Controls")
        
        # TTS Selection
        available_options = get_available_tts_options()
        
        if available_options:
            st.subheader("🗣️ TTS Engine")
            selected_tts = st.selectbox(
                "Choose TTS Engine:",
                options=list(available_options.keys()),
                format_func=lambda x: available_options[x]["name"],
                key="tts_selector"
            )
            
            # Show TTS info
            tts_info = available_options[selected_tts]
            st.info(f"**{tts_info['name']}**\n\n{tts_info['description']}\n\nQuality: {tts_info['quality']}")
            
            # Voice selection for Edge TTS
            selected_voice = "en-IN-NeerjaNeural"
            if selected_tts == "edge" and EDGE_TTS_AVAILABLE:
                voices = [
                    "en-IN-NeerjaNeural",
                    "en-IN-PrabhatNeural", 
                    "en-US-AriaNeural",
                    "en-US-GuyNeural"
                ]
                selected_voice = st.selectbox("Voice:", voices, key="voice_selector")
        
        # Section navigation
        st.subheader("📖 Navigation")
        sections = list(parsed_content.keys())
        
        if 'current_section' not in st.session_state:
            st.session_state.current_section = sections[0] if sections else None
        
        selected_section = st.selectbox(
            "Select Section:",
            sections,
            index=sections.index(st.session_state.current_section) if st.session_state.current_section in sections else 0,
            key="section_selector"
        )
        st.session_state.current_section = selected_section
        
        # Settings
        st.subheader("⚙️ Settings")
        use_cache = st.checkbox("💾 Use audio cache", value=True)
        max_length = st.slider("Max text length for TTS", 500, 3000, 1500)
        
        # Stats
        if selected_section in parsed_content:
            current_text = parsed_content[selected_section]
            word_count = len(current_text.split())
            
            st.subheader("📊 Section Stats")
            st.metric("Words", word_count)
            st.metric("Characters", len(current_text))
            
            # Show total sections
            st.metric("Total Sections", len(sections))
    
    # Main content
    if selected_section:
        current_text = parsed_content[selected_section]
        
        st.header(f"📖 {selected_section}")
        
        # Content display
        tab1, tab2 = st.tabs(["📄 Read", "🎧 Listen"])
        
        with tab1:
            # Make text more readable on mobile
            st.markdown(f"""
            <div style="font-size: 16px; line-height: 1.6; padding: 10px;">
            {current_text.replace(chr(10), '<br>')}
            </div>
            """, unsafe_allow_html=True)
        
        with tab2:
            st.subheader("🎵 Audio Generation")
            
            # Text length handling
            text_for_tts = current_text
            if len(current_text) > max_length:
                st.warning(f"⚠️ Text will be truncated to {max_length} characters for TTS")
                text_for_tts = current_text[:max_length] + "..."
            
            # Show text that will be converted
            with st.expander("📝 Preview Text for TTS"):
                st.text_area("Text to convert:", text_for_tts, height=100, disabled=True)
            
            # Clean text
            parser = AudiobookParser("")
            cleaned_text = parser.clean_text_for_speech(text_for_tts)
            
            # Generate audio button
            col1, col2 = st.columns([3, 1])
            
            with col1:
                generate_btn = st.button("🎵 Generate Audio", type="primary", use_container_width=True)
            
            with col2:
                if st.button("🗑️ Clear Cache"):
                    try:
                        cache_dir = Path("audio_cache")
                        if cache_dir.exists():
                            for file in cache_dir.glob("*"):
                                file.unlink()
                        st.success("Cache cleared!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to clear cache: {e}")
            
            if generate_btn:
                if available_options:
                    with st.spinner(f"Generating audio with {available_options[selected_tts]['name']}..."):
                        voice = selected_voice if selected_tts == "edge" else ""
                        audio_data = tts_client.generate_tts(
                            cleaned_text, 
                            selected_tts, 
                            voice, 
                            use_cache
                        )
                        
                        if audio_data:
                            st.success("🎉 Audio generated successfully!")
                            
                            # Determine audio format
                            audio_format = "audio/mp3"
                            file_ext = ".mp3"
                            
                            # Use both Streamlit native and custom HTML player
                            st.audio(audio_data, format=audio_format)
                            
                            # Mobile-friendly HTML player as backup
                            st.markdown("**Alternative Player (if above doesn't work):**")
                            audio_html = create_audio_player(audio_data, audio_format)
                            st.markdown(audio_html, unsafe_allow_html=True)
                            
                            # Download button
                            st.download_button(
                                label="📥 Download Audio File",
                                data=audio_data,
                                file_name=f"NCF2023_{selected_section.replace(' ', '_').replace('/', '_')}{file_ext}",
                                mime=audio_format,
                                use_container_width=True
                            )
                            
                            # Store in session state for playback
                            st.session_state[f'audio_{selected_section}'] = audio_data
                            
                        else:
                            st.error("❌ Failed to generate audio. Please try again or switch TTS engines.")
                else:
                    st.error("No TTS engines available")
            
            # Show cached audio if available
            if f'audio_{selected_section}' in st.session_state:
                st.markdown("---")
                st.markdown("**🔄 Previously Generated Audio:**")
                cached_audio = st.session_state[f'audio_{selected_section}']
                st.audio(cached_audio, format="audio/mp3")
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; padding: 20px;'>
            <p><strong>Free TTS Audiobook Reader for NCF 2023</strong></p>
            <p>🆓 Using Free TTS Libraries | No API Keys Required</p>
            <p>📱 Mobile Optimized | 💾 Audio Caching Enabled</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Health endpoint for Render
    if st.query_params.get("health") == "check":
        st.json({"status": "healthy", "timestamp": time.time()})

if __name__ == "__main__":
    main()