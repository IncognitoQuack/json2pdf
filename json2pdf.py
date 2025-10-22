import streamlit as st
import json
import requests
import os
import tempfile
from datetime import datetime
import re
from pathlib import Path
import base64
from io import BytesIO

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

# Page configuration
st.set_page_config(
    page_title="Transcript to Book Converter",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Professional dark theme CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #0a0e27 0%, #151932 100%);
        font-family: 'Inter', sans-serif;
    }
    
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 1rem;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        text-align: center;
    }
    
    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 2.5rem;
    }
    
    .main-header p {
        color: rgba(255,255,255,0.9);
        margin-top: 0.5rem;
    }
    
    .stTextArea textarea {
        background-color: #1a1f3a;
        color: #e4e7eb;
        border: 1px solid #2d3561;
        border-radius: 0.5rem;
        font-family: 'Monaco', 'Courier New', monospace;
    }
    
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        border-radius: 0.5rem;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    
    .success-box {
        padding: 1rem;
        background: rgba(16, 185, 129, 0.1);
        border-left: 4px solid #10b981;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    
    .error-box {
        padding: 1rem;
        background: rgba(239, 68, 68, 0.1);
        border-left: 4px solid #ef4444;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    
    .info-box {
        padding: 1rem;
        background: rgba(59, 130, 246, 0.1);
        border-left: 4px solid #3b82f6;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    
    pre {
        background-color: #1a1f3a !important;
        border: 1px solid #2d3561;
        border-radius: 0.5rem;
        padding: 1rem !important;
        color: #e4e7eb !important;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        color: #e4e7eb;
        font-weight: 500;
    }
    
    .download-area {
        background: rgba(26, 31, 58, 0.6);
        border: 1px solid #2d3561;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'latex_content' not in st.session_state:
    st.session_state.latex_content = None
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None
if 'transcript_data' not in st.session_state:
    st.session_state.transcript_data = None

class TranscriptProcessor:
    """Process and convert transcripts to various formats"""
    
    @staticmethod
    def detect_structure(transcript):
        """Detect chapters and sections in transcript"""
        structure = {
            'chapters': [],
            'current_chapter': None,
            'current_section': None
        }
        
        for i, entry in enumerate(transcript):
            text = entry.get('text', '').strip()
            if not text:
                continue
            
            # Check for chapter markers
            chapter_match = re.search(r'\bchapter\s+(\d+)[:\s]*([^.]*)', text, re.IGNORECASE)
            if chapter_match:
                chapter_num = chapter_match.group(1)
                chapter_title = chapter_match.group(2).strip() or f"Chapter {chapter_num}"
                
                structure['chapters'].append({
                    'number': chapter_num,
                    'title': chapter_title,
                    'sections': [],
                    'content': []
                })
                structure['current_chapter'] = len(structure['chapters']) - 1
                structure['current_section'] = None
                continue
            
            # Check for section markers
            section_match = re.search(r'\bsection\s+([\d.]+)[:\s]*([^.]*)', text, re.IGNORECASE)
            if section_match and structure['current_chapter'] is not None:
                section_num = section_match.group(1)
                section_title = section_match.group(2).strip() or f"Section {section_num}"
                
                structure['chapters'][structure['current_chapter']]['sections'].append({
                    'number': section_num,
                    'title': section_title,
                    'content': []
                })
                structure['current_section'] = len(structure['chapters'][structure['current_chapter']]['sections']) - 1
                continue
            
            # Add content to appropriate location
            if structure['current_chapter'] is not None:
                if structure['current_section'] is not None:
                    structure['chapters'][structure['current_chapter']]['sections'][structure['current_section']]['content'].append(entry)
                else:
                    structure['chapters'][structure['current_chapter']]['content'].append(entry)
            else:
                # No chapter yet, create default
                if not structure['chapters']:
                    structure['chapters'].append({
                        'number': '1',
                        'title': 'Introduction',
                        'sections': [],
                        'content': []
                    })
                    structure['current_chapter'] = 0
                structure['chapters'][0]['content'].append(entry)
        
        return structure
    
    @staticmethod
    def process_math_text(text):
        """Convert math notation in text to readable format"""
        # Simple math conversions for display
        conversions = [
            (r'\bR\^n\b', 'ℝⁿ'),
            (r'\bR\^(\d+)', r'ℝ^\1'),
            (r'sqrt\(([^)]+)\)', r'√(\1)'),
            (r'sum from (\w+)=(\w+) to (\w+)', r'Σ(\1=\2 to \3)'),
            (r'integral from (\w+) to (\w+)', r'∫(\1 to \2)'),
            (r'lim as (\w+) (?:approaches|->|→) (\w+)', r'lim(\1→\2)'),
            (r'\balpha\b', 'α'),
            (r'\bbeta\b', 'β'),
            (r'\bgamma\b', 'γ'),
            (r'\bdelta\b', 'δ'),
            (r'\bepsilon\b', 'ε'),
            (r'\btheta\b', 'θ'),
            (r'\blambda\b', 'λ'),
            (r'\bpi\b', 'π'),
            (r'\bsigma\b', 'σ'),
            (r'\bomega\b', 'ω'),
            (r'd/dx', 'd/dx'),
            (r'e\^x', 'eˣ'),
            (r'x\^2', 'x²'),
            (r'x\^3', 'x³'),
            (r'x\^n', 'xⁿ'),
        ]
        
        result = text
        for pattern, replacement in conversions:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        return result

def generate_latex_with_ai(transcript_json, api_key):
    """Generate LaTeX using OpenRouter AI"""
    
    prompt = f"""Convert this educational video transcript into a professional LaTeX book document.

Title: {transcript_json.get('video_title', 'Course')}
Instructor: {transcript_json.get('instructor', 'Instructor')}

Transcript entries (first 15):
{json.dumps(transcript_json.get('transcript', [])[:15], indent=2)}

Requirements:
1. Create a complete LaTeX document using \\documentclass{{book}}
2. Include necessary packages: amsmath, amssymb, geometry, hyperref
3. Detect and create \\chapter{{}} and \\section{{}} from the transcript
4. Convert mathematical expressions to proper LaTeX math mode
5. Properly escape special LaTeX characters in regular text
6. Format URLs with \\href{{}}{{}}
7. Create a title page and table of contents

Output ONLY the LaTeX code from \\documentclass to \\end{{document}}.
No explanations, no markdown code blocks, just pure LaTeX."""

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://json2pdf-phe4ltl9d9bcmsnrehrczd.streamlit.app",
                "X-Title": "Transcript to Book Converter"
            },
            data=json.dumps({
                "model": "alibaba/tongyi-deepresearch-30b-a3b:free",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a LaTeX expert. Output only valid, compilable LaTeX code."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.25,
                # "max_tokens": 10000
            }),
            timeout=60
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # Clean any markdown formatting if present
            content = re.sub(r'^```[\w]*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)
            return content.strip(), None
        else:
            return None, f"API Error: {response.status_code}"
            
    except requests.exceptions.Timeout:
        return None, "Request timed out. Please try again."
    except Exception as e:
        return None, f"Error: {str(e)}"

def generate_latex_manual(transcript_json, processor):
    """Generate LaTeX manually without AI"""
    
    title = transcript_json.get('video_title', 'Educational Course').replace('&', '\\&').replace('%', '\\%').replace('$', '\\$')
    instructor = transcript_json.get('instructor', 'Instructor').replace('&', '\\&').replace('%', '\\%').replace('$', '\\$')
    transcript = transcript_json.get('transcript', [])
    
    # Detect structure
    structure = processor.detect_structure(transcript)
    
    latex = r"""\documentclass[12pt,a4paper]{book}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{geometry}
\usepackage[colorlinks=true,linkcolor=blue,urlcolor=blue]{hyperref}
\usepackage{graphicx}
\usepackage{fancyhdr}

\geometry{margin=1in}

\title{""" + title + r"""}
\author{""" + instructor + r"""}
\date{\today}

\begin{document}

\frontmatter
\maketitle
\tableofcontents

\mainmatter

"""
    
    # Process chapters
    for chapter in structure['chapters']:
        latex += f"\\chapter{{{chapter['title']}}}\n\n"
        
        # Chapter content
        for entry in chapter['content']:
            text = entry.get('text', '')
            # Process text
            text = processor.process_math_text(text)
            # Escape LaTeX special characters
            text = text.replace('\\', '\\textbackslash{}')
            text = text.replace('&', '\\&')
            text = text.replace('%', '\\%')
            text = text.replace('$', '\\$')
            text = text.replace('#', '\\#')
            text = text.replace('_', '\\_')
            text = text.replace('{', '\\{')
            text = text.replace('}', '\\}')
            text = text.replace('~', '\\textasciitilde{}')
            text = text.replace('^', '\\textasciicircum{}')
            
            # Handle URLs
            text = re.sub(r'(https?://[^\s]+)', r'\\url{\1}', text)
            
            latex += text + "\n\n"
        
        # Process sections
        for section in chapter['sections']:
            latex += f"\\section{{{section['title']}}}\n\n"
            
            for entry in section['content']:
                text = entry.get('text', '')
                text = processor.process_math_text(text)
                # Escape LaTeX special characters
                text = text.replace('\\', '\\textbackslash{}')
                text = text.replace('&', '\\&')
                text = text.replace('%', '\\%')
                text = text.replace('$', '\\$')
                text = text.replace('#', '\\#')
                text = text.replace('_', '\\_')
                text = text.replace('{', '\\{')
                text = text.replace('}', '\\}')
                text = text.replace('~', '\\textasciitilde{}')
                text = text.replace('^', '\\textasciicircum{}')
                
                # Handle URLs
                text = re.sub(r'(https?://[^\s]+)', r'\\url{\1}', text)
                
                latex += text + "\n\n"
    
    latex += r"""
\end{document}"""
    
    return latex

def generate_pdf_with_reportlab(transcript_json, processor):
    """Generate PDF using ReportLab - pure Python solution"""
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=28,
        textColor=HexColor('#2c3e50'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    author_style = ParagraphStyle(
        'Author',
        parent=styles['Normal'],
        fontSize=16,
        textColor=HexColor('#34495e'),
        alignment=TA_CENTER,
        spaceAfter=12
    )
    
    chapter_style = ParagraphStyle(
        'ChapterTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=HexColor('#8b4789'),
        spaceAfter=20,
        spaceBefore=30,
        fontName='Helvetica-Bold',
        keepWithNext=True
    )
    
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=HexColor('#667eea'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold',
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
        leading=14
    )
    
    # Title page
    title = transcript_json.get('video_title', 'Educational Course')
    instructor = transcript_json.get('instructor', 'Instructor')
    
    elements.append(Spacer(1, 2*inch))
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(f"by {instructor}", author_style))
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph(datetime.now().strftime("%B %Y"), author_style))
    elements.append(PageBreak())
    
    # Table of Contents
    toc_title = Paragraph("Table of Contents", chapter_style)
    elements.append(toc_title)
    elements.append(Spacer(1, 0.5*inch))
    
    # Detect structure
    structure = processor.detect_structure(transcript_json.get('transcript', []))
    
    # Generate TOC
    toc_entries = []
    for i, chapter in enumerate(structure['chapters'], 1):
        toc_entries.append(Paragraph(f"Chapter {chapter['number']}: {chapter['title']}", body_style))
        for section in chapter['sections']:
            toc_entries.append(Paragraph(f"    Section {section['number']}: {section['title']}", body_style))
    
    elements.extend(toc_entries)
    elements.append(PageBreak())
    
    # Process content
    for chapter in structure['chapters']:
        # Chapter title
        elements.append(Paragraph(f"Chapter {chapter['number']}: {chapter['title']}", chapter_style))
        
        # Chapter content
        for entry in chapter['content']:
            text = entry.get('text', '').strip()
            if text and not re.search(r'\bchapter\s+\d+\b', text, re.IGNORECASE):
                # Process math notation for display
                text = processor.process_math_text(text)
                
                # Escape XML/HTML characters for ReportLab
                text = text.replace('&', '&amp;')
                text = text.replace('<', '&lt;')
                text = text.replace('>', '&gt;')
                
                # Convert URLs to links
                text = re.sub(
                    r'(https?://[^\s]+)',
                    r'<link href="\1" color="blue">\1</link>',
                    text
                )
                
                # Add paragraph
                para = Paragraph(text, body_style)
                elements.append(para)
        
        # Process sections
        for section in chapter['sections']:
            elements.append(Paragraph(f"Section {section['number']}: {section['title']}", section_style))
            
            for entry in section['content']:
                text = entry.get('text', '').strip()
                if text and not re.search(r'\bsection\s+[\d.]+\b', text, re.IGNORECASE):
                    # Process math notation
                    text = processor.process_math_text(text)
                    
                    # Escape XML/HTML characters
                    text = text.replace('&', '&amp;')
                    text = text.replace('<', '&lt;')
                    text = text.replace('>', '&gt;')
                    
                    # Convert URLs to links
                    text = re.sub(
                        r'(https?://[^\s]+)',
                        r'<link href="\1" color="blue">\1</link>',
                        text
                    )
                    
                    para = Paragraph(text, body_style)
                    elements.append(para)
    
    # Build PDF
    try:
        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes, None
    except Exception as e:
        return None, f"PDF generation error: {str(e)}"

def get_sample_json():
    """Provide sample JSON for testing"""
    return {
        "video_title": "Introduction to Machine Learning",
        "instructor": "Dr. Sarah Chen",
        "duration": "1:45:30",
        "transcript": [
            {
                "timestamp": "00:00:00",
                "text": "Welcome to this comprehensive course on Machine Learning. I'm Dr. Sarah Chen, and I'll be your instructor."
            },
            {
                "timestamp": "00:00:15",
                "text": "Chapter 1: Foundations of Machine Learning. Let's begin our journey into the world of artificial intelligence."
            },
            {
                "timestamp": "00:00:45",
                "text": "Machine learning is a subset of artificial intelligence that enables computers to learn from data without being explicitly programmed."
            },
            {
                "timestamp": "00:01:30",
                "text": "The fundamental equation in linear regression is y = mx + b, where m represents the slope and b is the y-intercept."
            },
            {
                "timestamp": "00:02:15",
                "text": "Section 1.1: Types of Learning. There are three main paradigms in machine learning."
            },
            {
                "timestamp": "00:02:45",
                "text": "First, supervised learning uses labeled data to train models. The algorithm learns from input-output pairs."
            },
            {
                "timestamp": "00:03:30",
                "text": "The loss function for mean squared error is L = sum from i=1 to n of (y_i - y_hat_i)^2 divided by n."
            },
            {
                "timestamp": "00:04:15",
                "text": "Second, unsupervised learning discovers hidden patterns in unlabeled data without predefined categories."
            },
            {
                "timestamp": "00:05:00",
                "text": "Third, reinforcement learning involves an agent learning through interaction with an environment."
            },
            {
                "timestamp": "00:05:45",
                "text": "Chapter 2: Neural Networks and Deep Learning. Now let's explore the architecture of neural networks."
            },
            {
                "timestamp": "00:06:30",
                "text": "A neural network consists of layers of interconnected nodes, inspired by biological neurons."
            },
            {
                "timestamp": "00:07:15",
                "text": "The activation function sigmoid(x) = 1/(1 + e^(-x)) introduces non-linearity into the network."
            },
            {
                "timestamp": "00:08:00",
                "text": "Section 2.1: Backpropagation. The backpropagation algorithm is crucial for training neural networks."
            },
            {
                "timestamp": "00:08:45",
                "text": "The gradient descent update rule is theta = theta - alpha times the gradient, where alpha is the learning rate."
            },
            {
                "timestamp": "00:09:30",
                "text": "Chapter 3: Practical Applications. Machine learning has revolutionized many industries."
            },
            {
                "timestamp": "00:10:15",
                "text": "In healthcare, ML models can predict diseases and assist in diagnosis with remarkable accuracy."
            },
            {
                "timestamp": "00:11:00",
                "text": "For more resources, visit our course website at https://ml-course.edu and the TensorFlow documentation at https://tensorflow.org"
            },
            {
                "timestamp": "00:11:45",
                "text": "Remember: The key to mastering machine learning is understanding both the theory and practical implementation."
            }
        ]
    }

def main():
    # Header
    st.markdown("""
    <div class='main-header'>
        <h1>📚 Transcript to Book Converter</h1>
        <p>Transform educational video transcripts into professional books</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize processor
    processor = TranscriptProcessor()
    
    # Sidebar configuration
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        
        # API Key (optional)
        api_key = st.text_input(
            "🔑 OpenRouter API Key (Optional)",
            type="password",
            help="Enter your API key for AI-powered LaTeX generation. Leave empty for manual processing."
        )
        
        if api_key:
            st.success("✅ API key provided")
        else:
            st.info("ℹ️ Manual processing mode")
        
        st.divider()
        
        # Input method
        st.markdown("## 📥 Input Method")
        
        input_choice = st.radio(
            "Select input source:",
            ["📁 Upload JSON", "📝 Paste JSON", "🎯 Use Sample Data"]
        )
        
        transcript_json = None
        
        if input_choice == "📁 Upload JSON":
            uploaded_file = st.file_uploader(
                "Choose a JSON file",
                type=['json'],
                help="Upload a JSON file containing the video transcript"
            )
            if uploaded_file:
                try:
                    transcript_json = json.load(uploaded_file)
                    st.success(f"✅ Loaded: {uploaded_file.name}")
                except json.JSONDecodeError as e:
                    st.error(f"❌ Invalid JSON: {str(e)}")
        
        elif input_choice == "📝 Paste JSON":
            json_input = st.text_area(
                "Paste your JSON here:",
                height=250,
                placeholder='{"video_title": "...", "instructor": "...", "transcript": [...]}'
            )
            if json_input:
                try:
                    transcript_json = json.loads(json_input)
                    st.success("✅ JSON parsed successfully")
                except json.JSONDecodeError as e:
                    st.error(f"❌ Invalid JSON: {str(e)}")
        
        else:  # Use Sample Data
            if st.button("📥 Load Sample Data", use_container_width=True):
                transcript_json = get_sample_json()
                st.session_state.transcript_data = transcript_json
                st.success("✅ Sample data loaded")
        
        # Keep the loaded data in session state
        if transcript_json:
            st.session_state.transcript_data = transcript_json
        
        st.divider()
        
        # Generation options
        st.markdown("## 🎯 Generation Options")
        
        use_ai = st.checkbox(
            "🤖 Use AI for LaTeX",
            value=bool(api_key),
            disabled=not api_key,
            help="Use OpenRouter AI to generate professional LaTeX"
        )
        
        # Generate buttons
        st.markdown("## 🚀 Generate Documents")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📄 Generate LaTeX", use_container_width=True, type="primary"):
                if st.session_state.transcript_data:
                    with st.spinner("Generating LaTeX..."):
                        if use_ai and api_key:
                            latex_content, error = generate_latex_with_ai(st.session_state.transcript_data, api_key)
                            if latex_content:
                                st.session_state.latex_content = latex_content
                                st.success("✅ LaTeX generated with AI")
                            else:
                                st.warning(f"AI generation failed: {error}")
                                st.info("Falling back to manual generation...")
                                st.session_state.latex_content = generate_latex_manual(st.session_state.transcript_data, processor)
                                st.success("✅ LaTeX generated manually")
                        else:
                            st.session_state.latex_content = generate_latex_manual(st.session_state.transcript_data, processor)
                            st.success("✅ LaTeX generated")
                else:
                    st.error("❌ Please load transcript data first")
        
        with col2:
            if st.button("📕 Generate PDF", use_container_width=True, type="primary"):
                if st.session_state.transcript_data:
                    with st.spinner("Generating PDF..."):
                        pdf_bytes, error = generate_pdf_with_reportlab(st.session_state.transcript_data, processor)
                        if pdf_bytes:
                            st.session_state.pdf_bytes = pdf_bytes
                            st.success("✅ PDF generated")
                        else:
                            st.error(f"❌ PDF generation failed: {error}")
                else:
                    st.error("❌ Please load transcript data first")
    
    # Main content area
    if st.session_state.transcript_data:
        tabs = st.tabs(["📊 Preview", "📄 LaTeX", "📥 Downloads", "📋 Structure"])
        
        with tabs[0]:  # Preview
            st.markdown("### 📖 Document Information")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Title:** {st.session_state.transcript_data.get('video_title', 'N/A')}")
                st.markdown(f"**Instructor:** {st.session_state.transcript_data.get('instructor', 'N/A')}")
            with col2:
                st.markdown(f"**Duration:** {st.session_state.transcript_data.get('duration', 'N/A')}")
                st.markdown(f"**Entries:** {len(st.session_state.transcript_data.get('transcript', []))}")
            
            with st.expander("📝 View Raw Transcript"):
                st.json(st.session_state.transcript_data)
        
        with tabs[1]:  # LaTeX
            if st.session_state.latex_content:
                st.markdown("### 📄 Generated LaTeX Code")
                st.code(st.session_state.latex_content[:5000] + "\n...[truncated for display]" if len(st.session_state.latex_content) > 5000 else st.session_state.latex_content, language='latex')
            else:
                st.info("💡 Click 'Generate LaTeX' to create LaTeX code")
        
        with tabs[2]:  # Downloads
            st.markdown("### 📥 Download Your Documents")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.session_state.latex_content:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    st.download_button(
                        label="📄 Download LaTeX (.tex)",
                        data=st.session_state.latex_content,
                        file_name=f"transcript_book_{timestamp}.tex",
                        mime="text/x-tex",
                        use_container_width=True
                    )
                else:
                    st.info("Generate LaTeX first")
            
            with col2:
                if st.session_state.pdf_bytes:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    st.download_button(
                        label="📕 Download PDF",
                        data=st.session_state.pdf_bytes,
                        file_name=f"transcript_book_{timestamp}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.info("Generate PDF first")
        
        with tabs[3]:  # Structure
            st.markdown("### 📋 Document Structure")
            structure = processor.detect_structure(st.session_state.transcript_data.get('transcript', []))
            
            for chapter in structure['chapters']:
                with st.expander(f"📖 Chapter {chapter['number']}: {chapter['title']}"):
                    st.markdown(f"**Content entries:** {len(chapter['content'])}")
                    if chapter['sections']:
                        st.markdown("**Sections:**")
                        for section in chapter['sections']:
                            st.markdown(f"- Section {section['number']}: {section['title']} ({len(section['content'])} entries)")
    
    else:
        # Welcome screen
        st.markdown("""
        <div class='info-box'>
        <h3>👋 Welcome to Transcript to Book Converter!</h3>
        <p>This tool transforms educational video transcripts into professional books.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div class='success-box'>
            <h4>✨ Features</h4>
            <ul>
            <li>Auto-detect chapters & sections</li>
            <li>Convert math notation</li>
            <li>Generate professional PDFs</li>
            <li>Export LaTeX code</li>
            </ul>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class='info-box'>
            <h4>🚀 Quick Start</h4>
            <ol>
            <li>Load sample data</li>
            <li>Generate LaTeX/PDF</li>
            <li>Download your book</li>
            </ol>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class='success-box'>
            <h4>💡 No Installation</h4>
            <p>Works directly in browser. No LaTeX installation required!</p>
            </div>
            """, unsafe_allow_html=True)
        
        # JSON Format Example
        with st.expander("📋 Expected JSON Format"):
            st.code(json.dumps(get_sample_json(), indent=2)[:1000] + "...", language='json')

if __name__ == "__main__":
    main()
