import streamlit as st
import json
import requests
import os
import tempfile
from datetime import datetime
import re
from pathlib import Path
import base64
import time
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.pdfgen import canvas
from io import BytesIO
import markdown2
from weasyprint import HTML, CSS
import pdfkit

# Page configuration
st.set_page_config(
    page_title="Transcript to Book Converter Pro",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Professional dark theme
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
    }
    
    .stTextArea textarea {
        background-color: #1a1f3a;
        color: #e4e7eb;
        border: 1px solid #2d3561;
        border-radius: 0.5rem;
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
    
    .success-msg {
        padding: 1rem;
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        border-radius: 0.5rem;
        color: white;
        margin: 1rem 0;
    }
    
    .error-msg {
        padding: 1rem;
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        border-radius: 0.5rem;
        color: white;
        margin: 1rem 0;
    }
    
    .info-msg {
        padding: 1rem;
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        border-radius: 0.5rem;
        color: white;
        margin: 1rem 0;
    }
    
    pre {
        background-color: #1a1f3a !important;
        border: 1px solid #2d3561;
        border-radius: 0.5rem;
        padding: 1rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'latex_content' not in st.session_state:
    st.session_state.latex_content = None
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None
if 'html_content' not in st.session_state:
    st.session_state.html_content = None
if 'generation_method' not in st.session_state:
    st.session_state.generation_method = None

class TranscriptProcessor:
    """Main processor for converting transcripts to LaTeX/PDF"""
    
    @staticmethod
    def safe_latex_escape(text):
        """Safely escape LaTeX special characters"""
        if not text:
            return ""
        
        # Don't escape if already in math mode
        if text.strip().startswith('$') and text.strip().endswith('$'):
            return text
        
        # Dictionary of replacements - order matters!
        replacements = [
            ('\\', r'\textbackslash '),  # Must be first
            ('&', r'\&'),
            ('%', r'\%'),
            ('$', r'\$'),
            ('#', r'\#'),
            ('_', r'\_'),
            ('{', r'\{'),
            ('}', r'\}'),
            ('~', r'\textasciitilde '),
            ('^', r'\textasciicircum '),
        ]
        
        result = text
        for old, new in replacements:
            result = result.replace(old, new)
        
        return result
    
    @staticmethod
    def convert_math_expressions(text):
        """Convert verbal math to LaTeX notation"""
        
        # Protect already-formatted math
        if '$' in text:
            return text
        
        conversions = [
            # Common spaces and sets
            (r'\bR\^n\b', r'$\mathbb{R}^n$'),
            (r'\bR\^(\d+)', r'$\mathbb{R}^{\1}$'),
            (r'\bC\^n\b', r'$\mathbb{C}^n$'),
            
            # Operations
            (r'sqrt\(([^)]+)\)', r'$\sqrt{\1}$'),
            (r'log_(\w+)\(([^)]+)\)', r'$\log_{\1}(\2)$'),
            
            # Fractions (simple)
            (r'(\d+)/(\d+)', r'$\frac{\1}{\2}$'),
            
            # Limits
            (r'lim as (\w+) (?:approaches|->|→) (\w+)', r'$\lim_{\1 \to \2}$'),
            
            # Integrals
            (r'integral from (\w+) to (\w+)', r'$\int_{\1}^{\2}$'),
            (r'sum from (\w+)=(\w+) to (\w+)', r'$\sum_{\1=\2}^{\3}$'),
            
            # Greek letters
            (r'\balpha\b', r'$\alpha$'),
            (r'\bbeta\b', r'$\beta$'),
            (r'\bgamma\b', r'$\gamma$'),
            (r'\bdelta\b', r'$\delta$'),
            (r'\bepsilon\b', r'$\epsilon$'),
            (r'\btheta\b', r'$\theta$'),
            (r'\blambda\b', r'$\lambda$'),
            (r'\bpi\b', r'$\pi$'),
            (r'\bsigma\b', r'$\sigma$'),
            (r'\bomega\b', r'$\omega$'),
            
            # Derivatives
            (r'd/dx', r'$\frac{d}{dx}$'),
            (r"f'\(x\)", r"$f'(x)$"),
            (r"f''\(x\)", r"$f''(x)$"),
            
            # Common functions
            (r'sin\(', r'$\sin($'),
            (r'cos\(', r'$\cos($'),
            (r'tan\(', r'$\tan($'),
            (r'ln\(', r'$\ln($'),
            (r'e\^x', r'$e^x$'),
            (r'e\^(\w+)', r'$e^{\1}$'),
        ]
        
        result = text
        for pattern, replacement in conversions:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        return result

def call_openrouter_api(transcript_json, api_key):
    """Call OpenRouter API to generate LaTeX"""
    
    prompt = f"""You are a LaTeX expert. Convert this educational transcript to a perfect LaTeX book document.

Title: {transcript_json.get('video_title', 'Course')}
Instructor: {transcript_json.get('instructor', 'Instructor')}
Transcript: {json.dumps(transcript_json.get('transcript', [])[:10], indent=2)}  # Limit for API

Create a COMPLETE LaTeX document that:
1. Uses \\documentclass{{book}} 
2. Includes all necessary packages (amsmath, tikz, hyperref, geometry)
3. Detects and creates chapters/sections from the content
4. Converts ALL math expressions to proper LaTeX math mode
5. Escapes special characters correctly
6. Creates flowcharts where described
7. Makes URLs clickable with \\href

Output ONLY the LaTeX code from \\documentclass to \\end{{document}}.
No explanations, no markdown, just pure LaTeX that will compile without errors."""

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps({
                "model": "alibaba/tongyi-deepresearch-30b-a3b:free",
                "messages": [
                    {"role": "system", "content": "You are a LaTeX expert. Output only valid LaTeX code."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                # "max_tokens": 10000
            }),
            timeout=60
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # Clean markdown if present
            content = re.sub(r'^```[\w]*\n', '', content)
            content = re.sub(r'\n```$', '', content)
            return content.strip(), None
        else:
            return None, f"API Error: {response.status_code}"
    except Exception as e:
        return None, str(e)

def create_fallback_latex(transcript_json, processor):
    """Create LaTeX without AI - guaranteed to work"""
    
    title = processor.safe_latex_escape(transcript_json.get('video_title', 'Educational Course'))
    instructor = processor.safe_latex_escape(transcript_json.get('instructor', 'Instructor'))
    transcript = transcript_json.get('transcript', [])
    
    # Build LaTeX document
    latex = r"""\documentclass[12pt,a4paper]{book}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{geometry}
\usepackage[colorlinks=true,linkcolor=blue,urlcolor=blue]{hyperref}
\usepackage{tikz}
\usetikzlibrary{shapes.geometric,arrows.meta,positioning}

\geometry{
    top=1in,
    bottom=1in,
    left=1in,
    right=1in
}

\title{""" + title + r"""}
\author{""" + instructor + r"""}
\date{\today}

\begin{document}

\frontmatter
\maketitle
\tableofcontents

\mainmatter

"""
    
    # Process transcript
    current_chapter = False
    chapter_num = 0
    
    for entry in transcript:
        text = entry.get('text', '').strip()
        if not text:
            continue
        
        # Check for chapter markers
        if re.search(r'\bchapter\s+\d+\b', text, re.IGNORECASE):
            chapter_num += 1
            # Extract chapter title
            match = re.search(r'chapter\s+\d+[:\s]*([^.]*)', text, re.IGNORECASE)
            if match:
                chapter_title = match.group(1).strip()
            else:
                chapter_title = f"Chapter {chapter_num}"
            
            latex += f"\n\\chapter{{{processor.safe_latex_escape(chapter_title)}}}\n\n"
            current_chapter = True
            continue
        
        # Check for section markers
        if re.search(r'\bsection\s+[\d.]+\b', text, re.IGNORECASE):
            match = re.search(r'section\s+[\d.]+[:\s]*([^.]*)', text, re.IGNORECASE)
            if match:
                section_title = match.group(1).strip()
                latex += f"\n\\section{{{processor.safe_latex_escape(section_title)}}}\n\n"
                continue
        
        # If no chapters yet, create one
        if not current_chapter:
            latex += "\\chapter{Introduction}\n\n"
            current_chapter = True
        
        # Process the text
        # First convert math expressions
        processed = processor.convert_math_expressions(text)
        
        # Then escape non-math parts
        parts = processed.split('$')
        for i in range(len(parts)):
            if i % 2 == 0:  # Not in math mode
                parts[i] = processor.safe_latex_escape(parts[i])
        processed = '$'.join(parts)
        
        # Handle URLs
        processed = re.sub(
            r'(https?://[^\s]+)',
            r'\\url{\1}',
            processed
        )
        
        latex += processed + "\n\n"
    
    latex += r"""
\end{document}"""
    
    return latex

def generate_pdf_with_reportlab(transcript_json):
    """Generate PDF using ReportLab (Python-based, no external dependencies)"""
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=HexColor('#667eea'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    chapter_style = ParagraphStyle(
        'ChapterTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=HexColor('#764ba2'),
        spaceAfter=20,
        spaceBefore=30
    )
    
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=HexColor('#667eea'),
        spaceAfter=12,
        spaceBefore=20
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        alignment=TA_JUSTIFY,
        spaceAfter=12
    )
    
    # Add title page
    title = transcript_json.get('video_title', 'Educational Course')
    instructor = transcript_json.get('instructor', 'Instructor')
    
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"by {instructor}", styles['Normal']))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(datetime.now().strftime("%B %Y"), styles['Normal']))
    story.append(PageBreak())
    
    # Process transcript
    for entry in transcript_json.get('transcript', []):
        text = entry.get('text', '').strip()
        if not text:
            continue
        
        # Check for chapters
        if re.search(r'\bchapter\s+\d+\b', text, re.IGNORECASE):
            match = re.search(r'chapter\s+\d+[:\s]*([^.]*)', text, re.IGNORECASE)
            if match:
                chapter_title = match.group(1).strip()
            else:
                chapter_title = text
            story.append(Paragraph(chapter_title, chapter_style))
            continue
        
        # Check for sections
        if re.search(r'\bsection\s+[\d.]+\b', text, re.IGNORECASE):
            match = re.search(r'section\s+[\d.]+[:\s]*([^.]*)', text, re.IGNORECASE)
            if match:
                section_title = match.group(1).strip()
            else:
                section_title = text
            story.append(Paragraph(section_title, section_style))
            continue
        
        # Regular paragraph - escape XML characters
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        
        # Simple math rendering (convert to italic)
        text = re.sub(r'\$([^$]+)\$', r'<i>\1</i>', text)
        
        story.append(Paragraph(text, body_style))
    
    # Build PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes

def convert_latex_to_pdf_online(latex_content):
    """Convert LaTeX to PDF using online service"""
    
    # Method 1: Use LaTeX.Online
    try:
        # Create a request to latex.online
        response = requests.post(
            'https://latexonline.cc/compile',
            data={
                'text': latex_content,
                'command': 'pdflatex'
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.content, None
        else:
            return None, f"Online compilation failed: {response.status_code}"
    except Exception as e:
        return None, f"Online service error: {str(e)}"

def create_html_from_transcript(transcript_json, processor):
    """Create HTML version of the document"""
    
    title = transcript_json.get('video_title', 'Educational Course')
    instructor = transcript_json.get('instructor', 'Instructor')
    transcript = transcript_json.get('transcript', [])
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Crimson+Text:wght@400;600&family=Inter:wght@400;600&display=swap');
        
        body {{
            font-family: 'Crimson Text', serif;
            line-height: 1.8;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            color: #333;
            background: #fafafa;
        }}
        
        h1 {{
            font-family: 'Inter', sans-serif;
            color: #667eea;
            font-size: 2.5em;
            text-align: center;
            margin-bottom: 0.5em;
        }}
        
        h2 {{
            font-family: 'Inter', sans-serif;
            color: #764ba2;
            font-size: 1.8em;
            margin-top: 1.5em;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 0.3em;
        }}
        
        h3 {{
            font-family: 'Inter', sans-serif;
            color: #667eea;
            font-size: 1.3em;
            margin-top: 1.2em;
        }}
        
        p {{
            text-align: justify;
            margin: 1em 0;
        }}
        
        .math {{
            font-style: italic;
            color: #d63384;
            font-family: 'Times New Roman', serif;
        }}
        
        .title-page {{
            text-align: center;
            margin-bottom: 4em;
            padding: 2em;
            background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
            border-radius: 10px;
        }}
        
        .author {{
            font-size: 1.2em;
            color: #666;
            margin-top: 1em;
        }}
        
        .date {{
            color: #999;
            margin-top: 0.5em;
        }}
        
        a {{
            color: #667eea;
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
        
        @media print {{
            body {{
                background: white;
            }}
            .title-page {{
                page-break-after: always;
            }}
            h2 {{
                page-break-before: always;
            }}
        }}
    </style>
</head>
<body>
    <div class="title-page">
        <h1>{title}</h1>
        <div class="author">by {instructor}</div>
        <div class="date">{datetime.now().strftime("%B %Y")}</div>
    </div>
"""
    
    current_chapter = False
    
    for entry in transcript:
        text = entry.get('text', '').strip()
        if not text:
            continue
        
        # Check for chapters
        if re.search(r'\bchapter\s+\d+\b', text, re.IGNORECASE):
            match = re.search(r'chapter\s+\d+[:\s]*([^.]*)', text, re.IGNORECASE)
            if match:
                chapter_title = match.group(1).strip()
            else:
                chapter_title = text
            html += f"\n<h2>{chapter_title}</h2>\n"
            current_chapter = True
            continue
        
        # Check for sections
        if re.search(r'\bsection\s+[\d.]+\b', text, re.IGNORECASE):
            match = re.search(r'section\s+[\d.]+[:\s]*([^.]*)', text, re.IGNORECASE)
            if match:
                section_title = match.group(1).strip()
            else:
                section_title = text
            html += f"\n<h3>{section_title}</h3>\n"
            continue
        
        # Process text
        processed = processor.convert_math_expressions(text)
        
        # Convert math to HTML
        processed = re.sub(r'\$([^$]+)\$', r'<span class="math">\1</span>', processed)
        
        # Convert URLs
        processed = re.sub(
            r'(https?://[^\s]+)',
            r'<a href="\1" target="_blank">\1</a>',
            processed
        )
        
        # Escape HTML characters
        processed = processed.replace('&', '&amp;')
        processed = processed.replace('<', '&lt;').replace('>', '&gt;')
        # Restore our tags
        processed = processed.replace('&lt;span class="math"&gt;', '<span class="math">')
        processed = processed.replace('&lt;/span&gt;', '</span>')
        processed = processed.replace('&lt;a href=', '<a href=')
        processed = processed.replace('"&gt;', '">')
        processed = processed.replace('&lt;/a&gt;', '</a>')
        
        html += f"<p>{processed}</p>\n"
    
    html += """
</body>
</html>"""
    
    return html

def html_to_pdf_with_weasyprint(html_content):
    """Convert HTML to PDF using WeasyPrint"""
    try:
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes, None
    except Exception as e:
        return None, f"WeasyPrint error: {str(e)}"

def get_demo_json():
    """Get demo JSON data"""
    return {
        "video_title": "Introduction to Machine Learning",
        "instructor": "Prof. Alex Johnson",
        "duration": "1:30:00",
        "transcript": [
            {
                "timestamp": "00:00:00",
                "text": "Welcome to Machine Learning fundamentals. I'm Professor Johnson."
            },
            {
                "timestamp": "00:00:30",
                "text": "Chapter 1: Introduction to Machine Learning. Let's understand what ML is all about."
            },
            {
                "timestamp": "00:01:00",
                "text": "Machine learning is a subset of artificial intelligence where computers learn from data without being explicitly programmed."
            },
            {
                "timestamp": "00:02:00",
                "text": "The basic formula for a linear model is y = mx + b, where m is the slope and b is the intercept."
            },
            {
                "timestamp": "00:03:00",
                "text": "Chapter 2: Types of Machine Learning. There are three main types."
            },
            {
                "timestamp": "00:03:30",
                "text": "First, supervised learning where we have labeled data. The algorithm learns from input-output pairs."
            },
            {
                "timestamp": "00:04:00",
                "text": "The loss function for linear regression is L = sum from i=1 to n of (y_i - y_hat_i)^2"
            },
            {
                "timestamp": "00:05:00",
                "text": "Second, unsupervised learning works with unlabeled data to find hidden patterns."
            },
            {
                "timestamp": "00:06:00",
                "text": "The k-means clustering algorithm minimizes the within-cluster sum of squares."
            },
            {
                "timestamp": "00:07:00",
                "text": "Section 2.1: Deep Learning. Neural networks with multiple hidden layers."
            },
            {
                "timestamp": "00:08:00",
                "text": "The activation function sigmoid(x) = 1/(1 + e^(-x)) introduces non-linearity."
            },
            {
                "timestamp": "00:09:00",
                "text": "The gradient descent update rule is: theta = theta - alpha * gradient where alpha is the learning rate."
            },
            {
                "timestamp": "00:10:00",
                "text": "Chapter 3: Practical Applications. ML is used everywhere today."
            },
            {
                "timestamp": "00:11:00",
                "text": "For more resources, visit https://ml-course.university.edu and check out the TensorFlow documentation at https://tensorflow.org"
            },
            {
                "timestamp": "00:12:00",
                "text": "Remember: The key to mastering ML is practice and understanding the math behind the algorithms."
            }
        ]
    }

def main():
    # Header
    st.markdown("""
    <div class='main-header'>
        <h1 style='color: white; text-align: center; margin: 0;'>📚 Transcript to Book Converter</h1>
        <p style='color: rgba(255,255,255,0.9); text-align: center; margin-top: 0.5rem;'>
        No LaTeX Installation Required - Multiple PDF Generation Methods
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize processor
    processor = TranscriptProcessor()
    
    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")
        
        # API Key
        api_key = st.text_input(
            "🔑 OpenRouter API Key (Optional)",
            type="password",
            help="Enter for AI-powered LaTeX generation"
        )
        
        st.divider()
        
        # PDF Generation Method
        pdf_method = st.selectbox(
            "📖 PDF Generation Method",
            ["ReportLab (No LaTeX needed)", "Online LaTeX Compiler", "HTML to PDF"],
            help="Choose how to generate PDF without local LaTeX installation"
        )
        
        st.divider()
        
        # Input method
        st.markdown("### 📥 Input JSON")
        
        input_method = st.radio(
            "Select input method:",
            ["📁 Upload File", "📝 Paste JSON", "🎯 Use Demo"]
        )
        
        transcript_json = None
        
        if input_method == "📁 Upload File":
            uploaded = st.file_uploader("Choose JSON file", type=['json'])
            if uploaded:
                try:
                    transcript_json = json.load(uploaded)
                    st.success("✅ File loaded!")
                except:
                    st.error("❌ Invalid JSON file")
        
        elif input_method == "📝 Paste JSON":
            json_text = st.text_area("Paste JSON here:", height=300)
            if json_text:
                try:
                    transcript_json = json.loads(json_text)
                    st.success("✅ JSON parsed!")
                except:
                    st.error("❌ Invalid JSON")
        
        else:  # Demo
            if st.button("📥 Load Demo Data", use_container_width=True):
                transcript_json = get_demo_json()
                st.success("✅ Demo loaded!")
        
        st.divider()
        
        # Generation method
        use_ai = st.checkbox("🤖 Use AI for LaTeX", value=bool(api_key))
        
        # Generate button
        if st.button("🚀 Generate Document", type="primary", use_container_width=True):
            if not transcript_json:
                st.error("❌ Please provide input JSON")
            else:
                with st.spinner("⚙️ Generating document..."):
                    # Generate LaTeX
                    if use_ai and api_key:
                        latex, error = call_openrouter_api(transcript_json, api_key)
                        if latex:
                            st.session_state.latex_content = latex
                            st.session_state.generation_method = "AI"
                        else:
                            st.warning(f"AI failed: {error}. Using fallback...")
                            st.session_state.latex_content = create_fallback_latex(transcript_json, processor)
                            st.session_state.generation_method = "Fallback"
                    else:
                        st.session_state.latex_content = create_fallback_latex(transcript_json, processor)
                        st.session_state.generation_method = "Manual"
                    
                    # Generate HTML
                    st.session_state.html_content = create_html_from_transcript(transcript_json, processor)
                    
                    # Generate PDF based on selected method
                    if pdf_method == "ReportLab (No LaTeX needed)":
                        try:
                            pdf_bytes = generate_pdf_with_reportlab(transcript_json)
                            st.session_state.pdf_bytes = pdf_bytes
                            st.success("✅ PDF generated with ReportLab!")
                        except Exception as e:
                            st.error(f"❌ ReportLab error: {str(e)}")
                            st.info("💡 Try: pip install reportlab")
                    
                    elif pdf_method == "Online LaTeX Compiler":
                        pdf_bytes, error = convert_latex_to_pdf_online(st.session_state.latex_content)
                        if pdf_bytes:
                            st.session_state.pdf_bytes = pdf_bytes
                            st.success("✅ PDF generated online!")
                        else:
                            st.error(f"❌ {error}")
                    
                    else:  # HTML to PDF
                        try:
                            # Try WeasyPrint first
                            pdf_bytes, error = html_to_pdf_with_weasyprint(st.session_state.html_content)
                            if pdf_bytes:
                                st.session_state.pdf_bytes = pdf_bytes
                                st.success("✅ PDF generated from HTML!")
                            else:
                                st.error(f"❌ {error}")
                                st.info("💡 Try: pip install weasyprint")
                        except:
                            st.error("WeasyPrint not installed")
                            st.info("💡 Install with: pip install weasyprint")
    
    # Main area
    if st.session_state.latex_content or st.session_state.html_content:
        tab1, tab2, tab3, tab4 = st.tabs(["📄 LaTeX", "🌐 HTML", "📥 Downloads", "ℹ️ Help"])
        
        with tab1:
            if st.session_state.latex_content:
                st.markdown(f"**Generation Method:** {st.session_state.generation_method}")
                st.code(st.session_state.latex_content[:3000] + "\n...[truncated]", language='latex')
        
        with tab2:
            if st.session_state.html_content:
                st.markdown("**HTML Preview:**")
                st.components.v1.html(st.session_state.html_content, height=600, scrolling=True)
        
        with tab3:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.session_state.latex_content:
                    st.download_button(
                        "📄 Download .tex",
                        data=st.session_state.latex_content,
                        file_name=f"book_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tex",
                        mime="text/plain",
                        use_container_width=True
                    )
            
            with col2:
                if st.session_state.html_content:
                    st.download_button(
                        "🌐 Download HTML",
                        data=st.session_state.html_content,
                        file_name=f"book_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                        mime="text/html",
                        use_container_width=True
                    )
            
            with col3:
                if st.session_state.pdf_bytes:
                    st.download_button(
                        "📕 Download PDF",
                        data=st.session_state.pdf_bytes,
                        file_name=f"book_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.info("Generate document first")
        
        with tab4:
            st.markdown("""
            ### 📚 PDF Generation Methods (No LaTeX Required!)
            
            #### Method 1: ReportLab (Recommended)
            ```bash
            pip install reportlab
            ```
            - Pure Python solution
            - No external dependencies
            - Basic formatting
            
            #### Method 2: Online Compiler
            - Uses online LaTeX services
            - No installation needed
            - Requires internet connection
            
            #### Method 3: HTML to PDF
            ```bash
            pip install weasyprint
            # or
            pip install pdfkit
            ```
            - Converts HTML to PDF
            - Good formatting support
            
            ### 🔧 Quick Install All Dependencies:
            ```bash
            pip install streamlit reportlab weasyprint markdown2
            ```
            
            ### 💡 Tips:
            - ReportLab works out of the box
            - Online compiler needs internet
            - WeasyPrint gives best formatting
            """)
    else:
        # Welcome screen
        st.markdown("""
        <div class='info-msg'>
        <h3>✨ No LaTeX Installation Required!</h3>
        <p>This tool can generate PDFs without LaTeX using:</p>
        <ul>
        <li>ReportLab - Pure Python PDF generation</li>
        <li>Online LaTeX compilers</li>
        <li>HTML to PDF conversion</li>
        </ul>
        <p>Just upload your transcript and click Generate!</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Show demo JSON structure
        with st.expander("📋 Expected JSON Format"):
            st.json(get_demo_json())

if __name__ == "__main__":
    main()