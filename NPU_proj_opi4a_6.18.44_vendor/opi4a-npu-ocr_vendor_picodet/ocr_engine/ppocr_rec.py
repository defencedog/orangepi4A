# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
# Adapted for Allwinner T527 (MNN FP16 CPU) on Orange Pi 4A with Dynamic Aspect Ratio.
import math
import os
import cv2
import numpy as np
from vipcore_model import UnifiedModelContainer
from utils.rec_postprocess import CTCLabelDecode


class TextRecognizer:
    def __init__(self, rec_model_path, dict_path=None, backend='auto', num_threads=4):
        # Auto-detect dynamic model if specified static model is missing or dynamic is available
        if not os.path.exists(rec_model_path):
            base_dir = os.path.dirname(rec_model_path)
            dyn_cand = os.path.join(base_dir, 'en_pp_ocrv4_rec_dynamic.mnn')
            if os.path.exists(dyn_cand):
                rec_model_path = dyn_cand

        self.model = UnifiedModelContainer(rec_model_path, backend=backend, num_threads=num_threads, precision='low')
        
        if dict_path is None:
            dict_path = os.environ.get('NPU_OCR_REC_DICT', 
                                       os.path.join(os.path.dirname(rec_model_path), 'en_dict.txt'))
        self.dict_path = dict_path
        self.ctc_postprocess = CTCLabelDecode(character_dict_path=self.dict_path, use_space_char=True)

    def preprocess(self, img):
        h, w = img.shape[:2]
        ratio = w / float(h)
        # Calculate width preserving aspect ratio (quantized to multiple of 32 for CNN alignment)
        target_w = max(320, min(1536, int(math.ceil(48.0 * ratio / 32.0) * 32)))
        res_w = min(int(round(48.0 * ratio)), target_w)
        resized = cv2.resize(img, (res_w, 48))

        # Pad with zero to target_w
        padded = np.zeros((48, target_w, 3), dtype=np.uint8)
        padded[:, :res_w] = resized

        # Convert BGR to RGB
        img_rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        # Normalize: (img / 255 - 0.5) / 0.5
        img_norm = (img_rgb.astype(np.float32) / 255.0 - 0.5) / 0.5
        return img_norm

    def run(self, imgs):
        outputs = []
        for img in imgs:
            if img is None or img.size == 0 or img.shape[0] < 4 or img.shape[1] < 4:
                continue
            norm_img = self.preprocess(img)
            output = self.model.run(norm_img)
            preds = output[0].astype(np.float32)
            decoded = self.ctc_postprocess(preds)
            outputs.append(decoded)
        return outputs

    def release(self):
        self.model.release()
