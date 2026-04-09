let selectedFile = null;

const uploadBox = document.getElementById('uploadBox');
const fileInput = document.getElementById('fileInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const loadingSection = document.getElementById('loadingSection');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');

// Click to upload
uploadBox.addEventListener('click', () => {
    fileInput.click();
});

// File selection
fileInput.addEventListener('change', (e) => {
    handleFileSelect(e.target.files[0]);
});

// Drag and drop
uploadBox.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadBox.classList.add('dragover');
});

uploadBox.addEventListener('dragleave', () => {
    uploadBox.classList.remove('dragover');
});

uploadBox.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadBox.classList.remove('dragover');
    handleFileSelect(e.dataTransfer.files[0]);
});

function handleFileSelect(file) {
    if (!file) return;
    
    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
    if (!validTypes.includes(file.type)) {
        showError('Invalid file type. Please upload a PDF, JPG, or PNG file.');
        return;
    }
    
    selectedFile = file;
    uploadBox.querySelector('h3').textContent = `Selected: ${file.name}`;
    uploadBox.querySelector('.upload-icon').textContent = '✅';
    analyzeBtn.disabled = false;
}

// Analyze button
analyzeBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    
    hideAllSections();
    loadingSection.style.display = 'block';
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Analysis failed');
        }
        
        displayResults(data);
    } catch (error) {
        showError(error.message);
    }
});

// Tab functionality
document.addEventListener('DOMContentLoaded', () => {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.getAttribute('data-tab');
            
            // Remove active class from all tabs and contents
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            // Add active class to clicked tab and corresponding content
            btn.classList.add('active');
            document.getElementById(`${tabName}-tab`).classList.add('active');
        });
    });
});

function displayResults(data) {
    hideAllSections();
    resultsSection.style.display = 'block';
    
    // Calculate summary statistics with animation
    let normalCount = 0, highCount = 0, lowCount = 0;
    data.results.forEach(result => {
        if (result.status === 'Normal') normalCount++;
        else if (result.status === 'High') highCount++;
        else if (result.status === 'Low') lowCount++;
    });
    
    const totalTests = data.results.length;
    
    // Update report date
    const now = new Date();
    document.getElementById('reportDate').textContent = 
        `Analysis completed on ${now.toLocaleDateString()} at ${now.toLocaleTimeString()}`;
    
    // Calculate health score (0-100)
    const healthScore = Math.round((normalCount / totalTests) * 100);
    
    // Animate health score
    animateValue('healthScore', 0, healthScore, 2000);
    
    // Update score circle
    const circumference = 2 * Math.PI * 90;
    const offset = circumference - (healthScore / 100) * circumference;
    document.getElementById('scoreProgress').style.strokeDashoffset = offset;
    
    // Update score title and description
    const scoreTitle = document.getElementById('scoreTitle');
    const scoreDescription = document.getElementById('scoreDescription');
    
    if (healthScore >= 80) {
        scoreTitle.textContent = '🎉 Excellent Health!';
        scoreDescription.textContent = 'Most of your test results are within normal ranges. Keep up the great work!';
    } else if (healthScore >= 60) {
        scoreTitle.textContent = '👍 Good Health';
        scoreDescription.textContent = 'Majority of your tests are normal, but some areas need attention.';
    } else if (healthScore >= 40) {
        scoreTitle.textContent = '⚠️ Needs Attention';
        scoreDescription.textContent = 'Several test results are outside normal ranges. Consult your doctor.';
    } else {
        scoreTitle.textContent = '🚨 Requires Action';
        scoreDescription.textContent = 'Many tests are abnormal. Please consult your healthcare provider immediately.';
    }
    
    // Update score breakdown
    document.getElementById('normalPercentage').textContent = `${Math.round((normalCount/totalTests)*100)}%`;
    document.getElementById('testsReviewed').textContent = totalTests;
    
    const riskLevel = document.getElementById('riskLevel');
    const abnormalCount = highCount + lowCount;
    if (abnormalCount === 0) {
        riskLevel.textContent = 'Low';
        riskLevel.className = 'breakdown-value risk-badge low';
    } else if (abnormalCount <= 2) {
        riskLevel.textContent = 'Medium';
        riskLevel.className = 'breakdown-value risk-badge medium';
    } else {
        riskLevel.textContent = 'High';
        riskLevel.className = 'breakdown-value risk-badge high';
    }
    
    // Animate summary cards
    animateValue('normalCount', 0, normalCount, 1000);
    animateValue('highCount', 0, highCount, 1000);
    animateValue('lowCount', 0, lowCount, 1000);
    animateValue('totalCount', 0, totalTests, 1000);
    
    // Update percentages
    document.getElementById('normalPercent').textContent = `${Math.round((normalCount/totalTests)*100)}%`;
    document.getElementById('highPercent').textContent = `${Math.round((highCount/totalTests)*100)}%`;
    document.getElementById('lowPercent').textContent = `${Math.round((lowCount/totalTests)*100)}%`;
    
    // Generate quick insights
    generateQuickInsights(data.results, normalCount, highCount, lowCount);
    
    // Show tests needing attention
    if (highCount > 0 || lowCount > 0) {
        showAttentionPanel(data.results);
    }
    
    // Display bar chart
    if (data.chart && data.chart.bar) {
        const barData = JSON.parse(data.chart.bar);
        Plotly.newPlot('barChartContainer', barData.data, barData.layout, {
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
            displaylogo: false
        });
    }
    
    // Display gauge charts
    if (data.chart && data.chart.gauges) {
        const gaugeContainer = document.getElementById('gaugeChartsContainer');
        gaugeContainer.innerHTML = '';
        
        data.chart.gauges.forEach((gaugeJson, index) => {
            const gaugeDiv = document.createElement('div');
            gaugeDiv.className = 'gauge-item';
            gaugeDiv.style.animationDelay = `${index * 0.1}s`;
            gaugeContainer.appendChild(gaugeDiv);
            
            const gaugeData = JSON.parse(gaugeJson);
            Plotly.newPlot(gaugeDiv, gaugeData.data, gaugeData.layout, {
                responsive: true,
                displayModeBar: false
            });
        });
    }
    
    // Display pie chart
    if (data.chart && data.chart.pie) {
        const pieData = JSON.parse(data.chart.pie);
        Plotly.newPlot('pieChartContainer', pieData.data, pieData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display radar chart
    if (data.chart && data.chart.radar) {
        const radarData = JSON.parse(data.chart.radar);
        Plotly.newPlot('radarChartContainer', radarData.data, radarData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display trend chart
    if (data.chart && data.chart.trend) {
        const trendData = JSON.parse(data.chart.trend);
        Plotly.newPlot('trendChartContainer', trendData.data, trendData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display box plot
    if (data.chart && data.chart.box) {
        const boxData = JSON.parse(data.chart.box);
        Plotly.newPlot('boxChartContainer', boxData.data, boxData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display heatmap
    if (data.chart && data.chart.heatmap) {
        const heatmapData = JSON.parse(data.chart.heatmap);
        Plotly.newPlot('heatmapContainer', heatmapData.data, heatmapData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display 3D scatter
    if (data.chart && data.chart.scatter3d) {
        const scatter3dData = JSON.parse(data.chart.scatter3d);
        Plotly.newPlot('scatter3dContainer', scatter3dData.data, scatter3dData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display waterfall chart
    if (data.chart && data.chart.waterfall) {
        const waterfallData = JSON.parse(data.chart.waterfall);
        Plotly.newPlot('waterfallContainer', waterfallData.data, waterfallData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display funnel chart
    if (data.chart && data.chart.funnel) {
        const funnelData = JSON.parse(data.chart.funnel);
        Plotly.newPlot('funnelContainer', funnelData.data, funnelData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display polar chart
    if (data.chart && data.chart.polar) {
        const polarData = JSON.parse(data.chart.polar);
        Plotly.newPlot('polarContainer', polarData.data, polarData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display sunburst chart
    if (data.chart && data.chart.sunburst) {
        const sunburstData = JSON.parse(data.chart.sunburst);
        Plotly.newPlot('sunburstContainer', sunburstData.data, sunburstData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display violin plot
    if (data.chart && data.chart.violin) {
        const violinData = JSON.parse(data.chart.violin);
        Plotly.newPlot('violinContainer', violinData.data, violinData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display sankey diagram
    if (data.chart && data.chart.sankey) {
        const sankeyData = JSON.parse(data.chart.sankey);
        Plotly.newPlot('sankeyContainer', sankeyData.data, sankeyData.layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false
        });
    }
    
    // Display KPI indicators
    if (data.chart && data.chart.kpi) {
        const kpiContainer = document.getElementById('kpiContainer');
        kpiContainer.innerHTML = '';
        
        data.chart.kpi.forEach((kpiJson, index) => {
            const kpiDiv = document.createElement('div');
            kpiDiv.className = 'kpi-item';
            kpiDiv.style.animationDelay = `${index * 0.1}s`;
            kpiContainer.appendChild(kpiDiv);
            
            const kpiData = JSON.parse(kpiJson);
            Plotly.newPlot(kpiDiv, kpiData.data, kpiData.layout, {
                responsive: true,
                displayModeBar: false
            });
        });
    }
    
    // Display table with animation
    const tableBody = document.getElementById('tableBody');
    tableBody.innerHTML = '';
    
    data.results.forEach((result, index) => {
        const row = document.createElement('tr');
        row.className = `table-row-${result.status.toLowerCase()}`;
        row.style.animationDelay = `${index * 0.05}s`;
        row.innerHTML = `
            <td><strong>${result.test}</strong></td>
            <td class="value-cell">${result.value}</td>
            <td>${result.min} - ${result.max}</td>
            <td>${result.unit}</td>
            <td><span class="status-badge" style="background-color: ${result.color}">${result.status}</span></td>
            <td class="description-cell">${result.description}</td>
        `;
        tableBody.appendChild(row);
    });
    
    // Display insights with animation
    const insightsList = document.getElementById('insightsList');
    insightsList.innerHTML = '';
    
    data.insights.forEach((insight, index) => {
        const card = document.createElement('div');
        card.className = `insight-card ${insight.status.toLowerCase()}`;
        card.style.animationDelay = `${index * 0.1}s`;
        
        const statusIcon = insight.status === 'Normal' ? '✅' : 
                          insight.status === 'High' ? '⚠️' : '⬇️';
        
        card.innerHTML = `
            <div class="insight-header">
                <span class="insight-icon">${statusIcon}</span>
                <h4>${insight.test}</h4>
            </div>
            <p>${insight.insight}</p>
        `;
        insightsList.appendChild(card);
    });
    
    // Setup interactive comparison
    setupComparison(data.results);
    
    // Store report data for chatbot
    storeReportData(data);
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Animate number counting
function animateValue(id, start, end, duration) {
    const element = document.getElementById(id);
    const range = end - start;
    const increment = range / (duration / 16);
    let current = start;
    
    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        element.textContent = Math.floor(current);
    }, 16);
}

// Interactive comparison functionality
let comparisonData = null;

function setupComparison(results) {
    comparisonData = results;
    const selector = document.getElementById('testSelector');
    selector.innerHTML = '<option value="">Choose a test...</option>';
    
    results.forEach((result, index) => {
        const option = document.createElement('option');
        option.value = index;
        option.textContent = result.test;
        selector.appendChild(option);
    });
    
    selector.addEventListener('change', (e) => {
        if (e.target.value !== '') {
            updateComparison(parseInt(e.target.value));
        }
    });
    
    // Auto-select first test
    if (results.length > 0) {
        selector.value = '0';
        updateComparison(0);
    }
}

function updateComparison(index) {
    const result = comparisonData[index];
    const marker = document.getElementById('valueMarker');
    
    // Calculate position (0-100%)
    const totalRange = result.max * 1.5; // Extended range for visualization
    const minPos = 0;
    const normalStart = (result.min / totalRange) * 100;
    const normalEnd = (result.max / totalRange) * 100;
    const valuePos = (result.value / totalRange) * 100;
    
    // Update marker position
    marker.style.left = `${Math.min(Math.max(valuePos, 0), 100)}%`;
    
    // Update marker color based on status
    if (result.status === 'Normal') {
        marker.style.borderColor = '#2ecc71';
    } else if (result.status === 'High') {
        marker.style.borderColor = '#e74c3c';
    } else {
        marker.style.borderColor = '#3498db';
    }
    
    // Update values
    document.getElementById('compMinValue').textContent = `${result.min} ${result.unit}`;
    document.getElementById('compYourValue').textContent = `${result.value} ${result.unit}`;
    document.getElementById('compMaxValue').textContent = `${result.max} ${result.unit}`;
    
    // Update marker label
    marker.querySelector('.marker-label').textContent = `${result.value} ${result.unit}`;
}

function showError(message) {
    hideAllSections();
    errorSection.style.display = 'block';
    document.getElementById('errorMessage').textContent = message;
}

function hideAllSections() {
    loadingSection.style.display = 'none';
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';
}

// Chatbot functionality
let currentReportData = null;
let recognition = null;
let synthesis = window.speechSynthesis;
let currentUtterance = null;

const chatbotContainer = document.getElementById('chatbotContainer');
const chatbotFloatBtn = document.getElementById('chatbotFloatBtn');
const chatbotToggle = document.getElementById('chatbotToggle');
const chatbotHeader = document.getElementById('chatbotHeader');
const chatbotBody = document.getElementById('chatbotBody');
const chatbotMessages = document.getElementById('chatbotMessages');
const chatbotInput = document.getElementById('chatbotInput');
const chatbotSend = document.getElementById('chatbotSend');
const chatbotVoice = document.getElementById('chatbotVoice');

// Initialize speech recognition
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        chatbotInput.value = transcript;
        chatbotVoice.classList.remove('listening');
        sendMessage();
    };
    
    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        chatbotVoice.classList.remove('listening');
        if (event.error === 'no-speech') {
            addMessage('I didn\'t hear anything. Please try again.', 'bot');
        }
    };
    
    recognition.onend = () => {
        chatbotVoice.classList.remove('listening');
    };
}

// Toggle chatbot visibility
chatbotFloatBtn.addEventListener('click', () => {
    chatbotContainer.classList.toggle('active');
    if (chatbotContainer.classList.contains('active')) {
        chatbotInput.focus();
    }
});

// Minimize/maximize chatbot
chatbotToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    chatbotBody.classList.toggle('collapsed');
    chatbotToggle.textContent = chatbotBody.classList.contains('collapsed') ? '+' : '−';
});

// Voice input
chatbotVoice.addEventListener('click', () => {
    if (recognition) {
        if (chatbotVoice.classList.contains('listening')) {
            recognition.stop();
            chatbotVoice.classList.remove('listening');
        } else {
            recognition.start();
            chatbotVoice.classList.add('listening');
            addMessage('Listening... Speak now!', 'bot');
        }
    } else {
        addMessage('Sorry, voice recognition is not supported in your browser. Please use Chrome, Edge, or Safari.', 'bot');
    }
});

// Send message on button click
chatbotSend.addEventListener('click', sendMessage);

// Send message on Enter key
chatbotInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

async function sendMessage() {
    const question = chatbotInput.value.trim();
    if (!question) return;
    
    // Add user message to chat
    addMessage(question, 'user');
    chatbotInput.value = '';
    
    // Show typing indicator
    const typingId = showTypingIndicator();
    
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: question,
                report_data: currentReportData
            })
        });
        
        const data = await response.json();
        
        // Remove typing indicator
        removeTypingIndicator(typingId);
        
        if (data.success) {
            addMessage(data.response, 'bot');
        } else {
            addMessage('Sorry, I encountered an error. Please try again.', 'bot');
        }
    } catch (error) {
        removeTypingIndicator(typingId);
        addMessage('Sorry, I\'m having trouble connecting. Please try again.', 'bot');
    }
}

function addMessage(text, sender, enableSpeech = true) {
    const messageDiv = document.createElement('div');
    messageDiv.className = sender === 'user' ? 'user-message' : 'bot-message';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = sender === 'user' ? '👤' : '🤖';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    content.style.position = 'relative';
    
    // Add speaker button for bot messages
    if (sender === 'bot' && enableSpeech && synthesis) {
        const speakerBtn = document.createElement('button');
        speakerBtn.className = 'message-speaker';
        speakerBtn.innerHTML = '🔊';
        speakerBtn.title = 'Listen to this message';
        speakerBtn.onclick = () => speakText(text, speakerBtn);
        content.appendChild(speakerBtn);
    }
    
    // Convert newlines to paragraphs and handle formatting
    const paragraphs = text.split('\n').filter(p => p.trim());
    let currentList = null;
    
    paragraphs.forEach(para => {
        const trimmed = para.trim();
        
        // Handle bullet points
        if (trimmed.startsWith('•')) {
            if (!currentList) {
                currentList = document.createElement('ul');
                content.appendChild(currentList);
            }
            const li = document.createElement('li');
            li.textContent = trimmed.substring(1).trim();
            currentList.appendChild(li);
        } 
        // Handle bold headers (text between **)
        else if (trimmed.includes('**')) {
            currentList = null;
            const p = document.createElement('p');
            const parts = trimmed.split('**');
            parts.forEach((part, index) => {
                if (index % 2 === 1) {
                    const strong = document.createElement('strong');
                    strong.textContent = part;
                    p.appendChild(strong);
                } else if (part) {
                    p.appendChild(document.createTextNode(part));
                }
            });
            content.appendChild(p);
        }
        // Handle emojis and regular text
        else {
            currentList = null;
            const p = document.createElement('p');
            p.textContent = trimmed;
            content.appendChild(p);
        }
    });
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    chatbotMessages.appendChild(messageDiv);
    
    // Scroll to bottom
    chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
    
    // Auto-speak bot messages (optional - can be disabled)
    // if (sender === 'bot' && enableSpeech && synthesis) {
    //     setTimeout(() => speakText(text), 500);
    // }
}

function speakText(text, button = null) {
    // Stop any ongoing speech
    if (synthesis.speaking) {
        synthesis.cancel();
        if (button) button.classList.remove('speaking');
        return;
    }
    
    // Clean text for speech (remove emojis and special formatting)
    let cleanText = text
        .replace(/[🔴🛡️🍬💛🩸⚠️📈📉💪🎯✨💡]/g, '')
        .replace(/\*\*/g, '')
        .replace(/•/g, '')
        .trim();
    
    // Create utterance
    currentUtterance = new SpeechSynthesisUtterance(cleanText);
    currentUtterance.rate = 0.9; // Slightly slower for clarity
    currentUtterance.pitch = 1.0;
    currentUtterance.volume = 1.0;
    
    // Try to use a natural voice
    const voices = synthesis.getVoices();
    const preferredVoice = voices.find(voice => 
        voice.name.includes('Google') || 
        voice.name.includes('Microsoft') ||
        voice.lang.startsWith('en')
    );
    if (preferredVoice) {
        currentUtterance.voice = preferredVoice;
    }
    
    // Add button animation
    if (button) {
        button.classList.add('speaking');
        currentUtterance.onend = () => {
            button.classList.remove('speaking');
        };
        currentUtterance.onerror = () => {
            button.classList.remove('speaking');
        };
    }
    
    // Speak
    synthesis.speak(currentUtterance);
}

// Load voices when available
if (synthesis) {
    synthesis.onvoiceschanged = () => {
        synthesis.getVoices();
    };
}

function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'bot-message typing-message';
    typingDiv.id = 'typing-indicator';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = '🤖';
    
    const content = document.createElement('div');
    content.className = 'message-content typing-indicator';
    content.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    
    typingDiv.appendChild(avatar);
    typingDiv.appendChild(content);
    chatbotMessages.appendChild(typingDiv);
    
    chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
    
    return 'typing-indicator';
}

function removeTypingIndicator(id) {
    const typingElement = document.getElementById(id);
    if (typingElement) {
        typingElement.remove();
    }
}

// Generate quick insights
function generateQuickInsights(results, normalCount, highCount, lowCount) {
    const insightsContainer = document.getElementById('quickInsights');
    insightsContainer.innerHTML = '';
    
    const insights = [];
    
    // Positive insights
    if (normalCount > 0) {
        insights.push({
            type: 'positive',
            icon: '✅',
            text: `${normalCount} test${normalCount > 1 ? 's' : ''} within normal range`
        });
    }
    
    if (normalCount === results.length) {
        insights.push({
            type: 'positive',
            icon: '🎉',
            text: 'All tests are normal - Excellent health status!'
        });
    }
    
    // Warning insights
    if (highCount > 0) {
        insights.push({
            type: 'warning',
            icon: '⚠️',
            text: `${highCount} test${highCount > 1 ? 's' : ''} above normal range`
        });
    }
    
    if (lowCount > 0) {
        insights.push({
            type: 'warning',
            icon: '⬇️',
            text: `${lowCount} test${lowCount > 1 ? 's' : ''} below normal range`
        });
    }
    
    // Critical insights
    const criticalTests = results.filter(r => {
        const deviation = Math.abs(r.value - ((r.min + r.max) / 2)) / ((r.max - r.min) / 2);
        return deviation > 0.5 && r.status !== 'Normal';
    });
    
    if (criticalTests.length > 0) {
        insights.push({
            type: 'critical',
            icon: '🚨',
            text: `${criticalTests.length} test${criticalTests.length > 1 ? 's' : ''} significantly out of range`
        });
    }
    
    // Render insights
    insights.forEach(insight => {
        const item = document.createElement('div');
        item.className = `insight-item ${insight.type}`;
        item.innerHTML = `
            <span class="insight-icon">${insight.icon}</span>
            <span class="insight-text">${insight.text}</span>
        `;
        insightsContainer.appendChild(item);
    });
}

// Show tests needing attention
function showAttentionPanel(results) {
    const panel = document.getElementById('attentionPanel');
    const list = document.getElementById('attentionList');
    
    const abnormalTests = results.filter(r => r.status !== 'Normal');
    
    if (abnormalTests.length === 0) {
        panel.style.display = 'none';
        return;
    }
    
    panel.style.display = 'block';
    list.innerHTML = '';
    
    abnormalTests.forEach(test => {
        const item = document.createElement('div');
        item.className = `attention-item ${test.status.toLowerCase()}`;
        item.innerHTML = `
            <div class="attention-info">
                <div class="attention-test-name">${test.test}</div>
                <div class="attention-value">
                    Your value: ${test.value} ${test.unit} 
                    (Normal: ${test.min}-${test.max} ${test.unit})
                </div>
            </div>
            <button class="attention-action" onclick="askAboutTest('${test.test}')">
                Learn More
            </button>
        `;
        list.appendChild(item);
    });
}

// Ask chatbot about specific test
function askAboutTest(testName) {
    // Open chatbot
    chatbotContainer.classList.add('active');
    
    // Set question
    chatbotInput.value = `Why is my ${testName} ${currentReportData.results.find(r => r.test === testName).status.toLowerCase()}?`;
    
    // Send message
    setTimeout(() => {
        sendMessage();
    }, 300);
}

// Download report functionality
document.getElementById('downloadReportBtn')?.addEventListener('click', () => {
    alert('Download feature coming soon! This will generate a PDF report of your results.');
});

// Print report functionality
document.getElementById('printReportBtn')?.addEventListener('click', () => {
    window.print();
});

// Share report functionality
document.getElementById('shareReportBtn')?.addEventListener('click', () => {
    if (navigator.share) {
        navigator.share({
            title: 'My Health Report',
            text: 'Check out my health report analysis',
            url: window.location.href
        }).catch(err => console.log('Error sharing:', err));
    } else {
        alert('Share feature not supported in your browser. You can copy the URL to share.');
    }
});

// Store report data when analysis is complete
function storeReportData(data) {
    currentReportData = data;
    
    // Add a welcome message about the report
    if (chatbotMessages.children.length === 1) {
        setTimeout(() => {
            addMessage(
                `Great! I've analyzed your medical report with ${data.results.length} tests. Feel free to ask me any questions about your results!`,
                'bot'
            );
        }, 1000);
    }
}
