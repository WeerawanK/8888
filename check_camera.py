import cv2

for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f"Index {i}: เปิดกล้องได้")
        cap.release()
    else:
        print(f"Index {i}: ไม่มีกล้อง")