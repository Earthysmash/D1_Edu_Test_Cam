# D1 EDU: ตรวจจับคนและส่งคำสั่งเดินจริง

รุ่นนี้เพิ่ม `robot_follow.py` ซึ่งเรียก SDK ทางการ `HighLevel.move(vx, vy, yaw_rate)` จริง
PC ทำ YOLO; โปรแกรมบนหุ่นทำ motion control ผ่าน SDK Linux Python 3.10
รันแค่ `live_demo.py` อย่างเดียวยังไม่ส่งคำสั่งเดิน ต้องเปิดโปรแกรมบนหุ่นด้วย

สถานะการตรวจสอบ: ทดสอบ logic/API ด้วย SDK จำลองแล้ว แต่ยังไม่ได้ทดสอบกับ D1 จริง
เครื่องพัฒนาเชื่อมต่อ SSH ไป 192.168.234.1 ไม่สำเร็จ จึงยังไม่ได้ติดตั้งหรือแก้ config บนหุ่น
การตอบรับ SDK ไม่ใช่หลักฐานว่าหุ่นเคลื่อนที่จริง ต้องตรวจการทำงานบนหุ่น

## 1. เตรียมครั้งแรก บน PC

เปิด PowerShell ในโฟลเดอร์ repo ที่อัปเดตแล้ว ใช้ path ของ clone ของคุณ:

```powershell
cd "C:\Users\UsEr\Documents\Codex\2026-10-22\fo\outputs\D1_Edu_Test_Cam"
git pull --ff-only
python -m pip install -r requirements.txt
# ทำตอน PC มีอินเทอร์เน็ต: ดาวน์โหลด SDK ทางการที่ตรวจสอบเวอร์ชันไว้
.\prepare_robot.ps1 -DownloadOnly
# เปลี่ยนไปเชื่อม Wi-Fi ของ D1 แล้วอัปโหลด (จะขอรหัสผ่าน SSH)
.\prepare_robot.ps1
```

สคริปต์อัปโหลดไป `/home/firefly/d1-follow` และตรวจ Python / SDK / config โดยไม่สั่งเดิน
ถ้า PowerShell บล็อกสคริปต์ตามนโยบายเครื่อง ให้ทำตามนโยบายของเครื่องนั้น หรืออัปโหลด
`robot_follow.py`, `robot_check.py`, `run_follow.sh` ด้วย `scp` และวาง SDK
`lib/zsl-1` ไว้ใน `/home/firefly/d1-follow/sdk/lib/zsl-1` ด้วยตนเอง

SDK ที่ pin: `AgibotTech/agibot_D1_Edu-Ultra` commit
`b5fe0a86094507238944ad118721376a98615ac0` (ZSL-1 / D1 EDU)
หาก firmware บนหุ่นไม่เข้ากัน ต้องใช้ SDK รุ่นที่ผู้ผลิตระบุให้ตรง firmware

## 2. ตรวจ config บนหุ่น (ครั้งแรก)

ถ้า precheck แจ้งค่าไม่ตรง ให้ SSH เข้าไปตรวจ:

```bash
cat /opt/export/config/sdk_config.yaml
```

ตามคู่มือ SDK แบบรันบนตัวหุ่น Wi-Fi IP เดิม ค่าที่ต้องใช้คือ:

```yaml
target_ip: "192.168.234.1"
target_port: 43988
```

ถ้าต้องแก้ สำรองก่อน แล้วแก้เฉพาะสองฟิลด์นี้ เก็บฟิลด์อื่นไว้:

```bash
sudo cp -an /opt/export/config/sdk_config.yaml /opt/export/config/sdk_config.yaml.before-follow
sudo nano /opt/export/config/sdk_config.yaml
```

หลังแก้ต้องรีสตาร์ตหุ่นตามคู่มือผู้ผลิต ขณะหุ่นหยุดและวางในท่าที่เหมาะสม
สคริปต์เราไม่แก้ config หรือรีบูตให้เอง และไม่แก้ startup/network ของ motion service
หาก Python ไม่ใช่ 3.10 หรือ import `.so` ไม่ผ่าน ต้องแก้ runtime ให้ตรง SDK ก่อน

## 3. เปิด 3 terminal

**Terminal 1 บน PC: tunnel ภาพและผลตรวจจับ**

หยุด tunnel เก่าด้วย Ctrl+C ก่อน เพื่อไม่ให้ชนพอร์ต แล้วรัน:

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=2 -o ServerAliveCountMax=3 -L 18554:127.0.0.1:8554 -R 18080:127.0.0.1:8080 firefly@192.168.234.1
```

`-L` ส่งกล้องมาที่ PC; `-R` ให้โปรแกรมบนหุ่นอ่าน dashboard ของ PC ผ่าน loopback
ไม่ได้เปิด motion server สู่เครือข่ายภายนอก กล้องบนหุ่นต้องเปิดอยู่แล้ว

**Terminal 2 บน PC: ตรวจจับเฉพาะคนให้เร็วขึ้น**

```powershell
cd "C:\Users\UsEr\Documents\Codex\2026-10-22\fo\outputs\D1_Edu_Test_Cam"
python live_demo.py --follow --imgsz 320
```

เปิด http://127.0.0.1:8080 ต้องเห็นคนและกรอบถูกต้องก่อนเริ่ม motion
`--follow` ปิดโมเดล event ตัวที่สอง ลด latency; ถ้าตรวจไม่แม่นพอเพิ่ม imgsz เป็น 640
แต่ข้อมูลที่เก่าเกิน 1 วินาทีจะถูกหยุด ไม่เพิ่ม timeout เพื่อกลบปัญหาภาพช้า

**Terminal 3: SSH ไปเปิดส่วนควบคุมจริง**

```powershell
ssh firefly@192.168.234.1
```

บนหุ่น ตรวจโดยยังไม่เคลื่อนไหว:

```bash
bash /home/firefly/d1-follow/run_follow.sh --check
```

ใช้รีโมตทำให้หุ่นยืน จากนั้นเลือกสิทธิ์ควบคุม SDK ตามคู่มือรุ่น/firmware
คู่มือผู้ผลิตระบุการสลับด้วยการกดค้าง `LT+RT+A` (จอย Logitech) หรือ
`L2+R2+A` (รีโมตมีจอ) ไม่ใช้ SDK และรีโมตควบคุมการเดินพร้อมกัน
โค้ดไม่เดาหรือเรียกฟังก์ชันแย่งสิทธิ์ควบคุมที่ไม่มีใน Python API

**คำสั่งต่อไปนี้เปิดการเดินจริง และเริ่มเลือกคน/เดินตามอัตโนมัติทันทีเมื่อข้อมูลพร้อม:**

```bash
bash /home/firefly/d1-follow/run_follow.sh --enable-motion
```

เริ่มด้วยทางโล่ง ผู้ควบคุมถือรีโมตหยุด: ยังไม่มีระบบหลบโต๊ะ เก้าอี้ บันได หรือสิ่งกีดขวาง
คนที่เลือกสามารถเปลี่ยนได้ทุกเฟรมตามคนที่อยู่ใกล้กลางภาพที่สุด

## 4. Logic และหยุด

- คนใกล้กลางภาพที่สุดถูกเลือกอัตโนมัติ ไม่ต้อง Lock
- คนกลางภาพ: `move(0.15, 0, 0)` เมตร/วินาที
- คนเยื้องซ้าย/ขวาเกิน 12% ของความกว้างภาพ: เลี้ยวอยู่กับที่ `move(0, 0, ±0.2)` เรเดียน/วินาที
- กรอบคนสูง ≥ 65% ของภาพ: HOLD ส่ง `move(0, 0, 0)`; ไม่ใช่ระยะวัดจริง
- ไม่พบคน / ข้อมูลที่รับบน PC เก่าเกิน 1 วินาที: ส่งความเร็วศูนย์
- Network/API/SDK error: พยายามส่งศูนย์ 3 ครั้ง แล้วออก ต้องรัน bridge ใหม่
- Dashboard **หยุดเดิน / STOP**: ปิด permission; bridge ส่งศูนย์เมื่อรับผล poll ถัดไป
- Dashboard **เริ่มเดินตาม / Resume**: เปิด permission อีกครั้งเมื่อ bridge READY
- Ctrl+C ใน terminal 3: ส่งศูนย์ก่อนออก
- Bridge heartbeat ขาดเกิน 1 วินาที: dashboard แสดง OFFLINE และยกเลิก permission

ไม่มีการรับประกันการหยุดด้วยซอฟต์แวร์หาก process ถูก kill แบบทันที, native SDK ค้าง,
SDK ไม่รับคำสั่ง หรือช่องสื่อสารกับ motor controller ขาด ใช้ physical remote stop ในกรณีนั้น
ข้อมูลอายุภาพเริ่มนับเมื่อ OpenCV รับภาพ ไม่สามารถวัด buffering ภายในกล้อง RTSP ได้

## 5. ถ้าไม่เดิน

- OFFLINE: ยังไม่รัน bridge / ไม่มี reverse tunnel / bridge หยุดจาก error
- READY + FOLLOW DISABLED: กด Resume หรือดูว่ากด Stop ไว้หรือไม่
- TARGET: STOP: ไม่มีคน หรือ inference/ภาพช้าเกิน 1 วินาที
- HOLD: กรอบคนใหญ่เกินเกณฑ์ จึงตั้งใจหยุด
- SDK rejection หรือ mode ไม่ใช่ 1/3: ดู terminal 3 ตรวจ firmware, SDK config, ท่ายืน และสิทธิ์ควบคุม
- ACTIVE หมายถึง SDK ตอบรับคำสั่งเท่านั้น ถ้าตัวหุ่นไม่เดินให้ตรวจสิทธิ์/firmware ไม่เพิ่มความเร็วแก้ปัญหา

## อ้างอิงทางการ

- https://github.com/AgibotTech/agibot_D1_Edu-Ultra
- https://github.com/AgibotTech/agibot_D1_Edu-Ultra/blob/main/include/zsl-1/highlevel.h
- https://github.com/AgibotTech/agibot_D1_Edu-Ultra/blob/main/demo/zsl-1/python/examples/highlevel_demo_Interactive.py
- https://github.com/AgibotTech/agibot_D1_Edu-Ultra/blob/main/docs/source/5.7在机器人本体运行SDK.md
- https://github.com/AgibotTech/agibot_D1_Edu-Ultra/blob/main/docs/source/5.4控制权切换功能.md
