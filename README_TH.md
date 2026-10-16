# Agibot D1 Edu: Live object detection ผ่าน SSH

ตัวอย่าง Python: RTSP → OpenCV → YOLOv8 nano → MJPEG ใน browser
ใช้ตรวจจับวัตถุทั่วไป เช่น คน เก้าอี้ ขวด ตามคลาสของโมเดลสำเร็จรูป
ไม่มีคำสั่งควบคุมการเคลื่อนที่ของหุ่น

## ข้อมูลที่ยืนยันได้ และสิ่งที่ต้องลองกับหุ่นจริง

- เอกสารกล้องใน repo ระบุ `rtsp://192.168.234.1:8554/test`
- คู่มือ deployment ระบุ SSH user `firefly`, Wi-Fi IP `192.168.234.1` และ Ethernet IP `192.168.168.168`
- ใช้ username/IP/password จริงของเครื่องหากเคยเปลี่ยนไว้
- ยังไม่ได้ทดสอบกับหุ่นของคุณ จึงต้องยืนยันว่า firmware นี้เปิด RTSP service ดังกล่าวอยู่
- ยังไม่มี ROS 2 subscriber ในตัวอย่างนี้ รอชื่อ topic, message type และ QoS จากเครื่องจริงก่อน
- ค่าเริ่มต้นใช้ CPU ไม่ได้ใช้ NPU โดยอัตโนมัติ ประสิทธิภาพขึ้นกับฮาร์ดแวร์

## วิธี A: รันบนหุ่น เปิดภาพบนคอมพิวเตอร์

แตก ZIP แล้วเปิด terminal ของคอมพิวเตอร์ในโฟลเดอร์ที่มี `agibot-d1-detection`
คัดลอกโฟลเดอร์ขึ้นหุ่น:

```bash
scp -r agibot-d1-detection firefly@192.168.234.1:~/
ssh -o ExitOnForwardFailure=yes -L 8080:127.0.0.1:8080 firefly@192.168.234.1
```

คำสั่งต่อไปนี้รันใน SSH บนหุ่น:

```bash
cd ~/agibot-d1-detection
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# ทดสอบ feed ก่อน ยังไม่โหลดโมเดล
python detect_web.py --source rtsp://192.168.234.1:8554/test --preview-only
```

เปิด browser **บนคอมพิวเตอร์** ที่ http://127.0.0.1:8080
เมื่อเห็นภาพแล้ว กด Ctrl+C ใน SSH และเริ่ม detection:

```bash
python detect_web.py --source rtsp://192.168.234.1:8554/test --model yolov8n.pt --device cpu --imgsz 320
```

เก็บหน้าต่าง SSH ไว้ขณะดูภาพ ถ้า IP หุ่นต่างออกไปให้เปลี่ยนทุกจุดให้ตรงกัน
หากขาด venv ให้ติดตั้ง `python3-venv` ตามระบบ Ubuntu ของหุ่นก่อน
การติดตั้ง dependency และโหลดโมเดลครั้งแรกต้องใช้อินเทอร์เน็ต
ถ้า PyTorch ไม่มี wheel ที่ตรงกับ Python/ARM ของหุ่น ให้ใช้วิธี B ก่อน
ห้ามแทนที่ PyTorch/OpenCV ของระบบหุ่นเพียงเพื่อรัน sample นี้; ใช้ venv แยก

## วิธี B: ให้คอมพิวเตอร์รัน YOLO ดึงกล้องผ่าน SSH

เหมาะเมื่อ CPU บนหุ่นช้า หรือติดตั้ง PyTorch บนหุ่นไม่ได้
เปิด terminal แรกบนคอมพิวเตอร์ แล้วคงไว้:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 18554:192.168.234.1:8554 firefly@192.168.234.1
```

เปิด PowerShell อีกหน้าต่างในโฟลเดอร์ sample บน Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe detect_web.py --source rtsp://127.0.0.1:18554/test --preview-only
```

เปิด http://127.0.0.1:8080 เมื่อเห็นภาพแล้ว Ctrl+C และรัน:

```powershell
.\.venv\Scripts\python.exe detect_web.py --source rtsp://127.0.0.1:18554/test --model yolov8n.pt --device cpu
```

บน Linux/macOS ใช้ `python3 -m venv .venv`, `source .venv/bin/activate` แล้วใช้ `python` แทน path ของ Windows
โค้ดบังคับ RTSP over TCP เพื่อให้ทั้งข้อมูลควบคุมและภาพผ่าน SSH tunnel
หากอยู่เครือข่ายเดียวกันและต้องการต่อโดยตรง ใช้ `--source rtsp://192.168.234.1:8554/test`

## หุ่นไม่มีอินเทอร์เน็ต

ใช้วิธี B ได้โดยติดตั้งโมเดลและ dependency บนคอมพิวเตอร์ที่มีอินเทอร์เน็ตก่อน
หากจะรันบนหุ่นและติดตั้ง dependency แล้ว ให้ดาวน์โหลดน้ำหนักบนคอมพิวเตอร์:

```bash
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
scp yolov8n.pt firefly@192.168.234.1:~/agibot-d1-detection/
```

## ตรวจสอบกล้องและ ROS 2 บนหุ่น

คำสั่งต่อไปนี้ใช้ดูข้อมูล ไม่แก้ไขการตั้งค่าหุ่น:

```bash
uname -m
python3 --version
ss -lnt | grep ':8554'
ls -l /dev/video*
printenv ROS_DISTRO
ros2 topic list -t
ros2 node list
```

ถ้าพบ image topic ให้แทน `/ACTUAL_IMAGE_TOPIC` ด้วยชื่อจริง:

```bash
ros2 topic info -v /ACTUAL_IMAGE_TOPIC
```

หาก `ros2` ไม่พบ ให้ใช้ terminal/environment ที่ source ROS และ workspace ของหุ่นไว้แล้ว
ถ้าหุ่นมี ffprobe สามารถยืนยัน RTSP ได้ด้วย:

```bash
ffprobe -v error -rtsp_transport tcp -show_streams rtsp://192.168.234.1:8554/test
```

ส่งผล `ros2 topic list -t`, `ros2 node list`, `ros2 topic info -v` ของ image topic กลับมาเพื่อเพิ่ม ROS adapter ให้ตรง firmware
ไม่ต้องเปลี่ยน sdk_config.yaml หรือรีสตาร์ต motion control เพื่อใช้ sample กล้องนี้

## ตัวเลือกและการแก้ปัญหา

- `--preview-only`: ดูภาพอย่างเดียว ใช้แยกปัญหา feed ออกจากโมเดล
- `--conf 0.5`: เพิ่มเกณฑ์ confidence
- `--imgsz 320`: ขนาด inference เล็กลงช่วยลดภาระ; ลอง 640 หากต้องการรายละเอียดเพิ่ม
- `--device cpu`: ค่าเริ่มต้น; `--device 0` ใช้ได้เมื่อมี CUDA และ PyTorch ที่รองรับ
- `--source /dev/video0`: ใช้ได้เฉพาะเมื่อยืนยันแล้วว่าเป็นกล้อง V4L2 ที่อ่านได้และไม่ถูก process อื่นใช้อยู่
- `--model /path/to/best.pt`: โมเดลตรวจจับที่ฝึกเอง
- `/health`: สถานะกล้อง/โมเดล อายุเฟรม และเวลา processing
- `stale: true`: ไม่มีผลใหม่เกิน 5 วินาที ภาพที่ browser ค้างอยู่ไม่ใช่ภาพปัจจุบัน
- หาก camera connected แต่ detector error ดูข้อความใน terminal และ `/health`
- หากภาพไม่มา ตรวจ IP, RTSP service, tunnel และทดลอง preview-only ก่อน
- หาก port 8080 ถูกใช้ ให้เปลี่ยน `--port` และ SSH forward ให้ตรงกัน

เซิร์ฟเวอร์นี้เป็น sample สำหรับดูผ่าน localhost/SSH และปิดด้วย Ctrl+C
อ่านกล้องและ inference คนละ thread โดยเก็บเฉพาะเฟรมล่าสุด; เวลา processing ไม่ใช่ end-to-end latency
dependency กำหนดช่วงเวอร์ชัน ยังไม่ใช่ lockfile ที่รับรองกับ firmware ของหุ่น

## แหล่งอ้างอิง

- กล้อง: https://github.com/AgibotTech/agibot_D1_Edu-Ultra/blob/main/docs/video.md
- SSH/network: https://github.com/AgibotTech/agibot_D1_Edu-Ultra/blob/main/docs/deploy.md
- YOLO API: https://docs.ultralytics.com/modes/predict/

ตรวจ syntax และทดสอบการส่งต่อเฟรมในสภาพแวดล้อมพัฒนาแล้ว
ยังไม่ได้ทดสอบ RTSP จริง, inference ด้วยน้ำหนักจริง หรือความเร็วบน Agibot D1 Edu

## อัปเดต: Dashboard นับวัตถุบนคอมพิวเตอร์

ใช้วิธี B ด้านบน: รัน Python/YOLO บน Windows และรับ RTSP จากหุ่นผ่าน SSH
Dashboard แสดง In frame now, Total tracks this session และยอดสะสมแยกประเภท
ใช้ BoT-SORT ผ่าน Ultralytics model.track(persist=True) ไม่บวกยอดทุกเฟรม
Total เป็นจำนวน tracking IDs ไม่ใช่การยืนยันจำนวนวัตถุจริงที่ไม่ซ้ำตลอดเวลา
วัตถุถูกบัง ออกจากภาพ กล้องเคลื่อนเร็ว หรือ reconnect อาจทำให้ยอดคลาดเคลื่อน
เมื่อ reconnect เริ่ม namespace การนับใหม่และยังเก็บยอดเก่า จึงอาจนับวัตถุเดิมอีกครั้ง
ประเภทสะสมใช้ประเภทตอนพบ ID ครั้งแรก ยอดในเฟรมใช้ผลล่าสุด
กด Ctrl+C เพื่อบันทึก counts.json ในโฟลเดอร์ที่รันโปรแกรม หรือกำหนด --summary PATH
เปิดโปรแกรมใหม่เริ่มยอดที่ศูนย์ การ refresh browser ไม่ล้างยอด
ยังไม่ได้เชื่อม ROS image topic เพราะยังไม่พบ topic ของกล้องจริง
อ้างอิง: https://docs.ultralytics.com/modes/track/
ตัวอย่างนับผ่านเส้น/พื้นที่ (ยังไม่ได้เพิ่มใน sample นี้): https://docs.ultralytics.com/guides/object-counting/
