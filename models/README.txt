Place trained ONNX models here:

  gtav_yolov8n.onnx   — trained on GTA V gameplay frames
  mgs5_yolov8n.onnx   — trained on MGS5 gameplay frames

See training/colab_train.md for the full training pipeline.

The bot runs without these files (VisionEngine returns empty detections),
so you can verify the brain/planner loop with --dry-run before training.
