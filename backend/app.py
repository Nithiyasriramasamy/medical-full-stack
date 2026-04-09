import os
import re
import json
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
import pytesseract
from PIL import Image
import pdf2image
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from werkzeug.utils import secure_filename
import cv2

# Configure Tesseract path - try to find it dynamically for Linux, use default for Windows
def get_tesseract_path():
    # If environment variable is set (e.g. on Render), use it
    env_path = os.environ.get('TESSERACT_CMD')
    if env_path:
        return env_path
    
    # Common Windows path
    windows_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if os.path.exists(windows_path):
        return windows_path
    
    # On Linux, it's usually in the PATH
    return 'tesseract'

pytesseract.pytesseract.tesseract_cmd = get_tesseract_path()

# Initialize Flask as an API only
app = Flask(__name__)
CORS(app) # Enable Cross-Origin Resource Sharing

# Configure upload folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load reference data
reference_path = os.path.join(BASE_DIR, 'reference_data.csv')
reference_df = pd.read_csv(reference_path)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def preprocess_image(image_path):
    """Enhance image quality for better OCR"""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Apply thresholding
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Denoise
    denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)
    temp_path = image_path.replace('.', '_processed.')
    cv2.imwrite(temp_path, denoised)
    return temp_path

def extract_text_from_image(image_path):
    """Extract text using OCR with preprocessing"""
    processed_path = preprocess_image(image_path)
    img = Image.open(processed_path)
    # Try multiple OCR configurations for better results
    text = pytesseract.image_to_string(img, config='--psm 6')
    if len(text.strip()) < 50:  # If not much text, try different config
        text = pytesseract.image_to_string(img, config='--psm 4')
    # Clean up processed image
    if os.path.exists(processed_path):
        os.remove(processed_path)
    return text

def extract_text_from_pdf(pdf_path):
    """Convert PDF to images and extract text"""
    images = pdf2image.convert_from_path(pdf_path)
    text = ""
    for i, image in enumerate(images):
        temp_image_path = f"{pdf_path}_page_{i}.jpg"
        image.save(temp_image_path, 'JPEG')
        text += extract_text_from_image(temp_image_path)
        os.remove(temp_image_path)
    return text

def extract_medical_values(text):
    """Extract medical test values from OCR text - handles messy OCR"""
    results = []
    
    # Split text into lines for better parsing
    lines = text.split('\n')
    
    # Enhanced patterns that handle OCR errors and look for values on same line
    test_patterns = {
        'Hemoglobin': {
            'keywords': ['hemoglobin', 'haemoglobin', 'hb', 'hgb', 'haemo', 'hemo'],
            'range': (5, 20)
        },
        'WBC': {
            'keywords': ['wbc', 'white', 'leucocyte', 'leukocyte', 'w.b.c'],
            'range': (1000, 20000)
        },
        'RBC': {
            'keywords': ['rbc', 'red blood', 'erythrocyte', 'r.b.c'],
            'range': (2, 7)
        },
        'Platelets': {
            'keywords': ['platelet', 'plt'],
            'range': (50000, 500000)
        },
        'Neutrophils': {
            'keywords': ['neutrophil', 'neutro'],
            'range': (20, 80)
        },
        'Lymphocytes': {
            'keywords': ['lymphocyte', 'lympho', 'litpiocr'],
            'range': (15, 50)
        },
        'Glucose': {
            'keywords': ['glucose', 'sugar', 'fbs', 'rbs'],
            'range': (50, 400)
        },
        'Cholesterol': {
            'keywords': ['cholesterol', 'chol'],
            'range': (100, 400)
        },
        'Hematocrit': {
            'keywords': ['hematocrit', 'haematocrit', 'hct', 'hot'],
            'range': (30, 55)
        },
        'MCV': {
            'keywords': ['mcv', 'mean corpuscular volume', 'mean cell volume'],
            'range': (70, 110)
        },
        'MCH': {
            'keywords': ['mch', 'mean cell haemoglobin', 'mean cell hemoglobin'],
            'range': (20, 35)
        },
        'MCHC': {
            'keywords': ['mchc', 'mean cell haemoglobin con', 'waeoglogin'],
            'range': (30, 37)
        }
    }
    
    text_lower = text.lower()
    
    # Try to find values for each test
    for test_name, config in test_patterns.items():
        keywords = config['keywords']
        min_val, max_val = config['range']
        
        for keyword in keywords:
            # Look for the keyword in text
            if keyword in text_lower:
                # Find the position of keyword
                idx = text_lower.find(keyword)
                # Get surrounding text (100 chars after keyword)
                context = text_lower[idx:idx+100]
                
                # Extract all numbers from context
                numbers = re.findall(r'\b(\d+\.?\d*)\b', context)
                
                # Find first number in valid range
                for num_str in numbers:
                    try:
                        value = float(num_str)
                        if min_val <= value <= max_val:
                            results.append({'test': test_name, 'value': value})
                            break
                    except ValueError:
                        continue
                
                if any(r['test'] == test_name for r in results):
                    break  # Found value for this test
    
    return results

def compare_with_reference(extracted_values):
    """Compare extracted values with reference ranges"""
    comparison_results = []
    
    for item in extracted_values:
        test_name = item['test']
        value = item['value']
        
        ref_row = reference_df[reference_df['Test_Name'] == test_name]
        
        if not ref_row.empty:
            min_val = ref_row['Min_Value'].values[0]
            max_val = ref_row['Max_Value'].values[0]
            unit = ref_row['Unit'].values[0]
            description = ref_row['Description'].values[0]
            
            if value < min_val:
                status = 'Low'
                color = '#3498db'
            elif value > max_val:
                status = 'High'
                color = '#e74c3c'
            else:
                status = 'Normal'
                color = '#2ecc71'
            
            comparison_results.append({
                'test': test_name,
                'value': value,
                'min': min_val,
                'max': max_val,
                'unit': unit,
                'status': status,
                'color': color,
                'description': description
            })
    
    return comparison_results

def generate_insights(comparison_results):
    """Generate AI-like health insights"""
    insights = []
    
    insight_templates = {
        'Hemoglobin': {
            'Low': 'Your hemoglobin is below normal range, which may indicate anemia. Consider iron-rich foods and consult a doctor.',
            'High': 'Your hemoglobin is elevated, which could be due to dehydration or other conditions. Stay hydrated and consult a doctor.',
            'Normal': 'Your hemoglobin level is within the healthy range.'
        },
        'WBC': {
            'Low': 'Your white blood cell count is low, which may weaken your immune system. Consult a doctor.',
            'High': 'Your WBC count is higher than normal, possibly indicating infection, inflammation, or stress. Medical evaluation recommended.',
            'Normal': 'Your white blood cell count is healthy.'
        },
        'Platelets': {
            'Low': 'Your platelet count is low, which may affect blood clotting. Consult a doctor.',
            'High': 'Your platelet count is elevated. This may need medical evaluation.',
            'Normal': 'Your platelet count is within normal range.'
        },
        'Neutrophils': {
            'Low': 'Your neutrophil percentage is low, which may affect infection fighting ability.',
            'High': 'Your neutrophil percentage is elevated, possibly indicating infection or inflammation.',
            'Normal': 'Your neutrophil levels are normal.'
        },
        'Lymphocytes': {
            'Low': 'Your lymphocyte percentage is low, which may affect immune function.',
            'High': 'Your lymphocyte percentage is elevated, which may indicate viral infection or immune response.',
            'Normal': 'Your lymphocyte levels are normal.'
        },
        'Glucose': {
            'Low': 'Your blood sugar is low. Ensure regular meals and monitor for hypoglycemia symptoms.',
            'High': 'Your glucose level is elevated. This may indicate prediabetes or diabetes risk. Consult a doctor for further testing.',
            'Normal': 'Your blood sugar level is within the healthy range.'
        },
        'Cholesterol': {
            'Low': 'Your cholesterol is low, which is generally good, but extremely low levels may need evaluation.',
            'High': 'Your cholesterol is elevated, increasing cardiovascular risk. Consider dietary changes and exercise.',
            'Normal': 'Your cholesterol level is healthy.'
        },
        'Creatinine': {
            'Low': 'Your creatinine is low, which is usually not a concern but may indicate low muscle mass.',
            'High': 'Elevated creatinine may indicate kidney function issues. Consult a doctor for kidney function tests.',
            'Normal': 'Your kidney function markers are normal.'
        },
        'Hematocrit': {
            'Low': 'Your hematocrit is low, which may indicate anemia or blood loss.',
            'High': 'Your hematocrit is elevated, which may indicate dehydration or polycythemia.',
            'Normal': 'Your hematocrit level is normal.'
        },
        'MCV': {
            'Low': 'Your MCV is low, suggesting smaller red blood cells (microcytic anemia).',
            'High': 'Your MCV is elevated, suggesting larger red blood cells (macrocytic anemia).',
            'Normal': 'Your red blood cell size is normal.'
        },
        'MCH': {
            'Low': 'Your MCH is low, which may indicate iron deficiency.',
            'High': 'Your MCH is elevated, which may need further evaluation.',
            'Normal': 'Your MCH level is normal.'
        },
        'MCHC': {
            'Low': 'Your MCHC is low, which may indicate iron deficiency anemia.',
            'High': 'Your MCHC is elevated, which is rare and may need evaluation.',
            'Normal': 'Your MCHC level is normal.'
        }
    }
    
    for result in comparison_results:
        test = result['test']
        status = result['status']
        
        if test in insight_templates:
            insight = insight_templates[test].get(status, f'Your {test} is {status.lower()}.')
        else:
            if status == 'Low':
                insight = f'Your {test} is below the normal range. Consult a healthcare provider.'
            elif status == 'High':
                insight = f'Your {test} is above the normal range. Medical consultation recommended.'
            else:
                insight = f'Your {test} is within the normal range.'
        
        insights.append({
            'test': test,
            'insight': insight,
            'status': status
        })
    
    return insights

def create_visualization(comparison_results):
    """Create interactive Plotly visualizations"""
    if not comparison_results:
        return None
    
    charts = {}
    
    # 1. Bar Chart with Range Indicators
    fig_bar = go.Figure()
    
    tests = [r['test'] for r in comparison_results]
    values = [r['value'] for r in comparison_results]
    colors = [r['color'] for r in comparison_results]
    min_vals = [r['min'] for r in comparison_results]
    max_vals = [r['max'] for r in comparison_results]
    
    fig_bar.add_trace(go.Bar(
        x=tests,
        y=values,
        marker_color=colors,
        text=[f"{v} {r['unit']}" for v, r in zip(values, comparison_results)],
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>Value: %{y}<br>Normal: %{customdata[0]} - %{customdata[1]}<extra></extra>',
        customdata=list(zip(min_vals, max_vals)),
        name='Your Value'
    ))
    
    fig_bar.update_layout(
        title='Medical Test Results Overview',
        xaxis_title='Test Name',
        yaxis_title='Value',
        template='plotly_white',
        height=450,
        showlegend=False,
        xaxis={'tickangle': -45}
    )
    
    charts['bar'] = fig_bar.to_json()
    
    # 2. Gauge Charts for each test
    gauges = []
    for result in comparison_results[:6]:  # First 6 tests
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=result['value'],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"{result['test']}<br><span style='font-size:0.8em'>{result['unit']}</span>"},
            delta={'reference': (result['min'] + result['max']) / 2},
            gauge={
                'axis': {'range': [None, result['max'] * 1.2]},
                'bar': {'color': result['color']},
                'steps': [
                    {'range': [0, result['min']], 'color': "lightblue"},
                    {'range': [result['min'], result['max']], 'color': "lightgreen"},
                    {'range': [result['max'], result['max'] * 1.2], 'color': "lightcoral"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': result['max']
                }
            }
        ))
        
        fig_gauge.update_layout(
            height=250,
            margin={'t': 50, 'b': 0, 'l': 0, 'r': 0}
        )
        
        gauges.append(fig_gauge.to_json())
    
    charts['gauges'] = gauges
    
    # 3. Status Distribution Pie Chart
    status_counts = {}
    for result in comparison_results:
        status = result['status']
        status_counts[status] = status_counts.get(status, 0) + 1
    
    fig_pie = go.Figure(data=[go.Pie(
        labels=list(status_counts.keys()),
        values=list(status_counts.values()),
        marker=dict(colors=['#2ecc71', '#e74c3c', '#3498db']),
        hole=0.4,
        textinfo='label+percent',
        hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>'
    )])
    
    fig_pie.update_layout(
        title='Health Status Distribution',
        height=350,
        showlegend=True
    )
    
    charts['pie'] = fig_pie.to_json()
    
    # 4. Radar/Spider Chart - Normalized values
    fig_radar = go.Figure()
    
    # Normalize values to percentage of normal range
    normalized_values = []
    for result in comparison_results[:8]:  # Limit to 8 for readability
        mid_point = (result['min'] + result['max']) / 2
        normalized = (result['value'] / mid_point) * 100
        normalized_values.append(normalized)
    
    radar_tests = [r['test'] for r in comparison_results[:8]]
    
    fig_radar.add_trace(go.Scatterpolar(
        r=normalized_values,
        theta=radar_tests,
        fill='toself',
        name='Your Results',
        line=dict(color='#667eea', width=2),
        fillcolor='rgba(102, 126, 234, 0.3)'
    ))
    
    # Add reference line at 100%
    fig_radar.add_trace(go.Scatterpolar(
        r=[100] * len(radar_tests),
        theta=radar_tests,
        name='Normal Range',
        line=dict(color='#2ecc71', width=2, dash='dash')
    ))
    
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 150],
                ticksuffix='%'
            )
        ),
        showlegend=True,
        title='Health Parameters Radar View',
        height=500
    )
    
    charts['radar'] = fig_radar.to_json()
    
    # 5. Simulated Trend Chart (Historical comparison)
    fig_trend = go.Figure()
    
    # Simulate 6 months of data
    months = ['6 months ago', '5 months ago', '4 months ago', '3 months ago', '2 months ago', 'Last month', 'Current']
    
    for i, result in enumerate(comparison_results[:4]):  # Show trends for first 4 tests
        # Generate simulated historical data with some variation
        base_value = result['value']
        historical_values = []
        for j in range(6):
            variation = np.random.uniform(-0.15, 0.15)
            historical_values.append(base_value * (1 + variation))
        historical_values.append(result['value'])
        
        fig_trend.add_trace(go.Scatter(
            x=months,
            y=historical_values,
            mode='lines+markers',
            name=result['test'],
            line=dict(width=3),
            marker=dict(size=8),
            hovertemplate='<b>%{fullData.name}</b><br>%{x}<br>Value: %{y:.2f}<extra></extra>'
        ))
        
        # Add reference range bands
        fig_trend.add_trace(go.Scatter(
            x=months,
            y=[result['max']] * len(months),
            mode='lines',
            name=f'{result["test"]} Max',
            line=dict(color=result['color'], width=1, dash='dash'),
            showlegend=False,
            hoverinfo='skip'
        ))
        
        fig_trend.add_trace(go.Scatter(
            x=months,
            y=[result['min']] * len(months),
            mode='lines',
            name=f'{result["test"]} Min',
            line=dict(color=result['color'], width=1, dash='dash'),
            fill='tonexty',
            fillcolor=f'rgba({int(result["color"][1:3], 16)}, {int(result["color"][3:5], 16)}, {int(result["color"][5:7], 16)}, 0.1)',
            showlegend=False,
            hoverinfo='skip'
        ))
    
    fig_trend.update_layout(
        title='Simulated Health Trends Over Time',
        xaxis_title='Time Period',
        yaxis_title='Value',
        template='plotly_white',
        height=450,
        hovermode='x unified'
    )
    
    charts['trend'] = fig_trend.to_json()
    
    # 6. Box Plot - Distribution Analysis
    fig_box = go.Figure()
    
    for result in comparison_results[:6]:
        # Generate sample distribution around the value
        samples = np.random.normal(result['value'], result['value'] * 0.1, 100)
        
        fig_box.add_trace(go.Box(
            y=samples,
            name=result['test'],
            marker_color=result['color'],
            boxmean='sd',
            hovertemplate='<b>%{fullData.name}</b><br>Value: %{y:.2f}<extra></extra>'
        ))
    
    fig_box.update_layout(
        title='Test Results Distribution Analysis',
        yaxis_title='Value',
        template='plotly_white',
        height=450,
        showlegend=False
    )
    
    charts['box'] = fig_box.to_json()
    
    # 7. Heatmap - Correlation Matrix (simulated)
    if len(comparison_results) >= 4:
        test_names = [r['test'] for r in comparison_results[:6]]
        n = len(test_names)
        
        # Generate simulated correlation matrix
        correlation_matrix = np.random.rand(n, n)
        correlation_matrix = (correlation_matrix + correlation_matrix.T) / 2
        np.fill_diagonal(correlation_matrix, 1)
        
        fig_heatmap = go.Figure(data=go.Heatmap(
            z=correlation_matrix,
            x=test_names,
            y=test_names,
            colorscale='RdYlGn',
            zmid=0.5,
            text=np.round(correlation_matrix, 2),
            texttemplate='%{text}',
            textfont={"size": 10},
            hovertemplate='%{x} vs %{y}<br>Correlation: %{z:.2f}<extra></extra>'
        ))
        
        fig_heatmap.update_layout(
            title='Test Parameters Correlation Matrix',
            height=450,
            xaxis={'tickangle': -45}
        )
        
        charts['heatmap'] = fig_heatmap.to_json()
    
    # 8. 3D Scatter Plot (for first 3 tests with sufficient data)
    if len(comparison_results) >= 3:
        fig_3d = go.Figure(data=[go.Scatter3d(
            x=[comparison_results[0]['value']],
            y=[comparison_results[1]['value']],
            z=[comparison_results[2]['value']],
            mode='markers',
            marker=dict(
                size=20,
                color='#667eea',
                symbol='diamond',
                line=dict(color='white', width=2)
            ),
            text=['Your Results'],
            hovertemplate=f'<b>Your Results</b><br>{comparison_results[0]["test"]}: %{{x}}<br>{comparison_results[1]["test"]}: %{{y}}<br>{comparison_results[2]["test"]}: %{{z}}<extra></extra>',
            name='Your Results'
        )])
        
        # Add reference point (midpoint of normal ranges)
        fig_3d.add_trace(go.Scatter3d(
            x=[(comparison_results[0]['min'] + comparison_results[0]['max']) / 2],
            y=[(comparison_results[1]['min'] + comparison_results[1]['max']) / 2],
            z=[(comparison_results[2]['min'] + comparison_results[2]['max']) / 2],
            mode='markers',
            marker=dict(
                size=15,
                color='#2ecc71',
                symbol='circle',
                line=dict(color='white', width=2)
            ),
            text=['Normal Range Center'],
            hovertemplate='<b>Normal Range Center</b><extra></extra>',
            name='Normal Center'
        ))
        
        fig_3d.update_layout(
            title='3D Health Parameters Visualization',
            scene=dict(
                xaxis_title=comparison_results[0]['test'],
                yaxis_title=comparison_results[1]['test'],
                zaxis_title=comparison_results[2]['test']
            ),
            height=500
        )
        
        charts['scatter3d'] = fig_3d.to_json()
    
    # 9. Waterfall Chart - Show deviation from normal
    fig_waterfall = go.Figure()
    
    waterfall_tests = []
    waterfall_values = []
    waterfall_colors = []
    
    for result in comparison_results[:6]:
        mid_point = (result['min'] + result['max']) / 2
        deviation = result['value'] - mid_point
        waterfall_tests.append(result['test'])
        waterfall_values.append(deviation)
        waterfall_colors.append(result['color'])
    
    fig_waterfall.add_trace(go.Waterfall(
        name='Deviation',
        orientation='v',
        x=waterfall_tests,
        y=waterfall_values,
        connector={'line': {'color': 'rgb(63, 63, 63)'}},
        decreasing={'marker': {'color': '#3498db'}},
        increasing={'marker': {'color': '#e74c3c'}},
        totals={'marker': {'color': '#667eea'}},
        hovertemplate='<b>%{x}</b><br>Deviation: %{y:.2f}<extra></extra>'
    ))
    
    fig_waterfall.update_layout(
        title='Deviation from Normal Range Midpoint',
        xaxis_title='Test Name',
        yaxis_title='Deviation',
        template='plotly_white',
        height=450,
        showlegend=False,
        xaxis={'tickangle': -45}
    )
    
    charts['waterfall'] = fig_waterfall.to_json()
    
    # 10. Funnel Chart - Health Status Breakdown
    status_counts = {}
    for result in comparison_results:
        status = result['status']
        status_counts[status] = status_counts.get(status, 0) + 1
    
    fig_funnel = go.Figure()
    
    funnel_data = [
        ('Total Tests', len(comparison_results)),
        ('Normal', status_counts.get('Normal', 0)),
        ('Needs Attention', status_counts.get('High', 0) + status_counts.get('Low', 0))
    ]
    
    fig_funnel.add_trace(go.Funnel(
        y=[item[0] for item in funnel_data],
        x=[item[1] for item in funnel_data],
        textposition='inside',
        textinfo='value+percent initial',
        marker={'color': ['#667eea', '#2ecc71', '#e74c3c']},
        connector={'line': {'color': 'royalblue', 'dash': 'dot', 'width': 3}},
        hovertemplate='<b>%{y}</b><br>Count: %{x}<extra></extra>'
    ))
    
    fig_funnel.update_layout(
        title='Health Status Funnel',
        height=400
    )
    
    charts['funnel'] = fig_funnel.to_json()
    
    # 11. Polar Bar Chart - Circular comparison
    fig_polar = go.Figure()
    
    polar_tests = [r['test'] for r in comparison_results[:8]]
    polar_values = []
    polar_colors = [r['color'] for r in comparison_results[:8]]
    
    for result in comparison_results[:8]:
        # Normalize to percentage of max range
        percentage = (result['value'] / (result['max'] * 1.2)) * 100
        polar_values.append(percentage)
    
    fig_polar.add_trace(go.Barpolar(
        r=polar_values,
        theta=polar_tests,
        marker=dict(
            color=polar_colors,
            line=dict(color='white', width=2)
        ),
        hovertemplate='<b>%{theta}</b><br>%{r:.1f}%<extra></extra>',
        name='Test Values'
    ))
    
    fig_polar.update_layout(
        title='Circular Test Comparison',
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                ticksuffix='%'
            ),
            angularaxis=dict(
                direction='clockwise'
            )
        ),
        height=500,
        showlegend=False
    )
    
    charts['polar'] = fig_polar.to_json()
    
    # 12. Sunburst Chart - Hierarchical view
    sunburst_data = {
        'labels': ['All Tests'],
        'parents': [''],
        'values': [len(comparison_results)],
        'colors': ['#667eea']
    }
    
    # Add status categories
    for status in ['Normal', 'High', 'Low']:
        count = sum(1 for r in comparison_results if r['status'] == status)
        if count > 0:
            sunburst_data['labels'].append(status)
            sunburst_data['parents'].append('All Tests')
            sunburst_data['values'].append(count)
            color = '#2ecc71' if status == 'Normal' else ('#e74c3c' if status == 'High' else '#3498db')
            sunburst_data['colors'].append(color)
            
            # Add individual tests
            for result in comparison_results:
                if result['status'] == status:
                    sunburst_data['labels'].append(result['test'])
                    sunburst_data['parents'].append(status)
                    sunburst_data['values'].append(1)
                    sunburst_data['colors'].append(result['color'])
    
    fig_sunburst = go.Figure(go.Sunburst(
        labels=sunburst_data['labels'],
        parents=sunburst_data['parents'],
        values=sunburst_data['values'],
        marker=dict(colors=sunburst_data['colors']),
        branchvalues='total',
        hovertemplate='<b>%{label}</b><br>Count: %{value}<extra></extra>'
    ))
    
    fig_sunburst.update_layout(
        title='Hierarchical Test Results View',
        height=500
    )
    
    charts['sunburst'] = fig_sunburst.to_json()
    
    # 13. Violin Plot - Distribution with statistics
    fig_violin = go.Figure()
    
    for result in comparison_results[:6]:
        # Generate sample distribution
        samples = np.random.normal(result['value'], result['value'] * 0.08, 100)
        
        fig_violin.add_trace(go.Violin(
            y=samples,
            name=result['test'],
            box_visible=True,
            meanline_visible=True,
            fillcolor=result['color'],
            opacity=0.6,
            x0=result['test'],
            hovertemplate='<b>%{fullData.name}</b><br>Value: %{y:.2f}<extra></extra>'
        ))
    
    fig_violin.update_layout(
        title='Test Results Distribution (Violin Plot)',
        yaxis_title='Value',
        template='plotly_white',
        height=450,
        showlegend=False
    )
    
    charts['violin'] = fig_violin.to_json()
    
    # 14. Indicator/KPI Cards
    kpi_charts = []
    for result in comparison_results[:4]:
        fig_kpi = go.Figure()
        
        # Calculate percentage of normal range
        mid_point = (result['min'] + result['max']) / 2
        percentage = (result['value'] / mid_point) * 100
        
        fig_kpi.add_trace(go.Indicator(
            mode='number+delta+gauge',
            value=result['value'],
            title={'text': f"{result['test']}<br><span style='font-size:0.8em'>{result['unit']}</span>"},
            delta={
                'reference': mid_point,
                'relative': False,
                'valueformat': '.2f'
            },
            gauge={
                'shape': 'bullet',
                'axis': {'range': [None, result['max'] * 1.2]},
                'threshold': {
                    'line': {'color': result['color'], 'width': 2},
                    'thickness': 0.75,
                    'value': result['value']
                },
                'steps': [
                    {'range': [0, result['min']], 'color': 'lightblue'},
                    {'range': [result['min'], result['max']], 'color': 'lightgreen'},
                    {'range': [result['max'], result['max'] * 1.2], 'color': 'lightcoral'}
                ],
                'bar': {'color': result['color']}
            },
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        
        fig_kpi.update_layout(
            height=150,
            margin={'t': 40, 'b': 0, 'l': 0, 'r': 0}
        )
        
        kpi_charts.append(fig_kpi.to_json())
    
    charts['kpi'] = kpi_charts
    
    # 15. Sankey Diagram - Flow from status to tests
    sankey_labels = ['All Tests', 'Normal', 'High', 'Low']
    sankey_sources = []
    sankey_targets = []
    sankey_values = []
    sankey_colors = []
    
    status_indices = {'Normal': 1, 'High': 2, 'Low': 3}
    
    for status, index in status_indices.items():
        count = sum(1 for r in comparison_results if r['status'] == status)
        if count > 0:
            sankey_sources.append(0)
            sankey_targets.append(index)
            sankey_values.append(count)
            color = 'rgba(46, 204, 113, 0.4)' if status == 'Normal' else ('rgba(231, 76, 60, 0.4)' if status == 'High' else 'rgba(52, 152, 219, 0.4)')
            sankey_colors.append(color)
    
    fig_sankey = go.Figure(go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color='black', width=0.5),
            label=sankey_labels,
            color=['#667eea', '#2ecc71', '#e74c3c', '#3498db']
        ),
        link=dict(
            source=sankey_sources,
            target=sankey_targets,
            value=sankey_values,
            color=sankey_colors
        )
    ))
    
    fig_sankey.update_layout(
        title='Test Results Flow Diagram',
        height=400
    )
    
    charts['sankey'] = fig_sankey.to_json()
    
    return charts

@app.route('/')
def api_status():
    return jsonify({
        'status': 'online',
        'message': 'Medical Analysis API is running',
        'endpoints': {
            'analyze': '/analyze (POST)',
            'chat': '/chat (POST)'
        }
    })


@app.route('/chat', methods=['POST'])
def chat():
    """Handle chatbot queries about medical reports"""
    try:
        data = request.json
        question = data.get('question', '').lower()
        report_data = data.get('report_data', None)
        
        # Generate AI-like responses based on question
        response = generate_chat_response(question, report_data)
        
        return jsonify({
            'success': True,
            'response': response
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_chat_response(question, report_data):
    """Generate intelligent responses to user questions"""
    
    # Enhanced knowledge base with comprehensive information
    knowledge_base = {
        'hemoglobin': {
            'what': '''🔴 **Hemoglobin (Hb)** is a crucial protein found in red blood cells that carries oxygen from your lungs to all parts of your body and returns carbon dioxide back to your lungs.

**Key Functions:**
• Oxygen transport throughout the body
• Gives blood its red color
• Essential for cellular energy production
• Maintains acid-base balance

**Normal Ranges:**
• Men: 14-18 g/dL
• Women: 12-16 g/dL
• Children: 11-13 g/dL''',
            
            'low': '''⚠️ **Low Hemoglobin (Anemia)** means your blood isn't carrying enough oxygen to your body's tissues.

**Common Symptoms:**
• Persistent fatigue and weakness
• Pale skin and nail beds
• Shortness of breath
• Dizziness or lightheadedness
• Cold hands and feet
• Rapid or irregular heartbeat

**Possible Causes:**
• Iron deficiency (most common)
• Vitamin B12 or folate deficiency
• Chronic diseases (kidney disease, cancer)
• Blood loss (menstruation, ulcers)
• Bone marrow problems
• Inherited conditions (sickle cell, thalassemia)

**When to See a Doctor:**
Consult immediately if you experience severe fatigue, chest pain, or difficulty breathing.''',
            
            'high': '''📈 **High Hemoglobin** means you have more red blood cells than normal, which can make your blood thicker.

**Possible Causes:**
• Dehydration (most common - easily fixed!)
• Living at high altitude
• Smoking
• Lung diseases (COPD, pulmonary fibrosis)
• Heart disease
• Polycythemia vera (rare blood disorder)
• Use of performance-enhancing drugs

**Potential Risks:**
• Increased blood viscosity
• Higher risk of blood clots
• Stroke or heart attack risk

**Immediate Actions:**
• Stay well-hydrated
• Avoid smoking
• Monitor oxygen levels
• Consult your doctor for proper evaluation''',
            
            'improve': '''💪 **How to Improve Hemoglobin Naturally:**

**Iron-Rich Foods (Best Sources):**
• Red meat, liver, and organ meats
• Shellfish (oysters, clams)
• Dark leafy greens (spinach, kale)
• Legumes (lentils, chickpeas, beans)
• Fortified cereals and bread
• Pumpkin seeds and quinoa

**Vitamin C (Enhances Iron Absorption):**
• Citrus fruits (oranges, lemons)
• Bell peppers and tomatoes
• Strawberries and kiwi
• Broccoli and Brussels sprouts
💡 Tip: Combine iron-rich foods with vitamin C!

**Essential Vitamins:**
• Vitamin B12: Eggs, dairy, fish, fortified foods
• Folate: Leafy greens, beans, citrus fruits
• Vitamin B6: Poultry, fish, potatoes, bananas

**Lifestyle Changes:**
• Avoid tea/coffee with meals (blocks iron absorption)
• Cook in cast iron cookware
• Consider iron supplements (consult doctor first)
• Exercise regularly to stimulate RBC production
• Get adequate sleep (7-9 hours)

**Foods to Limit:**
• Calcium-rich foods during iron-rich meals
• Excessive dairy products
• High-fiber foods with iron supplements'''
        },
        
        'wbc': {
            'what': '''🛡️ **White Blood Cells (WBC)** are your body's defense army, protecting you against infections, diseases, and foreign invaders.

**Types of WBC:**
• Neutrophils (60-70%): Fight bacterial infections
• Lymphocytes (20-40%): Produce antibodies, fight viruses
• Monocytes (2-8%): Clean up dead cells
• Eosinophils (1-4%): Combat parasites, allergies
• Basophils (<1%): Release histamine in allergic reactions

**Normal Range:** 4,000-11,000 cells/μL

**Functions:**
• Identify and destroy pathogens
• Produce antibodies
• Remove dead or damaged cells
• Trigger inflammatory responses''',
            
            'low': '''⚠️ **Low WBC Count (Leukopenia)** weakens your immune system, making you more susceptible to infections.

**Common Causes:**
• Viral infections (flu, HIV, hepatitis)
• Autoimmune disorders (lupus, rheumatoid arthritis)
• Bone marrow disorders
• Medications (chemotherapy, antibiotics, antipsychotics)
• Nutritional deficiencies (B12, folate, copper, zinc)
• Severe infections (sepsis)
• Radiation therapy

**Symptoms to Watch:**
• Frequent infections
• Fever and chills
• Mouth sores
• Skin infections
• Fatigue and weakness
• Swollen lymph nodes

**Precautions:**
• Practice excellent hand hygiene
• Avoid sick people and crowds
• Cook food thoroughly
• Avoid raw or undercooked foods
• Stay up-to-date with vaccinations
• Report fever >100.4°F immediately''',
            
            'high': '''📈 **High WBC Count (Leukocytosis)** usually indicates your body is fighting something.

**Common Causes:**
• Bacterial or viral infections
• Inflammation or tissue damage
• Allergic reactions
• Physical or emotional stress
• Smoking
• Medications (corticosteroids, epinephrine)
• Bone marrow disorders
• Leukemia (rare, but requires evaluation)

**Types of Elevation:**
• Neutrophilia: Bacterial infection, inflammation
• Lymphocytosis: Viral infection, chronic inflammation
• Monocytosis: Chronic infections, autoimmune
• Eosinophilia: Allergies, parasites
• Basophilia: Rare, may indicate blood disorders

**When to Worry:**
• Persistent elevation without clear cause
• Very high counts (>25,000)
• Accompanied by fever, night sweats, weight loss
• Unexplained bruising or bleeding

**Next Steps:**
• Identify and treat underlying infection
• Manage stress levels
• Quit smoking if applicable
• Follow up with complete blood count (CBC)''',
            
            'improve': '''💪 **How to Support Healthy WBC Count:**

**Immune-Boosting Foods:**
• Citrus fruits (vitamin C)
• Red bell peppers (highest vitamin C)
• Garlic and ginger (antimicrobial)
• Yogurt and kefir (probiotics)
• Almonds and sunflower seeds (vitamin E)
• Turmeric (anti-inflammatory)
• Green tea (antioxidants)
• Fatty fish (omega-3s)

**Essential Nutrients:**
• Vitamin C: 75-90mg daily
• Vitamin E: 15mg daily
• Vitamin B6: 1.3-1.7mg daily
• Vitamin B12: 2.4mcg daily
• Folate: 400mcg daily
• Zinc: 8-11mg daily
• Selenium: 55mcg daily

**Lifestyle Strategies:**
• Get 7-9 hours of quality sleep
• Exercise regularly (moderate intensity)
• Manage stress (meditation, yoga)
• Stay hydrated (8-10 glasses water)
• Avoid smoking and excessive alcohol
• Maintain healthy weight
• Practice good hygiene

**Supplements (Consult Doctor):**
• Multivitamin with minerals
• Vitamin D (if deficient)
• Probiotics for gut health
• Omega-3 fatty acids'''
        },
        
        'glucose': {
            'what': '''🍬 **Blood Glucose (Blood Sugar)** is your body's primary energy source, fueling every cell, tissue, and organ.

**How It Works:**
• Comes from food you eat (carbohydrates)
• Insulin helps cells absorb glucose
• Liver stores excess as glycogen
• Released when energy is needed

**Normal Ranges:**
• Fasting: 70-100 mg/dL (ideal)
• 2 hours after eating: <140 mg/dL
• Random: <200 mg/dL
• HbA1c: <5.7% (3-month average)

**Prediabetes:**
• Fasting: 100-125 mg/dL
• HbA1c: 5.7-6.4%

**Diabetes:**
• Fasting: ≥126 mg/dL
• HbA1c: ≥6.5%''',
            
            'low': '''⚠️ **Low Blood Sugar (Hypoglycemia)** occurs when glucose drops below 70 mg/dL.

**Immediate Symptoms (Act Fast!):**
• Shakiness and trembling
• Sweating and chills
• Rapid heartbeat
• Dizziness or lightheadedness
• Hunger and nausea
• Irritability or confusion
• Blurred vision
• Weakness and fatigue

**Severe Symptoms (Emergency!):**
• Confusion or unusual behavior
• Seizures
• Loss of consciousness
• Inability to eat or drink

**Common Causes:**
• Skipping meals or eating too little
• Too much insulin or diabetes medication
• Excessive exercise without eating
• Drinking alcohol without food
• Certain medications

**Immediate Treatment (Rule of 15):**
1. Consume 15g fast-acting carbs:
   • 4 glucose tablets
   • 1/2 cup fruit juice
   • 1 tablespoon honey
   • 3-4 hard candies
2. Wait 15 minutes
3. Recheck blood sugar
4. Repeat if still <70 mg/dL
5. Eat a meal or snack once stable

**Prevention:**
• Eat regular, balanced meals
• Don't skip breakfast
• Carry glucose tablets
• Monitor blood sugar if diabetic
• Adjust medication with doctor's guidance''',
            
            'high': '''📈 **High Blood Sugar (Hyperglycemia)** indicates your body isn't processing glucose effectively.

**Symptoms (May Develop Gradually):**
• Increased thirst and dry mouth
• Frequent urination (especially at night)
• Fatigue and weakness
• Blurred vision
• Headaches
• Slow-healing wounds
• Frequent infections
• Unexplained weight loss
• Tingling in hands/feet

**Serious Complications (Long-term):**
• Heart disease and stroke
• Kidney damage (nephropathy)
• Eye damage (retinopathy, blindness)
• Nerve damage (neuropathy)
• Foot problems (poor circulation)
• Skin conditions
• Alzheimer's disease risk

**Common Causes:**
• Insulin resistance (prediabetes/diabetes)
• Poor diet (high sugar, refined carbs)
• Lack of physical activity
• Obesity
• Stress (raises cortisol)
• Certain medications (steroids)
• Illness or infection
• Hormonal changes

**Immediate Actions:**
• Drink plenty of water
• Avoid sugary foods and drinks
• Take prescribed medication
• Light exercise (if not too high)
• Monitor blood sugar regularly
• Seek medical help if >300 mg/dL''',
            
            'improve': '''💪 **How to Manage Blood Sugar Naturally:**

**Best Foods for Blood Sugar Control:**
• Non-starchy vegetables (unlimited!)
• Leafy greens (spinach, kale, lettuce)
• Whole grains (oats, quinoa, brown rice)
• Legumes (beans, lentils, chickpeas)
• Nuts and seeds (almonds, chia, flax)
• Fatty fish (salmon, mackerel, sardines)
• Lean proteins (chicken, turkey, tofu)
• Berries (blueberries, strawberries)
• Cinnamon (helps insulin sensitivity)
• Apple cider vinegar (before meals)

**Foods to Avoid/Limit:**
• Sugary drinks (soda, juice, sweet tea)
• White bread, pasta, rice
• Pastries, cookies, cakes
• Candy and sweets
• Processed snacks
• Fried foods
• High-sugar fruits (watermelon, pineapple)

**Eating Strategies:**
• Eat smaller, frequent meals (5-6 times/day)
• Never skip breakfast
• Combine carbs with protein/fat
• Use the plate method: 1/2 veggies, 1/4 protein, 1/4 carbs
• Eat fiber-rich foods (25-30g daily)
• Stay hydrated (water only)

**Lifestyle Changes:**
• Exercise 150 min/week (walking, swimming)
• Lose 5-10% body weight if overweight
• Get 7-9 hours quality sleep
• Manage stress (meditation, yoga)
• Quit smoking
• Limit alcohol
• Monitor blood sugar regularly

**Supplements (Consult Doctor):**
• Chromium picolinate
• Alpha-lipoic acid
• Berberine
• Magnesium
• Vitamin D
• Cinnamon extract'''
        },
        
        'cholesterol': {
            'what': '''💛 **Cholesterol** is a waxy, fat-like substance essential for building cells, producing hormones, and making vitamin D.

**Types of Cholesterol:**
• LDL ("Bad"): Builds up in arteries, causes blockages
• HDL ("Good"): Removes LDL from arteries
• VLDL: Carries triglycerides
• Total Cholesterol: Sum of all types

**Optimal Levels:**
• Total Cholesterol: <200 mg/dL
• LDL: <100 mg/dL (optimal), <70 (very high risk)
• HDL: >60 mg/dL (protective)
• Triglycerides: <150 mg/dL
• Total/HDL Ratio: <3.5

**Why It Matters:**
• Essential for cell membranes
• Produces hormones (testosterone, estrogen, cortisol)
• Makes bile acids for digestion
• Synthesizes vitamin D
• But too much LDL = heart disease risk!''',
            
            'low': '''📉 **Low Cholesterol** is rare but can occur.

**Possible Causes:**
• Malnutrition or malabsorption
• Hyperthyroidism
• Liver disease
• Certain medications (statins overdose)
• Genetic disorders
• Chronic infections

**Potential Issues:**
• Hormone imbalances
• Vitamin D deficiency
• Depression or mood changes
• Weakened immune system
• Digestive problems

**When to Worry:**
• Total cholesterol <120 mg/dL
• Accompanied by symptoms
• Sudden drop from previous levels

**What to Do:**
• Eat healthy fats (avocados, nuts, olive oil)
• Include eggs and fatty fish
• Check thyroid function
• Review medications with doctor
• Rule out liver problems''',
            
            'high': '''⚠️ **High Cholesterol** is a major risk factor for heart disease and stroke.

**Why It's Dangerous:**
• LDL builds up in artery walls (plaque)
• Narrows blood vessels
• Reduces blood flow to heart and brain
• Can cause heart attack or stroke
• Often has NO symptoms (silent killer!)

**Risk Factors:**
• Poor diet (saturated fats, trans fats)
• Lack of exercise
• Obesity (especially belly fat)
• Smoking
• Diabetes
• Family history
• Age (men >45, women >55)
• High blood pressure

**Complications:**
• Coronary artery disease
• Heart attack
• Stroke
• Peripheral artery disease
• Chest pain (angina)
• Carotid artery disease

**Warning Signs (Advanced):**
• Chest pain or pressure
• Shortness of breath
• Pain in neck, jaw, upper abdomen
• Numbness or coldness in extremities
• Xanthomas (cholesterol deposits under skin)

**Immediate Actions:**
• Start heart-healthy diet TODAY
• Begin regular exercise
• Quit smoking
• Lose weight if overweight
• Consider medication (statins) if very high
• Get lipid panel every 3-6 months''',
            
            'improve': '''💪 **How to Lower Cholesterol Naturally:**

**Best Foods (Eat More):**
• Oats and barley (soluble fiber)
• Beans and lentils
• Nuts (almonds, walnuts) - 1 handful daily
• Fatty fish (salmon, mackerel) - 2x/week
• Avocados
• Olive oil (extra virgin)
• Fruits (apples, berries, citrus)
• Vegetables (especially leafy greens)
• Soy products (tofu, edamame)
• Dark chocolate (70%+ cocoa, small amounts)

**Foods to Avoid:**
• Red meat and processed meats
• Full-fat dairy products
• Butter and lard
• Fried foods
• Baked goods (cookies, cakes, pastries)
• Trans fats (partially hydrogenated oils)
• Fast food
• Processed snacks

**Powerful Cholesterol-Lowering Foods:**
• Psyllium husk (5-10g daily)
• Ground flaxseed (2 tablespoons daily)
• Chia seeds
• Plant sterols/stanols (2g daily)
• Garlic (fresh or aged extract)
• Green tea (3-4 cups daily)

**Exercise Plan:**
• 30 minutes moderate activity, 5 days/week
• Aerobic: Walking, jogging, cycling, swimming
• Strength training: 2 days/week
• Even 10-minute walks help!
• Aim for 10,000 steps daily

**Lifestyle Changes:**
• Lose 5-10% body weight
• Quit smoking (raises HDL by 10%)
• Limit alcohol (1 drink/day women, 2 men)
• Manage stress
• Get adequate sleep

**Supplements (Consult Doctor):**
• Fish oil (omega-3): 1-2g daily
• Plant sterols: 2g daily
• Red yeast rice (contains natural statin)
• Niacin (vitamin B3)
• Psyllium fiber
• Coenzyme Q10 (if on statins)

**Expected Results:**
• Diet changes: 5-10% reduction in 6 weeks
• Exercise: 5% reduction in 3 months
• Weight loss: 1% reduction per 2 lbs lost
• Combined approach: 20-30% reduction possible!'''
        },
        
        'platelets': {
            'what': '''🩸 **Platelets** are tiny blood cells that form clots to stop bleeding when you're injured.

**Key Functions:**
• Stop bleeding (hemostasis)
• Form blood clots at injury sites
• Release growth factors for healing
• Maintain blood vessel integrity

**Normal Range:** 150,000-400,000 cells/μL

**Lifespan:** 7-10 days

**How They Work:**
1. Blood vessel is damaged
2. Platelets rush to the site
3. They stick together (aggregation)
4. Form a plug to stop bleeding
5. Clotting factors strengthen the plug

**Production:**
• Made in bone marrow
• Regulated by thrombopoietin hormone
• Destroyed in spleen and liver''',
            
            'low': '''⚠️ **Low Platelets (Thrombocytopenia)** increases bleeding risk.

**Severity Levels:**
• Mild: 100,000-150,000 (usually no symptoms)
• Moderate: 50,000-100,000 (easy bruising)
• Severe: <50,000 (spontaneous bleeding)
• Critical: <20,000 (life-threatening)

**Symptoms:**
• Easy or excessive bruising (purpura)
• Prolonged bleeding from cuts
• Spontaneous bleeding (nose, gums)
• Blood in urine or stool
• Heavy menstrual periods
• Tiny red spots on skin (petechiae)
• Fatigue

**Common Causes:**
• Viral infections (dengue, HIV, hepatitis C)
• Medications (heparin, antibiotics, seizure drugs)
• Autoimmune disorders (ITP, lupus)
• Pregnancy
• Alcohol abuse
• Bone marrow disorders
• Enlarged spleen
• Chemotherapy/radiation

**When to Seek Emergency Care:**
• Bleeding that won't stop
• Blood in vomit or stool
• Severe headache
• Confusion or vision changes
• Platelet count <20,000

**Precautions:**
• Avoid contact sports
• Use soft toothbrush
• Avoid aspirin and NSAIDs
• Be careful with sharp objects
• Avoid alcohol
• Report any unusual bleeding''',
            
            'high': '''📈 **High Platelets (Thrombocytosis)** may increase blood clot risk.

**Types:**
• Primary (Essential): Bone marrow produces too many
• Secondary (Reactive): Response to another condition

**Symptoms (Often None):**
• Headaches
• Dizziness
• Chest pain
• Weakness or fatigue
• Vision changes
• Numbness or tingling
• Blood clots (serious!)

**Common Causes:**
• Acute bleeding or blood loss
• Iron deficiency anemia
• Infections or inflammation
• Cancer
• Recent surgery
• Removal of spleen
• Inflammatory bowel disease
• Rheumatoid arthritis
• Bone marrow disorders

**Complications:**
• Blood clots in legs (DVT)
• Pulmonary embolism
• Stroke
• Heart attack
• Pregnancy complications

**When to Worry:**
• Platelet count >450,000
• Persistent elevation
• Symptoms of blood clots
• No obvious cause

**Management:**
• Treat underlying condition
• Aspirin (low dose) if high risk
• Hydroxyurea (for primary)
• Stay hydrated
• Avoid smoking
• Regular monitoring''',
            
            'improve': '''💪 **How to Support Healthy Platelet Count:**

**For Low Platelets:**

**Foods to Increase Platelets:**
• Leafy greens (vitamin K): Kale, spinach, collards
• Fatty fish (omega-3): Salmon, mackerel, sardines
• Eggs (vitamin B12)
• Lean meats (iron, B12)
• Pumpkin seeds (zinc)
• Pomegranate (antioxidants)
• Papaya and papaya leaf extract
• Wheatgrass juice
• Beetroot
• Indian gooseberry (amla)

**Essential Nutrients:**
• Vitamin B12: 2.4mcg daily
• Folate: 400mcg daily
• Vitamin K: 90-120mcg daily
• Iron: 8-18mg daily
• Vitamin C: 75-90mg daily
• Vitamin D: 600-800 IU daily

**Lifestyle Tips:**
• Avoid alcohol (suppresses production)
• Don't take aspirin or NSAIDs
• Get adequate sleep
• Manage stress
• Avoid activities that risk bleeding
• Stay hydrated

**For High Platelets:**

**Anti-Inflammatory Foods:**
• Fatty fish (omega-3s)
• Berries (antioxidants)
• Turmeric and ginger
• Green tea
• Dark chocolate
• Olive oil
• Tomatoes
• Leafy greens

**Foods with Natural Blood Thinners:**
• Garlic
• Ginger
• Turmeric
• Cinnamon
• Cayenne pepper
• Vitamin E-rich foods

**Lifestyle:**
• Stay well-hydrated
• Exercise regularly
• Maintain healthy weight
• Avoid smoking
• Limit alcohol
• Manage underlying conditions

**Supplements (Consult Doctor):**
• Omega-3 fish oil
• Vitamin D (if deficient)
• Folate and B12 (for low platelets)
• Papaya leaf extract (for low platelets)
• Avoid vitamin K supplements if on blood thinners'''
        }
    }
    
    # Check if user is asking about their specific results
    if report_data and 'results' in report_data:
        for result in report_data['results']:
            test_name = result['test'].lower()
            if test_name in question:
                status = result['status']
                value = result['value']
                unit = result['unit']
                min_val = result['min']
                max_val = result['max']
                
                # Enhanced personalized response
                if status == 'Normal':
                    response = f"✅ **Great news!** Your {result['test']} level is {value} {unit}, which is within the healthy normal range of {min_val}-{max_val} {unit}.\n\n"
                    response += f"**What this means:**\n{result.get('description', '')}\n\n"
                    response += f"**Keep it up!** Continue your current healthy habits to maintain these good levels."
                elif status == 'Low':
                    response = f"⚠️ **Attention needed:** Your {result['test']} level is {value} {unit}, which is below the normal range of {min_val}-{max_val} {unit}.\n\n"
                    response += f"**What this means:**\n{result.get('description', '')}\n\n"
                    response += f"**Next steps:**\n• Consult your doctor for proper evaluation\n• Ask me 'How to improve {test_name}?' for dietary and lifestyle tips\n• Consider getting retested in 4-6 weeks"
                else:  # High
                    response = f"⚠️ **Attention needed:** Your {result['test']} level is {value} {unit}, which is above the normal range of {min_val}-{max_val} {unit}.\n\n"
                    response += f"**What this means:**\n{result.get('description', '')}\n\n"
                    response += f"**Next steps:**\n• Consult your doctor for proper evaluation\n• Ask me 'How to lower {test_name}?' for dietary and lifestyle tips\n• Monitor your levels regularly"
                
                return response
    
    # Answer general questions
    if 'what is' in question or 'what are' in question:
        for test, info in knowledge_base.items():
            if test in question:
                return info['what']
    
    if 'low' in question or 'decrease' in question:
        for test, info in knowledge_base.items():
            if test in question:
                return info['low']
    
    if 'high' in question or 'increase' in question or 'elevated' in question:
        for test, info in knowledge_base.items():
            if test in question:
                return info['high']
    
    if 'improve' in question or 'increase' in question or 'how to' in question or 'what can i do' in question:
        for test, info in knowledge_base.items():
            if test in question:
                return info['improve']
    
    # General health questions
    if 'normal range' in question:
        return "Normal ranges vary by test:\n• Hemoglobin: 12-16 g/dL (women), 14-18 g/dL (men)\n• WBC: 4,000-11,000 cells/μL\n• Glucose: 70-100 mg/dL (fasting)\n• Cholesterol: <200 mg/dL\n• Platelets: 150,000-400,000 cells/μL"
    
    if 'how often' in question and 'test' in question:
        return "Testing frequency depends on your health:\n• Healthy adults: Annual checkup with basic tests\n• Chronic conditions: Every 3-6 months\n• Diabetes: HbA1c every 3 months\n• High cholesterol: Every 4-6 months\nAlways follow your doctor's recommendations."
    
    if 'diet' in question or 'food' in question or 'eat' in question:
        return "For optimal health:\n• Eat plenty of fruits and vegetables\n• Choose whole grains over refined carbs\n• Include lean proteins (fish, chicken, beans)\n• Limit processed foods and added sugars\n• Stay hydrated with water\n• Consider Mediterranean diet patterns\nConsult a nutritionist for personalized advice."
    
    if 'exercise' in question or 'workout' in question:
        return "Exercise recommendations:\n• 150 minutes moderate activity per week\n• Or 75 minutes vigorous activity\n• Include strength training 2x/week\n• Start slowly and build up gradually\n• Walking, swimming, cycling are great options\nConsult your doctor before starting new exercise programs."
    
    if 'doctor' in question or 'when to see' in question:
        return "See a doctor if:\n• Any test results are significantly abnormal\n• You have concerning symptoms\n• Results show a sudden change from previous tests\n• You have multiple abnormal results\n• You're unsure about what results mean\nAlways consult healthcare professionals for medical advice."
    
    # Greeting responses
    greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening']
    if any(greeting in question for greeting in greetings):
        return "👋 Hello! I'm your AI Health Assistant. I'm here to help you understand your medical test results and answer health questions.\n\n**I can help you with:**\n• Understanding what medical tests mean\n• Explaining your specific test results\n• Providing dietary and lifestyle recommendations\n• Answering questions about normal ranges\n• Offering health improvement tips\n\n**Try asking:**\n• 'What is hemoglobin?'\n• 'Why is my glucose high?'\n• 'How to improve WBC count?'\n• 'Tell me about my results'"
    
    # Thank you responses
    if 'thank' in question or 'thanks' in question:
        return "😊 You're very welcome! I'm happy to help you understand your health better. Feel free to ask me anything else about your medical results or health questions!"
    
    # Help requests
    if 'help' in question or 'what can you do' in question:
        return "🤖 **I'm your AI Health Assistant!**\n\nI can help you:\n\n**Understand Medical Tests:**\n• What is hemoglobin, WBC, glucose, cholesterol, platelets?\n• What do these tests measure?\n• Why are they important?\n\n**Explain Your Results:**\n• Why is my [test] high or low?\n• What does my result mean?\n• Should I be concerned?\n\n**Provide Health Guidance:**\n• How to improve [test]?\n• What foods should I eat?\n• What lifestyle changes help?\n• When should I see a doctor?\n\n**General Health Info:**\n• What are normal ranges?\n• How often should I test?\n• Diet and exercise tips\n\n💡 **Tip:** Upload your medical report first, then ask me about your specific results!"
    
    # Summary request
    if 'summary' in question or 'overview' in question or 'all results' in question or 'my results' in question:
        if report_data and 'results' in report_data:
            results = report_data['results']
            normal_count = sum(1 for r in results if r['status'] == 'Normal')
            high_count = sum(1 for r in results if r['status'] == 'High')
            low_count = sum(1 for r in results if r['status'] == 'Low')
            
            response = f"📊 **Your Medical Report Summary**\n\n"
            response += f"**Overall Status:**\n"
            response += f"• ✅ Normal: {normal_count} tests\n"
            response += f"• ⚠️ High: {high_count} tests\n"
            response += f"• ⚠️ Low: {low_count} tests\n"
            response += f"• 📋 Total: {len(results)} tests analyzed\n\n"
            
            if high_count > 0 or low_count > 0:
                response += "**Tests Needing Attention:**\n"
                for r in results:
                    if r['status'] != 'Normal':
                        response += f"• {r['test']}: {r['value']} {r['unit']} ({r['status']})\n"
                response += "\n💡 Ask me about any specific test for detailed information!"
            else:
                response += "🎉 **Excellent!** All your test results are within normal ranges. Keep up the great work with your health!"
            
            return response
        else:
            return "📋 I don't have your test results yet. Please upload your medical report first, then I can provide a detailed summary of your results!"
    
    # Default responses
    default_responses = [
        "🤔 I'm not sure I understood that question. Let me help you!\n\n**I can answer questions like:**\n• 'What is hemoglobin?'\n• 'Why is my glucose high?'\n• 'How to improve WBC count?'\n• 'What are normal ranges?'\n• 'Give me a summary of my results'\n\n**Tip:** Try to be specific about which test or health topic you're asking about!",
        "💬 I'm here to help with medical test questions! Try asking:\n• About specific tests (hemoglobin, WBC, glucose, cholesterol, platelets)\n• About your test results (if you've uploaded a report)\n• How to improve specific health markers\n• What normal ranges are\n\nWhat would you like to know?",
        "🩺 I specialize in explaining medical test results! You can ask me:\n• What a specific test means\n• Why your results are high or low\n• How to improve your health markers\n• General health and nutrition questions\n\nWhat's on your mind?"
    ]
    
    return random.choice(default_responses)

@app.route('/analyze', methods=['POST'])
def analyze_report():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Please upload PNG, JPG, or PDF'}), 400
    
    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract text based on file type
        if filename.lower().endswith('.pdf'):
            text = extract_text_from_pdf(filepath)
        else:
            text = extract_text_from_image(filepath)
        
        print(f"Extracted text length: {len(text)}")
        print(f"First 500 chars: {text[:500]}")
        
        # Extract medical values
        extracted_values = extract_medical_values(text)
        
        print(f"Extracted values: {extracted_values}")
        
        if not extracted_values:
            return jsonify({
                'error': 'No medical values detected in the report. Please ensure the image is clear and contains medical test results.',
                'debug_text': text[:1000]  # Return first 1000 chars for debugging
            }), 400
        
        # Compare with reference
        comparison_results = compare_with_reference(extracted_values)
        
        # Generate insights
        insights = generate_insights(comparison_results)
        
        # Create visualization
        chart_json = create_visualization(comparison_results)
        
        # Clean up uploaded file
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'results': comparison_results,
            'insights': insights,
            'chart': chart_json,
            'extracted_text': text[:500]  # First 500 chars for debugging
        })
    
    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
