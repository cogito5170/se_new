#!/usr/bin/env bash
# SAR 데모 자산 내려받기. 제3자 이미지·모델이라 저장소에 커밋하지 않는다(라이선스는 원 저장소 참조).
#   - 이미지: ultralytics/yolov5 데모 이미지(사람이 있는 실사진; 수색구역 스탠드인)
#   - 모델:   opencv_zoo YuNet 얼굴탐지 ONNX(git-LFS -> media 엔드포인트로 받는다)
set -e
d="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$d/assets" "$d/models"
curl -sSL -o "$d/assets/zidane.jpg" https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/zidane.jpg
curl -sSL -o "$d/assets/bus.jpg"    https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/bus.jpg
curl -sSL -o "$d/models/yunet.onnx" https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
echo "assets:   $(wc -c < "$d/assets/zidane.jpg")B zidane.jpg, $(wc -c < "$d/assets/bus.jpg")B bus.jpg"
echo "model:    $(wc -c < "$d/models/yunet.onnx")B yunet.onnx"
echo "ready. deps: pip install opencv-python-headless numpy matplotlib ; then: make demo"
