/*
 * Company:    AW
 * Author:     zhuzhiyongs
 * Date:    2025/12/04
 */

#include <opencv2/core/core.hpp>
#include <opencv2/highgui/highgui.hpp>
#include <opencv2/imgproc/imgproc.hpp>
#include <iostream>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <chrono>

#include "model_config.h"

/* model_inputmeta.yml file param modify, eg:

    preproc_node_params:
      add_preproc_node: True
      preproc_type: IMAGE_BGR


demo model: model_rgb_xxx.nb.
*/

void get_input_data(const char* image_file, unsigned char* input_data, int letterbox_rows, int letterbox_cols)
{
    cv::Mat img = cv::imread(image_file, 1);
    if (img.empty()) {
        fprintf(stderr, "cv::imread %s failed\n", image_file);
        return;
    }

    fprintf(stderr, "Original image size: %dx%d\n", img.cols, img.rows);

    /* letterbox process to support different letterbox size */
    float scale_letterbox = 1.f;
    if ((letterbox_rows * 1.0 / img.rows) < (letterbox_cols * 1.0 / img.cols))
    {
        scale_letterbox = letterbox_rows * 1.0 / img.rows;
    }
    else
    {
        scale_letterbox = letterbox_cols * 1.0 / img.cols;
    }
    int resize_cols = int(round(scale_letterbox * img.cols));
    int resize_rows = int(round(scale_letterbox * img.rows));

    float dh = (float)(letterbox_rows - resize_rows);
    float dw = (float)(letterbox_cols - resize_cols);

    dh /= 2.0f;
    dw /= 2.0f;

    cv::resize(img, img, cv::Size(resize_cols, resize_rows));

    // create a mat with input_data ptr
    cv::Mat img_new(letterbox_rows, letterbox_cols, CV_8UC3, input_data);
    int top   = (int)(round(dh - 0.1));
    int bot   = (int)(round(dh + 0.1));
    int left  = (int)(round(dw - 0.1));
    int right = (int)(round(dw + 0.1));

    // Letterbox filling
    cv::copyMakeBorder(img, img_new, top, bot, left, right, cv::BORDER_CONSTANT, cv::Scalar(114, 114, 114));
}

int yolox_preprocess(const char* imagepath, void* buff_ptr, unsigned int buff_size)
{
    int img_c = 3;

    // set default letterbox size
    int letterbox_rows = LETTERBOX_ROWS;
    int letterbox_cols = LETTERBOX_COLS;
    int img_size = letterbox_rows * letterbox_cols * img_c;

    unsigned int data_size = img_size * sizeof(uint8_t);  // YOLOX_nb uses uint8_t input

    if (data_size > buff_size) {
        printf("data size > buff size, please check code. data_size=%u, buff_size=%u\n", data_size, buff_size);
        return -1;
    }

    get_input_data(imagepath, (unsigned char*)buff_ptr, letterbox_rows, letterbox_cols);

    printf("YOLOX preprocess completed: %s -> %dx%d, buffer size: %u\n",
           imagepath, letterbox_cols, letterbox_rows, data_size);
    return 0;
}