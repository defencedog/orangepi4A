/*
 * Company:    AW
 * Author:     zhuzhiyongs
 * Date:       2025/12/04
 */

#include <opencv2/core/core.hpp>
#include <opencv2/highgui/highgui.hpp>
#include <opencv2/imgproc/imgproc.hpp>
#include <opencv2/dnn.hpp>
#include <iostream>
#include <stdio.h>
#include <vector>
#include <cmath>

#include "model_config.h"

using namespace std;

struct Object
{
    cv::Rect_<float> rect;
    int label;
    float prob;
};

static inline float intersection_area(const Object& a, const Object& b)
{
    cv::Rect_<float> inter = a.rect & b.rect;
    return inter.area();
}

static void qsort_descent_inplace(std::vector<Object>& objects, int left, int right)
{
    int i = left;
    int j = right;
    float p = objects[(left + right) / 2].prob;

    while (i <= j)
    {
        while (objects[i].prob > p)
            i++;

        while (objects[j].prob < p)
            j--;

        if (i <= j)
        {
            std::swap(objects[i], objects[j]);
            i++;
            j--;
        }
    }

#pragma omp parallel sections
    {
#pragma omp section
        {
            if (left < j) qsort_descent_inplace(objects, left, j);
        }
#pragma omp section
        {
            if (i < right) qsort_descent_inplace(objects, i, right);
        }
    }
}

static void qsort_descent_inplace(std::vector<Object>& objects)
{
    if (objects.empty())
        return;

    qsort_descent_inplace(objects, 0, objects.size() - 1);
}

static void nms_sorted_bboxes(const std::vector<Object>& objects, std::vector<int>& picked, float nms_threshold, bool agnostic = true)
{
    picked.clear();

    const int n = objects.size();

    std::vector<float> areas(n);
    for (int i = 0; i < n; i++)
    {
        areas[i] = objects[i].rect.area();
    }

    for (int i = 0; i < n; i++)
    {
        const Object& a = objects[i];

        int keep = 1;
        for (int j = 0; j < (int)picked.size(); j++)
        {
            const Object& b = objects[picked[j]];

            // Different categories do not undergo NMS
            if (!agnostic && a.label != b.label)
                continue;

            float inter_area = intersection_area(a, b);
            float union_area = areas[i] + areas[picked[j]] - inter_area;
            if (inter_area / union_area > nms_threshold)
                keep = 0;
        }

        if (keep)
            picked.push_back(i);
    }
}

static inline float sigmoid(float x)
{
    return 1.0f / (1.0f + expf(-x));
}

static void generate_proposals_yolox(int stride, const float* feat, float prob_threshold, std::vector<Object>& objects,
                                    int letterbox_cols, int letterbox_rows)
{
    const int num_grid_w = letterbox_cols / stride;
    const int num_grid_h = letterbox_rows / stride;
    const int num_grid = num_grid_w * num_grid_h;

    const int num_class = CLASS_NUM;
    const int num_channel = CLASS_NUM + 5;

    int obj_count = 0;
    for (int i = 0; i < num_grid_h; i++)
    {
        for (int j = 0; j < num_grid_w; j++)
        {
            int grid_index = i * num_grid_w + j;

            // Channel-priority data access - retrieve the value at the corresponding position from each channel separately.
            float x_center = (feat[0 * num_grid_h * num_grid_w + grid_index] + j) * stride;
            float y_center = (feat[1 * num_grid_h * num_grid_w + grid_index] + i) * stride;
            float width = expf(feat[2 * num_grid_h * num_grid_w + grid_index]) * stride;
            float height = expf(feat[3 * num_grid_h * num_grid_w + grid_index]) * stride;

            // Object confidence
            float obj_conf = feat[4 * num_grid_h * num_grid_w + grid_index];

            if (obj_conf < prob_threshold) {
                continue;
            }

            // Find the highest category score
            int class_id = -1;
            float class_conf = -FLT_MAX;
            for (int c = 0; c < num_class; c++)
            {
                float conf = feat[(5 + c) * num_grid_h * num_grid_w + grid_index];
                if (conf > class_conf)
                {
                    class_id = c;
                    class_conf = conf;
                }
            }

            // Calculate final score
            float final_score = obj_conf * class_conf;
            if (final_score >= prob_threshold)
            {
                Object obj;
                obj.rect.x = x_center - width / 2.0f;
                obj.rect.y = y_center - height / 2.0f;
                obj.rect.width = width;
                obj.rect.height = height;
                obj.label = class_id;
                obj.prob = final_score;

                objects.push_back(obj);
            }
        }
    }
}

int detect_yolox_post(const cv::Mat& bgr, std::vector<Object>& objects, float **output)
{
    std::chrono::steady_clock::time_point Tbegin, Tend;
    Tbegin = std::chrono::steady_clock::now();
    // YOLOX has 3 outputs
    const float *output0_ptr = output[0]; // 85x80x80
    const float *output1_ptr = output[1]; // 85x40x40
    const float *output2_ptr = output[2]; // 85x20x20

    // Set letterbox size
    int letterbox_rows = LETTERBOX_ROWS;
    int letterbox_cols = LETTERBOX_COLS;

    // Post-processing parameters
    const float prob_threshold = SCORE_THRESHOLD;
    const float nms_threshold = NMS_THRESHOLD;

    std::vector<Object> proposals;
    std::vector<Object> objects80;
    std::vector<Object> objects40;
    std::vector<Object> objects20;

    // Process 3 outputs
    {
        generate_proposals_yolox(8, output0_ptr, prob_threshold, objects80, letterbox_cols, letterbox_rows);
        proposals.insert(proposals.end(), objects80.begin(), objects80.end());
    }
    {
        generate_proposals_yolox(16, output1_ptr, prob_threshold, objects40, letterbox_cols, letterbox_rows);
        proposals.insert(proposals.end(), objects40.begin(), objects40.end());
    }

    {
        generate_proposals_yolox(32, output2_ptr, prob_threshold, objects20, letterbox_cols, letterbox_rows);
        proposals.insert(proposals.end(), objects20.begin(), objects20.end());
    }

    // Sort all proposals by score from highest to lowest.
    qsort_descent_inplace(proposals);

    // appply NMS
    std::vector<int> picked;
    nms_sorted_bboxes(proposals, picked, nms_threshold);

    // Inverse coordinate transformation
    float scale_letterbox = 1.0f;
    if ((letterbox_rows * 1.0 / bgr.rows) < (letterbox_cols * 1.0 / bgr.cols))
    {
        scale_letterbox = letterbox_rows * 1.0 / bgr.rows;
    }
    else
    {
        scale_letterbox = letterbox_cols * 1.0 / bgr.cols;
    }
    float ratio = 1.0f / scale_letterbox;

    int resize_cols = int(round(scale_letterbox * bgr.cols));
    int resize_rows = int(round(scale_letterbox * bgr.rows));

    int hpad = (letterbox_rows - resize_rows)/ 2;
    int wpad = (letterbox_cols - resize_cols)/ 2;


    int count = picked.size();
    objects.resize(count);
    for (int i = 0; i < count; i++)
    {
        objects[i] = proposals[picked[i]];

        float x0 = (objects[i].rect.x - wpad) * ratio;
        float y0 = (objects[i].rect.y - hpad) * ratio;
        float x1 = (objects[i].rect.x + objects[i].rect.width - wpad) * ratio;
        float y1 = (objects[i].rect.y + objects[i].rect.height - hpad) * ratio;

        x0 = std::max(std::min(x0, (float)(bgr.cols - 1)), 0.f);
        y0 = std::max(std::min(y0, (float)(bgr.rows - 1)), 0.f);
        x1 = std::max(std::min(x1, (float)(bgr.cols - 1)), 0.f);
        y1 = std::max(std::min(y1, (float)(bgr.rows - 1)), 0.f);

        objects[i].rect.x = x0;
        objects[i].rect.y = y0;
        objects[i].rect.width = x1 - x0;
        objects[i].rect.height = y1 - y0;
    }

    // Sort objects by area
    struct
    {
        bool operator()(const Object& a, const Object& b) const
        {
            return a.rect.area() > b.rect.area();
        }
    } objects_area_greater;
    std::sort(objects.begin(), objects.end(), objects_area_greater);

    Tend = std::chrono::steady_clock::now();
    float f = std::chrono::duration_cast<std::chrono::milliseconds>(Tend - Tbegin).count();

    fprintf(stderr, "detection num: %d\n", count);

    return 0;
}

static void draw_objects(const cv::Mat& bgr, const std::vector<Object>& objects, const char *imagepath)
{
    cv::Mat image = bgr.clone();

    for (size_t i = 0; i < objects.size(); i++)
    {
        const Object& obj = objects[i];

        if (obj.prob > 1.0) {
            fprintf(stderr, "%2d: %3.0f%%, [%4.0f, %4.0f, %4.0f, %4.0f], score is illegal ........ \n", obj.label, obj.prob * 100, obj.rect.x,
                    obj.rect.y, obj.rect.x + obj.rect.width, obj.rect.y + obj.rect.height);
            continue;
        }

        fprintf(stderr, "%2d: %3.0f%%, [%4.0f, %4.0f, %4.0f, %4.0f], %s\n", obj.label, obj.prob * 100, obj.rect.x,
                obj.rect.y, obj.rect.x + obj.rect.width, obj.rect.y + obj.rect.height, g_classes_name[obj.label].c_str());

        cv::rectangle(image, obj.rect, cv::Scalar(255, 0, 0));

        char text[256];
        sprintf(text, "%s %.1f%%", g_classes_name[obj.label].c_str(), obj.prob * 100);

        int baseLine = 0;
        cv::Size label_size = cv::getTextSize(text, cv::FONT_HERSHEY_SIMPLEX, 0.5, 1, &baseLine);

        int x = obj.rect.x;
        int y = obj.rect.y - label_size.height - baseLine;
        if (y < 0)
            y = 0;
        if (x + label_size.width > image.cols)
            x = image.cols - label_size.width;

        cv::rectangle(image, cv::Rect(cv::Point(x, y), cv::Size(label_size.width, label_size.height + baseLine)),
            cv::Scalar(255, 255, 255), -1);

        cv::putText(image, text, cv::Point(x, y + label_size.height),
            cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 0, 0));
    }

    cv::imwrite("output_yolox.png", image);
}

int yolox_postprocess(const char *imagepath, float **output)
{
    cv::Mat m = cv::imread(imagepath, 1);
    if (m.empty()) {
        fprintf(stderr, "cv::imread %s failed\n", imagepath);
        return -1;
    }

    std::vector<Object> objects;
    detect_yolox_post(m, objects, output);

    draw_objects(m, objects, imagepath);

    return 0;
}