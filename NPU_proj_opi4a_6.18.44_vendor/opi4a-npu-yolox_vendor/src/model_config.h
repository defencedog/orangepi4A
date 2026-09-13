#ifndef _MODEL_CONFIG_H_
#define _MODEL_CONFIG_H_

#include <iostream>
#include <vector>

#define COCO    1
//#define COCO    0

#if COCO
// coco, 80 class
#define CLASS_NUM           80

/* 640 * 640 */
#define LETTERBOX_ROWS      640
#define LETTERBOX_COLS      640

#define SCORE_THRESHOLD     0.45f
#define NMS_THRESHOLD       0.45f

const std::vector<std::string> g_classes_name{
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic_light",
    "fire_hydrant", "stop_sign", "parking_meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports_ball", "kite", "baseball_bat", "baseball_glove", "skateboard", "surfboard",
    "tennis_racket", "bottle", "wine_glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot_dog", "pizza", "donut", "cake", "chair", "couch",
    "potted_plant", "bed", "dining_table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell_phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy_bear",
    "hair_drier", "toothbrush"
};

#else
// eg: plant, 1 class
#define CLASS_NUM           1

#define LETTERBOX_ROWS      640
#define LETTERBOX_COLS      640

#define SCORE_THRESHOLD     0.4f
#define NMS_THRESHOLD       0.45f

const std::vector<std::string> g_classes_name{
    "plant"
};

#endif

#endif
