#!/usr/bin/env python3
"""
Wordle Score Calculator - Vision AI Backend
Uses Claude Vision API to analyze Wordle boards
Much simpler and more accurate than OCR!
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import base64
import json
import anthropic

app = Flask(__name__, static_folder='.')
CORS(app)

# Scoring rules
SCORING_RULES = """
SCORING RULES:
- Each letter is scored only once based on when it first appears
- Row 1: Green = 8 pts, Yellow = 4 pts
- Row 2: Green = 7 pts, Yellow = 3 pts
- Row 3: Green = 6 pts, Yellow = 2 pts
- Row 4: Green = 5 pts, Yellow = 1 pt
- Row 5+: Green = 4 pts, Yellow = 0 pts
- Conversion bonus: +1 pt when a yellow letter becomes green later
- Gray letters (not in the word) are not scored

EXAMPLE:
If 'L' appears as green in row 1 = 8 points
If 'T' appears as yellow in row 1, then green in row 2 = 4 + 1 = 5 points total
"""

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('.', 'wordle_scorer_vision.html')

@app.route('/api/score', methods=['POST'])
def score_wordle():
    """
    Process uploaded Wordle image using Claude Vision
    """
    try:
        data = request.get_json()
        
        if not data or 'image' not in data:
            return jsonify({
                'success': False,
                'error': 'No image provided'
            }), 400
        
        # Get base64 image data
        image_data = data['image']
        
        # Remove data URL prefix if present
        if ',' in image_data:
            header, image_data = image_data.split(',', 1)
            # Determine media type from header
            if 'jpeg' in header or 'jpg' in header:
                media_type = 'image/jpeg'
            elif 'png' in header:
                media_type = 'image/png'
            elif 'webp' in header:
                media_type = 'image/webp'
            elif 'gif' in header:
                media_type = 'image/gif'
            else:
                media_type = 'image/jpeg'  # default
        else:
            media_type = 'image/jpeg'
        
        # Call Claude Vision API
        # Note: In production, you'd use actual API key from environment
        # For now, this will work in the Claude.ai Artifacts environment
        client = anthropic.Anthropic()
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"""Analyze this Wordle game board image and calculate the score.

{SCORING_RULES}

Please respond ONLY with a JSON object (no markdown, no explanation) in this exact format:
{{
    "success": true,
    "totalScore": <number>,
    "letters": [
        {{
            "char": "<letter>",
            "row": <row number>,
            "color": "<green/yellow/gray>",
            "points": <base points>,
            "conversion": <true/false>,
            "totalPoints": <points including conversion>
        }}
    ],
    "debug": {{
        "rows": ["<word1>", "<word2>", "<word3>"]
    }}
}}

Make sure to:
1. Identify all letters and their colors in each row
2. Track when each letter FIRST appears
3. Check for yellow→green conversions
4. Calculate points correctly
5. Only count each letter once (when it first appears)"""
                        }
                    ],
                }
            ],
        )
        
        # Parse Claude's response
        response_text = message.content[0].text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        result = json.loads(response_text)
        
        return jsonify(result)
    
    except anthropic.APIError as e:
        return jsonify({
            'success': False,
            'error': f'API error: {str(e)}'
        }), 500
    except json.JSONDecodeError as e:
        return jsonify({
            'success': False,
            'error': f'Failed to parse response: {str(e)}',
            'raw_response': response_text
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error: {str(e)}'
        }), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Starting Wordle Scorer with Vision AI...")
    print(f"📍 Server running on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port)
