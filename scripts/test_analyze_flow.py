import sys
import os
import httpx
import time
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.db import get_conn

def setup_test_data():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Ensure persona exists
            cur.execute("INSERT INTO entidades.personas_objetivo (id_persona, nombre_completo) VALUES (1, 'Test Person') ON CONFLICT (id_persona) DO NOTHING")
            
            # Insert or get identity
            cur.execute("""
                INSERT INTO entidades.identidades_digitales (id_persona, plataforma, usuario_o_url, estado)
                VALUES (1, 'x', 'jvgador9', 'pendiente')
                ON CONFLICT (id_persona, plataforma, usuario_o_url) 
                DO UPDATE SET estado = 'pendiente'
                RETURNING id_identidad
            """)
            row = cur.fetchone()
            id_identidad = row['id_identidad']
            conn.commit()
            print(f"Test identity ID: {id_identidad}")
            return id_identidad
    finally:
        conn.close()

def trigger_analysis(id_identidad):
    url = "http://localhost:8000/analyze/start"
    payload = {
        "id_identidad": id_identidad,
        "context": {
            "id_usuario": 1,
            "id_caso": 100,
            "id_organizacion": 1,
            "nombre_organizacion": "fiscalia",
            "nombre_area": "inteligencia",
            "nombre_departamento": "cibernetica"
        },
        "max_photos": 5,
        "headless": True,
        "max_depth": 2
    }
    
    print(f"Sending request to {url}...")
    try:
        response = httpx.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Request failed: {e}")
        return False

if __name__ == "__main__":
    print("Setting up test data...")
    id_identidad = setup_test_data()
    
    print("Triggering analysis...")
    success = trigger_analysis(id_identidad)
    
    if success:
        print("\nAnalysis triggered successfully. The background task is running.")
        print("Please wait a few moments and then run 'python scripts/verify_ftp_content.py' to check for images.")
