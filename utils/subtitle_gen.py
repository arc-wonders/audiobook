import os
import re
from pathlib import Path
from datetime import timedelta

try:
    import srt
    SRT_AVAILABLE = True
except ImportError:
    SRT_AVAILABLE = False

class SubtitleGenerator:
    def __init__(self):
        self.output_dir = Path("output/subtitles")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Estimated speaking rates (words per minute)
        self.wpm_slow = 140
        self.wpm_normal = 180
        self.wpm_fast = 220
        self.default_wpm = self.wpm_normal
    
    def generate_subtitles(self, text_file_path, audio_files):
        """Generate subtitle files for audio chapters"""
        if not os.path.exists(text_file_path):
            raise FileNotFoundError(f"Text file not found: {text_file_path}")
        
        # Read and parse text
        with open(text_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        chapters = self._parse_chapters(content)
        subtitle_files = []
        
        for i, (title, text) in enumerate(chapters):
            print(f"Generating subtitles for: {title}")
            
            # Match with audio file
            audio_file = None
            if i < len(audio_files):
                audio_file = audio_files[i]
            
            # Create subtitle file
            safe_title = re.sub(r'[^\w\s-]', '', title).strip()
            safe_title = re.sub(r'[-\s]+', '_', safe_title)
            filename = f"chapter_{i+1:02d}_{safe_title}.srt"
            filepath = self.output_dir / filename
            
            # Generate subtitles
            self._create_srt_file(text, str(filepath), audio_file)
            subtitle_files.append(filepath)
        
        return subtitle_files
    
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
    
    def _create_srt_file(self, text, output_path, audio_file=None):
        """Create SRT subtitle file"""
        # Get audio duration if available
        audio_duration = self._get_audio_duration(audio_file) if audio_file else None
        
        # Split text into subtitle chunks
        subtitle_chunks = self._split_text_for_subtitles(text)
        
        # Calculate timing
        timings = self._calculate_timings(subtitle_chunks, audio_duration)
        
        # Create subtitle entries
        if SRT_AVAILABLE:
            self._create_srt_with_library(subtitle_chunks, timings, output_path)
        else:
            self._create_srt_manual(subtitle_chunks, timings, output_path)
    
    def _split_text_for_subtitles(self, text, max_chars=80):
        """Split text into subtitle-appropriate chunks"""
        # Clean text
        text = re.sub(r'\n\s*\n', ' ', text)  # Remove paragraph breaks
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Split by sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # If sentence is too long, split by commas or length
            if len(sentence) > max_chars:
                sub_chunks = self._split_long_sentence(sentence, max_chars)
                for sub_chunk in sub_chunks:
                    if len(current_chunk) + len(sub_chunk) > max_chars:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sub_chunk
                    else:
                        current_chunk += " " + sub_chunk if current_chunk else sub_chunk
            else:
                # Add sentence to current chunk if it fits
                if len(current_chunk) + len(sentence) + 1 > max_chars:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    current_chunk += " " + sentence if current_chunk else sentence
        
        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _split_long_sentence(self, sentence, max_chars):
        """Split long sentence by commas or natural breaks"""
        # Try splitting by commas first
        parts = sentence.split(',')
        if len(parts) > 1:
            chunks = []
            current = ""
            for part in parts:
                part = part.strip()
                if len(current) + len(part) + 1 > max_chars:
                    if current:
                        chunks.append(current.strip())
                    current = part
                else:
                    current += ", " + part if current else part
            if current:
                chunks.append(current.strip())
            return chunks
        
        # Fallback: split by words
        words = sentence.split()
        chunks = []
        current = ""
        
        for word in words:
            if len(current) + len(word) + 1 > max_chars:
                if current:
                    chunks.append(current.strip())
                current = word
            else:
                current += " " + word if current else word
        
        if current:
            chunks.append(current.strip())
        
        return chunks
    
    def _calculate_timings(self, chunks, audio_duration=None):
        """Calculate timing for each subtitle chunk"""
        total_words = sum(len(chunk.split()) for chunk in chunks)
        
        if audio_duration:
            # Use actual audio duration
            actual_wpm = total_words / (audio_duration / 60)
            speaking_rate = min(max(actual_wpm, self.wpm_slow), self.wpm_fast)
        else:
            # Use default speaking rate
            speaking_rate = self.default_wpm
        
        timings = []
        current_time = 0
        
        for chunk in chunks:
            word_count = len(chunk.split())
            duration = (word_count / speaking_rate) * 60  # Convert to seconds
            
            start_time = current_time
            end_time = current_time + duration
            
            timings.append((start_time, end_time))
            current_time = end_time + 0.5  # Small pause between subtitles
        
        return timings
    
    def _get_audio_duration(self, audio_file):
        """Get duration of audio file"""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(str(audio_file))
            return len(audio) / 1000.0  # Convert to seconds
        except:
            # Fallback: estimate from file size (very rough)
            if os.path.exists(audio_file):
                file_size = os.path.getsize(audio_file)
                # Rough estimate: 1MB ≈ 1 minute for speech MP3
                return (file_size / (1024 * 1024)) * 60
            return None
    
    def _create_srt_with_library(self, chunks, timings, output_path):
        """Create SRT file using srt library"""
        subtitles = []
        
        for i, (chunk, (start_time, end_time)) in enumerate(zip(chunks, timings)):
            subtitle = srt.Subtitle(
                index=i + 1,
                start=timedelta(seconds=start_time),
                end=timedelta(seconds=end_time),
                content=chunk
            )
            subtitles.append(subtitle)
        
        # Write SRT file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt.compose(subtitles))
    
    def _create_srt_manual(self, chunks, timings, output_path):
        """Create SRT file manually (fallback)"""
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, (chunk, (start_time, end_time)) in enumerate(zip(chunks, timings)):
                # Format timestamps
                start_ts = self._format_timestamp(start_time)
                end_ts = self._format_timestamp(end_time)
                
                # Write SRT entry
                f.write(f"{i + 1}\n")
                f.write(f"{start_ts} --> {end_ts}\n")
                f.write(f"{chunk}\n\n")
    
    def _format_timestamp(self, seconds):
        """Format seconds to SRT timestamp format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def validate_srt_file(self, srt_path):
        """Validate SRT file format"""
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if SRT_AVAILABLE:
                list(srt.parse(content))
                return True, "Valid SRT file"
            else:
                # Basic validation
                if "-->" in content and content.strip():
                    return True, "Basic SRT format detected"
                else:
                    return False, "Invalid SRT format"
        
        except Exception as e:
            return False, f"Validation error: {str(e)}"