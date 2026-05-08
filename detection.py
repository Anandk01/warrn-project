import cv2
from ultralytics import YOLO
import math
import time

# Load model (using standard YOLOv8 nano for speed)
# It will download 'yolov8n.pt' automatically on first run
model = YOLO("yolov8n.pt")

# Target classes we care about (COCO dataset indices)
# 15: cat, 16: dog, 17: horse, 18: sheep, 19: cow, 20: elephant, 21: bear, 22: zebra, 23: giraffe
TARGET_CLASSES = [15, 16, 17, 18, 19, 20, 21, 22, 23]

# Vehicle classes for collision detection
# 2: car, 3: motorcycle, 5: bus, 7: truck
VEHICLE_CLASSES = [2, 3, 5, 7]
CLASS_NAMES = model.names


# Rate limiting for auto-reporting
last_report_time = 0
REPORT_COOLDOWN = 15  # Seconds between reports

def generate_frames(source=0, report_callback=None):
    global last_report_time
    cap = cv2.VideoCapture(source)
    
    # Check if camera opened successfully
    if not cap.isOpened():
        print(f"Error: Could not open video stream from source: {source}")
        return
        
    # Reduce resolution for speed
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while True:
        success, frame = cap.read()
        if not success:
            if isinstance(source, str):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            break
        
        # Resize frame for faster inference if it's too big
        if frame.shape[1] > 640:
             frame = cv2.resize(frame, (640, 480))

        # Run YOLOv8 inference
        results = model(frame, stream=True, verbose=False)
        
        # Lists to store boxes for collision detection
        animal_boxes = []
        vehicle_boxes = []
        
        # First pass: Collect all relevant detections
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = math.ceil((box.conf[0] * 100)) / 100
                
                # Get coords
                x1, y1, x2, y2 = box.xyxy[0]
                coords = (int(x1), int(y1), int(x2), int(y2))
                
                if cls in TARGET_CLASSES:
                    animal_boxes.append({'coords': coords, 'label': CLASS_NAMES[cls], 'conf': conf})
                elif cls in VEHICLE_CLASSES:
                    vehicle_boxes.append({'coords': coords, 'label': CLASS_NAMES[cls], 'conf': conf})

        # Second pass: Check collisions and draw
        accident_detected = False
        accident_info = ""
        
        # Draw vehicles (Blue)
        for v in vehicle_boxes:
            x1, y1, x2, y2 = v['coords']
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2) # Blue for vehicles
            
        # Check interactions and draw animals
        for a in animal_boxes:
            ax1, ay1, ax2, ay2 = a['coords']
            is_collision = False
            
            # Check overlap with any vehicle
            for v in vehicle_boxes:
                vx1, vy1, vx2, vy2 = v['coords']
                
                # Simple intersection check
                dx = min(ax2, vx2) - max(ax1, vx1)
                dy = min(ay2, vy2) - max(ay1, vy1)
                
                if (dx >= 0) and (dy >= 0):
                    is_collision = True
                    break
            
            # Color: Red if accident, Green if safe
            color = (0, 0, 255) if is_collision else (0, 255, 0)
            status = "ACCIDENT!" if is_collision else ""
            
            # Draw Animal Box
            cv2.rectangle(frame, (ax1, ay1), (ax2, ay2), color, 2)
            
            # Label
            label = f"{a['label']} {status}"
            t_size = cv2.getTextSize(label, 0, fontScale=0.5, thickness=1)[0]
            c2 = ax1 + t_size[0], ay1 - t_size[1] - 3
            cv2.rectangle(frame, (ax1, ay1), c2, color, -1, cv2.LINE_AA)
            cv2.putText(frame, label, (ax1, ay1 - 2), 0, 0.5, (255, 255, 255), thickness=1, lineType=cv2.LINE_AA)

            if is_collision:
                accident_detected = True
                accident_info = f"{a['label']} Hit"
        
        if accident_detected:
             cv2.putText(frame, "ACCIDENT DETECTED!", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
             
             # Auto-Reporting Hook
             if report_callback:
                 current_time = time.time()
                 if current_time - last_report_time > REPORT_COOLDOWN:
                     # Identify what was hit for the report
                     success = report_callback(frame, accident_info)
                     if success:
                         last_report_time = current_time
        
        # Display "REPORT SENT" status if within cooldown period
        time_since_report = time.time() - last_report_time
        if time_since_report < 5:  # Show for 5 seconds
            cv2.putText(frame, "REPORT SENT!", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)

        # Encode frame to JPEG with lower quality for speed
        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        frame = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
               
    cap.release()
