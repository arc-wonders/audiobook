import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re

class PDFExtractor:
    def __init__(self):
        self.skip_keywords = [
            'acknowledgement', 'foreword', 'preamble', 
            'table of contents', 'index', 'bibliography'
        ]
        self.min_text_length = 200
    
    def extract_and_filter(self, pdf_path):
        """Extract text from PDF with OCR fallback and filtering"""
        doc = fitz.open(pdf_path)
        chapters = []
        current_chapter = ""
        current_title = "Introduction"
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Extract text
            text = page.get_text()
            
            # Check if OCR is needed (low text density)
            if len(text.strip()) < 50:
                text = self._ocr_page(page)
            
            # Skip irrelevant pages
            if self._should_skip_page(text):
                continue
            
            # Clean and process text
            cleaned_text = self._clean_text(text)
            if len(cleaned_text) < self.min_text_length:
                continue
            
            # Detect chapter boundaries
            chapter_match = self._detect_chapter(cleaned_text)
            if chapter_match:
                # Save previous chapter
                if current_chapter.strip():
                    chapters.append((current_title, current_chapter.strip()))
                
                # Start new chapter
                current_title = chapter_match
                current_chapter = cleaned_text
            else:
                current_chapter += "\n" + cleaned_text
        
        # Add final chapter
        if current_chapter.strip():
            chapters.append((current_title, current_chapter.strip()))
        
        doc.close()
        return chapters
    
    def _ocr_page(self, page):
        """Perform OCR on a page"""
        try:
            # Render page as image
            mat = fitz.Matrix(2.0, 2.0)  # High resolution
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            
            # Convert to PIL Image
            image = Image.open(io.BytesIO(img_data))
            
            # Perform OCR
            text = pytesseract.image_to_string(image, lang='eng')
            return text
        
        except Exception as e:
            print(f"OCR failed: {str(e)}")
            return ""
    
    def _should_skip_page(self, text):
        """Check if page should be skipped"""
        text_lower = text.lower()
        
        # Check for skip keywords
        for keyword in self.skip_keywords:
            if keyword in text_lower:
                return True
        
        # Skip if too short
        if len(text.strip()) < 50:
            return True
        
        # Skip if mostly numbers (page numbers, etc.)
        if re.match(r'^\s*[\d\s\-\.]+\s*$', text.strip()):
            return True
        
        return False
    
    def _clean_text(self, text):
        """Clean extracted text"""
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # Remove figure/table references
        text = re.sub(r'\(Fig\.\s*\d+[^\)]*\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\(Table\s*\d+[^\)]*\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Figure\s*\d+[^\n]*\n?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Table\s*\d+[^\n]*\n?', '', text, flags=re.IGNORECASE)
        
        # Remove footnote markers
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'\(\d+\)', '', text)
        
        # Remove page headers/footers patterns
        text = re.sub(r'^.*NCF.*\d{4}.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        
        # Clean up spacing
        text = text.strip()
        
        return text
    
    def _detect_chapter(self, text):
        """Detect chapter titles"""
        lines = text.split('\n')[:5]  # Check first few lines
        
        for line in lines:
            line = line.strip()
            
            # Check for chapter patterns
            if re.match(r'^(Chapter|CHAPTER)\s+\d+', line, re.IGNORECASE):
                return line
            
            if re.match(r'^\d+\.\s+[A-Z]', line):
                return line
            
            # Check for section headers (all caps, short)
            if (line.isupper() and 
                len(line.split()) <= 6 and 
                len(line) > 5 and 
                not line.isdigit()):
                return line
            
            # Check for title case headers
            if (line.istitle() and 
                len(line.split()) <= 8 and 
                len(line) > 10):
                return line
        
        return None