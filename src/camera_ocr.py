import cv2
import pytesseract
import requests
import threading
import csv
import os
from datetime import datetime

# --- CONFIGURATION ---
# Windows users: Uncomment and set your path
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

CSV_FILE = 'scanned_cards.csv'
ZOOM_FACTOR = 1  # 2x Zoom. Increase to 3 if you need to hold the card even further back.

# Global variables
current_card_info = {
    "name": "Scanning...",
    "price": "...",
    "set": "",
    "found": False
}
last_searched_text = ""
scanned_list = []
recent_save_message = ""

# Initialize CSV
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Card Name", "Set", "Price"])

def save_to_csv(card_data):
    global recent_save_message, scanned_list
    if scanned_list and scanned_list[-1]['name'] == card_data['name']:
        return
    scanned_list.append(card_data)
    try:
        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                card_data['name'],
                card_data['set'],
                card_data['price']
            ])
        recent_save_message = f"ADDED: {card_data['name']}"
        print(f"Saved: {card_data['name']}")
    except Exception as e:
        print(f"Error saving to CSV: {e}")

def fetch_card_data(ocr_text):
    global current_card_info
    query = ocr_text.replace('\n', ' ').strip()
    try:
        url = f"https://api.scryfall.com/cards/named?fuzzy={query}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            name = data.get('name', 'Unknown')
            set_name = data.get('set_name', 'Unknown')
            prices = data.get('prices', {})
            price = prices.get('usd')
            if not price:
                price = prices.get('usd_foil', 'N/A')
            current_card_info = {
                "name": name,
                "price": f"${price}",
                "set": set_name,
                "found": True
            }
            save_to_csv(current_card_info)
        else:
            current_card_info["found"] = False
    except Exception as e:
        print(f"Connection Error: {e}")

def main():
    global last_searched_text, recent_save_message
    
    cap = cv2.VideoCapture(0)
    
    # Force High Res
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    
    # Manual Focus Settings
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 0) 
    current_focus = 25 # Start slightly further out
    cap.set(cv2.CAP_PROP_FOCUS, current_focus)

    frame_counter = 0
    OCR_FREQUENCY = 15 

    print("Align card title in the BLUE box.")
    print(f"Digital Zoom Active: {ZOOM_FACTOR}x")
    print("Hold the card FURTHER AWAY until it is sharp.")

    while True:
        ret, raw_frame = cap.read()
        if not ret:
            break

        # --- DIGITAL ZOOM LOGIC ---
        # 1. Get dimensions
        h, w, _ = raw_frame.shape
        
        # 2. Calculate crop size (center of image)
        new_h, new_w = int(h / ZOOM_FACTOR), int(w / ZOOM_FACTOR)
        
        # 3. Calculate start/end points
        y1_crop = (h - new_h) // 2
        x1_crop = (w - new_w) // 2
        
        # 4. Crop and Resize back to full screen
        cropped_frame = raw_frame[y1_crop:y1_crop+new_h, x1_crop:x1_crop+new_w]
        frame = cv2.resize(cropped_frame, (w, h), interpolation=cv2.INTER_LINEAR)

        # --- REST OF THE CODE IS THE SAME ---
        height, width, _ = frame.shape
        
        box_w, box_h = 400, 60
        x1 = (width - box_w) // 2
        y1 = (height - box_h) // 2 - 100
        x2, y2 = x1 + box_w, y1 + box_h
        info_y = y2 + 20

        color = (0, 255, 0) if current_card_info['found'] else (255, 0, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, "Align Title Here", (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        frame_counter += 1

        if frame_counter % OCR_FREQUENCY == 0:
            roi = frame[y1:y2, x1:x2]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            kernel = cv2.getGaussianKernel(9, 1.5)
            gray = cv2.filter2D(gray, -1, kernel)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            config = r'--psm 7'
            text = pytesseract.image_to_string(thresh, config=config).strip()

            if len(text) > 3 and text.lower() != last_searched_text.lower():
                last_searched_text = text
                t = threading.Thread(target=fetch_card_data, args=(text,), daemon=True)
                t.start()

        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, info_y), (x2, info_y + 130), (0, 0, 0), -1)
        alpha = 0.6
        frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

        if current_card_info['found']:
            cv2.putText(frame, current_card_info['name'], (x1 + 10, info_y + 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, current_card_info['set'], (x1 + 10, info_y + 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.putText(frame, current_card_info['price'], (x2 - 100, info_y + 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        else:
            cv2.putText(frame, "Scanning...", (x1 + 10, info_y + 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

        cv2.putText(frame, f"Total Scanned: {len(scanned_list)}", (x1 + 10, info_y + 90), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
        
        cv2.putText(frame, f"Zoom: {ZOOM_FACTOR}x | Focus: {current_focus}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

        if recent_save_message:
            cv2.putText(frame, recent_save_message, (x1 + 10, info_y + 120), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 255, 50), 1)

        cv2.imshow('MTG Auto-Lister', frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('['):
            current_focus = max(0, current_focus - 5)
            cap.set(cv2.CAP_PROP_FOCUS, current_focus)
        elif key == ord(']'):
            current_focus = min(255, current_focus + 5)
            cap.set(cv2.CAP_PROP_FOCUS, current_focus)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()