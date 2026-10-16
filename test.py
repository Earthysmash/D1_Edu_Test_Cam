from ultralytics import YOLO

# โหลดโมเดลสำเร็จรูป ครั้งแรกต้องใช้อินเทอร์เน็ตดาวน์โหลด
model = YOLO("yolo26n.pt")

# เลือกเฉพาะหมวดที่ต้องการ
wanted = {"person", "chair", "dining table"}
class_ids = [
    class_id
    for class_id, name in model.names.items()
    if name in wanted
]

# source=0 คือกล้องเว็บแคมของคอม
for result in model.predict(
    source=0,
    classes=class_ids,
    conf=0.5,
    show=True,
    stream=True,
):
    for box in result.boxes:
        name = result.names[int(box.cls.item())]
        confidence = box.conf.item()
        print(f"{name}: {confidence:.0%}")