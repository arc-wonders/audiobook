import os
import asyncio
import pyttsx3
from pathlib import Path
import re

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

class TTSEngine:
    def __init__(self, use_edge_tts=True):
        self.use_edge_tts = use_edge_tts and EDGE_TTS_AVAILABLE
        self.output_dir = Path("output/audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Voice settings
        if self.use_edge_tts:
            self.voice = "en-US-AriaNeural"  # Natural female voice
            self.rate = "+0%"
            self.pitch = "+0Hz"
        else:
            # Initialize pyttsx3 as fallback
            self.tts_engine = pyttsx3.init()
            voices = self.tts_engine.getProperty('voices')
            if voices:
                # Try to find a good voice
                for voice in voices:
                    if 'english' in voice.name.lower() and 'female' in voice.name.lower():
                        self.tts_engine.setProperty('voice', voice.id)
                        break
                else:
                    self.tts_engine.setProperty('voice', voices[0].id)
            
            # Set speech rate
            self.tts_engine.setProperty('rate', 180)  # Words per minute
    
    def generate_audiobook(self, text_file_path):
        """Generate audiobook from cleaned text file"""
        if not os.path.exists(text_file_path):
            raise FileNotFoundError(f"Text file not found: {text_file_path}")
        
        # Read and parse text
        with open(text_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        chapters = self._parse_chapters(content)
        audio_files = []
        
        for i, (title, text) in enumerate(chapters):
            print(f"Generating audio for: {title}")
            
            # Clean filename
            safe_title = re.sub(r'[^\w\s-]', '', title).strip()
            safe_title = re.sub(r'[-\s]+', '_', safe_title)
            filename = f"chapter_{i+1:02d}_{safe_title}.mp3"
            filepath = self.output_dir / filename
            
            # Generate audio
            if self.use_edge_tts:
                asyncio.run(self._generate_edge_tts(text, str(filepath)))
            else:
                self._generate_pyttsx3(text, str(filepath))
            
            audio_files.append(filepath)
        
        return audio_files
    
    def _parse_chapters(self, content):
        """Parse content into chapters"""
        chapters = []
        current_chapter = ""
        current_title = "Introduction"
        
        lines = content.split('\n')
        
        for line in lines:
            if line.startswith('# '):
                # Save previous chapter
                if current_chapter.strip():
                    chapters.append((current_title, current_chapter.strip()))
                
                # Start new chapter
                current_title = line[2:].strip()
                current_chapter = ""
            else:
                current_chapter += line + '\n'
        
        # Add final chapter
        if current_chapter.strip():
            chapters.append((current_title, current_chapter.strip()))
        
        return chapters
    
    async def _generate_edge_tts(self, text, output_path):
        """Generate audio using edge-tts"""
        try:
            # Split text into chunks (edge-tts has limits)
            chunks = self._split_for_tts(text)
            audio_segments = []
            
            for chunk in chunks:
                communicate = edge_tts.Communicate(chunk, self.voice)
                
                # Generate audio for chunk
                chunk_audio = b""
                async for chunk_data in communicate.stream():
                    if chunk_data["type"] == "audio":
                        chunk_audio += chunk_data["data"]
                
                audio_segments.append(chunk_audio)
            
            # Combine audio segments
            combined_audio = b"".join(audio_segments)
            
            # Save to file
            with open(output_path, "wb") as f:
                f.write(combined_audio)
            
            print(f"✅ Generated: {output_path}")
        
        except Exception as e:
            print(f"Edge-TTS failed for {output_path}: {str(e)}")
            # Fallback to pyttsx3
            self._generate_pyttsx3(text, output_path)
    
    def _generate_pyttsx3(self, text, output_path):
        """Generate audio using pyttsx3 (offline)"""
        try:
            # Split long text
            chunks = self._split_for_tts(text, max_length=1000)
            
            # Generate each chunk
            temp_files = []
            for i, chunk in enumerate(chunks):
                temp_path = output_path.replace('.mp3', f'_temp_{i}.wav')
                self.tts_engine.save_to_file(chunk, temp_path)
                self.tts_engine.runAndWait()
                temp_files.append(temp_path)
            
            # Combine audio files if multiple chunks
            if len(temp_files) > 1:
                self._combine_audio_files(temp_files, output_path)
            else:
                # Convert single WAV to MP3
                self._convert_wav_to_mp3(temp_files[0], output_path)
            
            # Clean up temp files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            
            print(f"✅ Generated: {output_path}")
        
        except Exception as e:
            print(f"pyttsx3 failed for {output_path}: {str(e)}")
    
    def _split_for_tts(self, text, max_length=2000):
        """Split text for TTS processing"""
        # Split by sentences to avoid cutting words
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += " " + sentence if current_chunk else sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _combine_audio_files(self, input_files, output_path):
        """Combine multiple audio files"""
        try:
            from pydub import AudioSegment
            
            combined = AudioSegment.empty()
            for file_path in input_files:
                if os.path.exists(file_path):
                    audio = AudioSegment.from_wav(file_path)
                    combined += audio
            
            # Export as MP3
            combined.export(output_path, format="mp3")
        
        except ImportError:
            print("pydub not available. Using first audio file only.")
            if input_files and os.path.exists(input_files[0]):
                self._convert_wav_to_mp3(input_files[0], output_path)
    
    def _convert_wav_to_mp3(self, wav_path, mp3_path):
        """Convert WAV to MP3"""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_wav(wav_path)
            audio.export(mp3_path, format="mp3")
        except ImportError:
            # If pydub not available, copy as WAV with MP3 extension
            # (not ideal but functional)
            import shutil
            shutil.copy2(wav_path, mp3_path.replace('.mp3', '.wav'))
    
    def get_available_voices(self):
        """Get list of available voices"""
        if self.use_edge_tts:
            try:
                import asyncio
                return asyncio.run(edge_tts.list_voices())
            except:
                return []
        else:
            voices = self.tts_engine.getProperty('voices')
            return [{"name": v.name, "id": v.id} for v in voices] if voices else []