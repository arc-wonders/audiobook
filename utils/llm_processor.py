import subprocess
import tempfile
import os
import time

class LLMProcessor:
    def __init__(self):
        self.model_name = "mistral:7b"
        self.prompt_template = """You are preparing audiobook narration of the National Curriculum Framework (NCF 2023). Clean the following text, remove formatting issues, references to figures/tables, and footnotes. Rewrite it into spoken-friendly sentences while keeping the meaning faithful. Make it flow naturally for audio listening.

Text:
{text}

Cleaned version for audiobook:"""
    
    def refine_text(self, text, progress_callback=None):
        """Refine text using Mistral-7B via Ollama"""
        try:
            # Split large text into chunks
            chunks = self._split_text(text, max_length=2000)
            refined_chunks = []
            
            print(f"🔄 Processing {len(chunks)} text chunks with Mistral-7B...")
            
            for i, chunk in enumerate(chunks):
                if progress_callback:
                    progress_callback(f"Processing chunk {i+1}/{len(chunks)}")
                
                print(f"  📝 Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                refined_chunk = self._process_chunk(chunk)
                
                if refined_chunk:
                    refined_chunks.append(refined_chunk)
                    print(f"  ✅ Chunk {i+1} refined successfully")
                else:
                    print(f"  ⚠️  Chunk {i+1} using fallback cleaning")
                
                time.sleep(1)  # Rate limiting
            
            print(f"✅ All {len(chunks)} chunks processed!")
            return "\n\n".join(refined_chunks)
        
        except Exception as e:
            print(f"❌ LLM processing failed: {str(e)}")
            return self._fallback_cleaning(text)
    
    def _split_text(self, text, max_length=2000):
        """Split text into manageable chunks"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 > max_length:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_length = len(word)
            else:
                current_chunk.append(word)
                current_length += len(word) + 1
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def _process_chunk(self, text):
        """Process a single chunk with Mistral-7B"""
        try:
            # Create prompt
            full_prompt = self.prompt_template.format(text=text)
            
            # Write prompt to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(full_prompt)
                temp_file = f.name
            
            try:
                # Run Ollama command
                cmd = ['ollama', 'run', self.model_name]
                
                # Read prompt from file and pipe to ollama
                with open(temp_file, 'r') as f:
                    prompt_content = f.read()
                
                process = subprocess.run(
                    cmd,
                    input=prompt_content,
                    text=True,
                    capture_output=True,
                    timeout=120  # 2 minute timeout
                )
                
                if process.returncode == 0:
                    response = process.stdout.strip()
                    # Extract the cleaned text from response
                    cleaned = self._extract_cleaned_text(response, text)
                    return cleaned
                else:
                    print(f"Ollama error: {process.stderr}")
                    return self._fallback_cleaning(text)
            
            finally:
                # Clean up temp file
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
        
        except subprocess.TimeoutExpired:
            print("Ollama request timed out")
            return self._fallback_cleaning(text)
        except FileNotFoundError:
            print("Ollama not found. Please install Ollama and Mistral-7B model.")
            return self._fallback_cleaning(text)
        except Exception as e:
            print(f"Error processing with Mistral: {str(e)}")
            return self._fallback_cleaning(text)
    
    def _extract_cleaned_text(self, response, original_text):
        """Extract cleaned text from Mistral's response"""
        # Look for patterns that indicate the cleaned version
        lines = response.split('\n')
        
        # Find where the actual cleaned content starts
        cleaned_lines = []
        found_start = False
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines and common response patterns
            if not line:
                continue
            
            # Skip meta responses
            if any(skip in line.lower() for skip in [
                'here is the cleaned', 'cleaned version', 'audiobook version',
                'here\'s the', 'the cleaned text', 'narration version'
            ]):
                found_start = True
                continue
            
            # Skip if it's just repeating the prompt
            if line in original_text:
                continue
            
            # Collect actual content
            if found_start or not any(meta in line.lower() for meta in [
                'you are preparing', 'clean the following', 'remove formatting'
            ]):
                cleaned_lines.append(line)
        
        cleaned_text = '\n'.join(cleaned_lines).strip()
        
        # If extraction failed, return fallback
        if len(cleaned_text) < len(original_text) * 0.3:
            return self._fallback_cleaning(original_text)
        
        return cleaned_text
    
    def _fallback_cleaning(self, text):
        """Basic text cleaning when LLM fails"""
        import re
        
        # Remove figure/table references
        text = re.sub(r'\(Fig\.\s*\d+[^\)]*\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\(Table\s*\d+[^\)]*\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Figure\s*\d+[^\n]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Table\s*\d+[^\n]*', '', text, flags=re.IGNORECASE)
        
        # Remove footnote references
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'\(\d+\)', '', text)
        
        # Fix common formatting issues
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Multiple newlines
        text = re.sub(r'([a-z])([A-Z])', r'\1. \2', text)  # Missing periods
        text = re.sub(r'\s+', ' ', text)  # Multiple spaces
        
        # Improve readability for audio
        text = re.sub(r'\b(i\.e\.)\b', 'that is', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(e\.g\.)\b', 'for example', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(etc\.)\b', 'and so on', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(vs\.)\b', 'versus', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    def check_ollama_status(self):
        """Check if Ollama is running and model is available"""
        try:
            # Check if Ollama is running
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
            if result.returncode != 0:
                return False, "Ollama is not running"
            
            # Check if Mistral-7B model is available
            if 'mistral' not in result.stdout.lower():
                return False, "Mistral-7B model not found. Run: ollama pull mistral:7b"
            
            return True, "Ollama and Mistral-7B are ready"
        
        except FileNotFoundError:
            return False, "Ollama not installed"
        except Exception as e:
            return False, f"Error checking Ollama: {str(e)}"