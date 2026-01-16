#!/usr/bin/env python3
"""
VIN Decoder - Flask Backend
Reads VIN from images and decodes vehicle information,
estimates used vehicle value, and stores upload history.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import anthropic
import requests
from datetime import datetime
import re
import json

app = Flask(__name__)
CORS(app)

DB_FILE = 'db.json'  # simple storage for upload history


@app.route('/')
def index():
    """Serve the frontend HTML file"""
    return send_from_directory('.', 'vin-decoder.html')


@app.route('/api/decode-vin', methods=['POST'])
def decode_vin():
    """
    Process uploaded VIN image:
    1. Use Claude Vision to read the VIN
    2. Use NHTSA API to decode vehicle details
    3. Estimate vehicle used value
    4. Save to history
    """
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': 'No image provided'}), 400

        image_data = data['image']
        if ',' in image_data:
            header, image_data = image_data.split(',', 1)
            media_type = 'image/jpeg'
            if 'png' in header:
                media_type = 'image/png'
            elif 'webp' in header:
                media_type = 'image/webp'
        else:
            media_type = 'image/jpeg'

        # --- Step 1: Extract VIN using Claude Vision ---
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
                            "source": {"type": "base64", "media_type": media_type, "data": image_data},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Look at this VIN plate image and extract the 17-character Vehicle Identification "
                                "Number (VIN). Respond with ONLY the 17-character VIN (no extra text)."
                            ),
                        },
                    ],
                }
            ],
        )

        vin = message.content[0].text.strip().upper()

        if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', vin):
            return jsonify({'success': False, 'error': f'Invalid VIN detected: {vin}'}), 400

        # --- Step 2: Decode VIN using NHTSA Extended API ---
        nhtsa_url = f'https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/{vin}?format=json'
        nhtsa_resp = requests.get(nhtsa_url)
        vin_data = nhtsa_resp.json().get('Results', [{}])[0]

        make = vin_data.get('Make', 'Unknown')
        model = vin_data.get('Model', 'Unknown')
        year = vin_data.get('ModelYear', 'Unknown')
        drive_type = vin_data.get('DriveType', 'Unknown')
        engine = vin_data.get('DisplacementL') or vin_data.get('EngineModel', 'Unknown')
        manufactured_in = f"{vin_data.get('PlantCity', '')} {vin_data.get('PlantCountry', '')}".strip()
        vehicle_type = vin_data.get('VehicleType', 'Unknown')
        body_class = vin_data.get('BodyClass', 'Unknown')

        # --- Step 3: Compute vehicle age ---
        current_year = datetime.now().year
        age_num = current_year - int(year) if year.isdigit() else None
        age = f"{age_num} Years" if age_num else "Unknown"

        # --- Step 4: Estimate used price range ---
        price_low, price_high = estimate_price_range(make, model, year)
        est_price = f"${price_low:,} - ${price_high:,}" if price_low else "N/A"

        details = {
            "Make": make,
            "Model": model,
            "Year": year,
            "Drive Type": drive_type,
            "Engine (L)": engine if engine else "Unknown",
            "Manufactured In": manufactured_in or "Unknown",
            "Vehicle Type": vehicle_type,
            "Body Class": body_class,
            "Age": age,
            "Estimated Used Price": est_price
        }

        # --- Step 5: Save record to history ---
        save_to_history(vin, details)

        return jsonify({'success': True, 'vin': vin, 'details': details})

    except anthropic.APIError as e:
        return jsonify({'success': False, 'error': f'Claude API error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@app.route('/api/history')
def history():
    """Return all saved VIN decode history"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f:
            records = json.load(f)
        return jsonify(records)
    return jsonify([])


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})


# --- Utility functions ---------------------------------------------------

def estimate_price_range(make, model, year):
    """
    Option A: Use MarketCheck API if available via environment variable.
    Option B: Estimate using simple depreciation curve if no API key.
    """
    key = os.environ.get('MARKETCHECK_KEY')
    try:
        if key:
            url = (
                f"https://api.marketcheck.com/v2/depreciation?"
                f"api_key={key}&year={year}&make={make}&model={model}"
            )
            resp = requests.get(url)
            if resp.ok:
                data = resp.json()
                price_range = data.get('price_range')
                if price_range:
                    return int(price_range['min']), int(price_range['max'])
    except Exception:
        pass

    # --- fallback simple formula ---
    if not year.isdigit():
        return None, None
    age = datetime.now().year - int(year)
    base_price = 35000  # you can adjust or vary by class
    value = base_price * (0.85 ** age)
    return round(value * 0.8), round(value * 1.2)


def save_to_history(vin, details):
    """Save each decoded VIN result locally"""
    record = {
        'vin': vin,
        'timestamp': datetime.now().isoformat(),
        'details': details
    }
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r+') as f:
            data = json.load(f)
            data.insert(0, record)
            f.seek(0)
            json.dump(data[:50], f, indent=2)  # keep last 50 records
    else:
        with open(DB_FILE, 'w') as f:
            json.dump([record], f, indent=2)


# --- App Runner -----------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚗 Starting VIN Decoder...")
    print(f"📍 Server running on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port)
