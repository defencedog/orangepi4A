# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
# Adapted for Allwinner T527 (VIPCore NPU / MNN CPU) on Orange Pi 4A.
import os
import sys
import cv2
import numpy as np
from vipcore_model import UnifiedModelContainer
from utils.db_postprocess import DBPostProcess, DetPostProcess

POSTPROCESS_CONFIG = {
    'thresh': 0.3,
    'box_thresh': 0.5,
    'max_candidates': 1000,
    'unclip_ratio': 1.6,
    'use_dilation': False,
    'score_mode': 'fast',
}

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape((1, 1, 3))
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape((1, 1, 3))


class TextDetector:
    def __init__(self, det_model_path, backend='auto', num_threads=6):
        self.model = UnifiedModelContainer(det_model_path, backend=backend, num_threads=num_threads, precision='normal')
        
        cfg = dict(POSTPROCESS_CONFIG)
        self.db_postprocess = DBPostProcess(**cfg)
        self.det_postprocess = DetPostProcess()

        # Dynamic shape auto-detection
        if hasattr(self.model, 'input_shape'):
            self.input_shape = self.model.input_shape
        elif hasattr(self.model, 'input_tensor') and self.model.input_tensor:
            shape = self.model.input_tensor.getShape()
            self.input_shape = [shape[2], shape[3]] if len(shape) == 4 else [1024, 1024]
        else:
            self.input_shape = [1024, 1024]

    def preprocess(self, img):
        src_h, src_w = img.shape[:2]
        target_h, target_w = self.input_shape
        ratio_h = float(target_h) / src_h
        ratio_w = float(target_w) / src_w

        img_resized = cv2.resize(img, (target_w, target_h))
        # Convert BGR to RGB
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        img_norm = (img_rgb.astype(np.float32) / 255.0 - MEAN) / STD
        
        # Prepare shape info for DBPostProcess
        shape_info = np.array([[src_h, src_w, ratio_h, ratio_w]])
        return img_norm, shape_info

    def run(self, img):
        img_norm, shape_info = self.preprocess(img)
        output = self.model.run(img_norm)
        pred_map = output[0]

        # Ensure pred_map is (1, 1, H, W) for DBPostProcess
        if pred_map.ndim == 4:
            if pred_map.shape[-1] == 1 and pred_map.shape[1] != 1:
                # NHWC -> NCHW
                pred_map = np.transpose(pred_map, (0, 3, 1, 2))
        elif pred_map.ndim == 3:
            pred_map = np.expand_dims(pred_map, axis=0)

        preds = {'maps': pred_map.astype(np.float32)}
        result = self.db_postprocess(preds, shape_info)
        output = self.det_postprocess.filter_tag_det_res(result[0]['points'], img.shape)
        return output

    def release(self):
        self.model.release()
