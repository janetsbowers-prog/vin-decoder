#!/usr/bin/env python3
"""
VIN Decoder - Flask Backend
Reads VIN from images and decodes vehicle information
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import anthropic
import requests

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    # Serve HTML file at root
    return send_from_directory('.', 'vin-decoder.html')

@app.route('/api/decode-vin', methods=['POST'])
def decode_vin():
    """
    Process uploaded VIN image
    1. Use Claude Vision to read the VIN
    2. Use NHTSA API to decode vehicle details
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
            if 'jpeg' in header or 'jpg' in header:
                media_type = 'image/jpeg'
            elif 'png' in header:
                media_type = 'image/png'
            elif 'webp' in header:
                media_type = 'image/webp'
            else:
                media_type = 'image/jpeg'
        else:
            media_type = 'image/jpeg'
        
        # Step 1: Read VIN with Claude Vision
        client = anthropic.Anthropic()
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
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
                            "text": """Look at this VIN plate image and extract the 17-character Vehicle Identification Number (VIN).

The VIN is a sequence of exactly 17 characters (numbers and capital letters, but NOT the letters I, O, or Q).

Respond with ONLY the 17-character VIN, nothing else. No explanation, no formatting, just the VIN.

Example format: 1HGBH41JXMN109186"""
                        }
                    ],
                }
            ],
        )
        
        # Extract VIN from response
        vin = message.content[0].text.strip().upper()
        
        # Validate VIN format (17 chars, no I/O/Q)
        import re
        if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', vin):
            return jsonify({
                'success': False,
                'error': f'Invalid VIN format detected: {vin}. Please try again with a clearer photo.'
            }), 400
        
        # Step 2: Decode VIN with NHTSA Extended API
nhtsa_url = f'https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/{vin}?format=json'
nhtsa_response = requests.get(nhtsa_url)
vin_data = nhtsa_response.json().get('Results', [{}])[0]

# Extract structured fields
make = vin_data.get('Make', 'Unknown')
model = vin_data.get('Model', 'Unknown')
year = vin_data.get('ModelYear', 'Unknown')
drive_type = vin_data.get('DriveType', 'Unknown')
engine = vin_data.get('DisplacementL', 'Unknown') or vin_data.get('EngineModel', 'Unknown')
manufactured_in = f"{vin_data.get('PlantCity', '')} {vin_data.get('PlantCountry', '')}".strip()
vehicle_type = vin_data.get('VehicleType', 'Unknown')
body_class = vin_data.get('BodyClass', 'Unknown')

# Calculate vehicle age
from datetime import datetime
current_year = datetime.now().year
age = f"{current_year - int(year)} Years" if year.isdigit() else "Unknown"

details = {
    "Make": make,
    "Model": model,
    "Year": year,
    "Drive Type": drive_type,
    "Engine (L)": engine,
    "Manufactured In": manufactured_in or "Unknown",
    "Vehicle Type": vehicle_type,
    "Body Class": body_class,
    "Age": age
}
        
        return jsonify({
            'success': True,
            'vin': vin,
            'details': details
        })
    
    except anthropic.APIError as e:
        return jsonify({
            'success': False,
            'error': f'API error: {str(e)}'
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
    print("🚗 Starting VIN Decoder...")
    print(f"📍 Server running on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port)
