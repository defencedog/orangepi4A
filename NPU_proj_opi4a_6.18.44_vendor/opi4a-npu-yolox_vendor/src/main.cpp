/*
 * Company:    AW
 * Author:     zhuzhiyongs
 * Date:    2025/11/14
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>

#include "npulib.h"

/*-------------------------------------------
        Macros and Variables
-------------------------------------------*/

extern int yolox_preprocess(const char* imagepath, void* buff_ptr, unsigned int buff_size);
extern int yolox_postprocess(const char *imagepath, float **output);

const char *usage =
    "yolox_demo -nb modle_path -i input_path -l loop_run_count -m malloc_mbyte \n"
    "-nb modle_path:    the NBG file path.\n"
    "-i input_path:     the input file path.\n"
    "-l loop_run_count: the number of loop run network.\n"
    "-m malloc_mbyte:   npu_unit init memory Mbytes.\n"
    "-h : help\n"
    "example: yolox_demo -nb model.nb -i input.jpg -l 10 -m 20 \n";

enum time_idx_e {
    NPU_INIT = 0,
    NETWORK_CREATE,
    NETWORK_PREPARE,
    NETWORK_PREPROCESS,
    NETWORK_RUN,
    NETWORK_LOOP,
    TIME_IDX_MAX = 9
};

#if defined(__linux__)
#define TIME_SLOTS   10
static uint64_t time_begin[TIME_SLOTS];
static uint64_t time_end[TIME_SLOTS];
static uint64_t GetTime(void)
{
    struct timeval time;
    gettimeofday(&time, NULL);
    return (uint64_t)(time.tv_usec + time.tv_sec * 1000000);
}

static void TimeBegin(int id)
{
    time_begin[id] = GetTime();
}

static void TimeEnd(int id)
{
    time_end[id] = GetTime();
}

static uint64_t TimeGet(int id)
{
    return time_end[id] - time_begin[id];
}
#endif

int main(int argc, char** argv)
{
    int status = 0;
    int i = 0;
    unsigned int count = 0;
    long long total_infer_time = 0;

    char *model_file = NULL;
    char *input_file = NULL;
    unsigned int loop_count = 1;
    unsigned int malloc_mbyte = 10;

    if (argc < 2) {
        printf("%s\n", usage);
        return -1;
    }

    for (i = 0; i< argc; i++) {
        if (!strcmp(argv[i], "-nb")) {
            model_file = argv[++i];
        }
        else if (!strcmp(argv[i], "-i")) {
            input_file = argv[++i];
        }
        else if (!strcmp(argv[i], "-l")) {
            loop_count = atoi(argv[++i]);
        }
        else if (!strcmp(argv[i], "-m")) {
            malloc_mbyte = atoi(argv[++i]);
        }
        else if (!strcmp(argv[i], "-h")) {
            printf("%s\n", usage);
            return 0;
        }
    }
    printf("model_file=%s, input=%s, loop_count=%d, malloc_mbyte=%d \n", model_file, input_file, loop_count, malloc_mbyte);

    if (model_file == nullptr)
        return -1;

    /* NPU init*/
    NpuUint npu_uint;

//    int ret = npu_uint.npu_init(malloc_mbyte*1024*1024);    // 85x
    int ret = npu_uint.npu_init();
    if (ret != 0) {
        return -1;
    }

    NetworkItem yolox_net;
    unsigned int network_id = 0;
    status = yolox_net.network_create(model_file, network_id);
    if (status != 0) {
        printf("network %d create failed.\n", network_id);
        return -1;
    }

    status = yolox_net.network_prepare();
    if (status != 0) {
        printf("network prepare fail, status=%d\n", status);
        return -1;
    }

    TimeBegin(NETWORK_PREPROCESS);
    // input jpg file, no copy way
    void *input_buffer_ptr = nullptr;
    unsigned int input_buffer_size = 0;
    yolox_net.get_network_input_buff_info(0, &input_buffer_ptr, &input_buffer_size);

    printf("buffer ptr: %p, buffer size: %d \n", input_buffer_ptr, input_buffer_size);

    yolox_preprocess(input_file, input_buffer_ptr, input_buffer_size);

    TimeEnd(NETWORK_PREPROCESS);
    printf("feed input cost: %lu us.\n", (unsigned long)TimeGet(NETWORK_PREPROCESS));

    // create yolox output buffer
    int output_cnt = yolox_net.get_output_cnt();     // network output count

    float **output_data = new float*[output_cnt]();

    for (int i = 0; i < output_cnt; i++)
        output_data[i] = new float[yolox_net.m_output_data_len[i]];

    i = network_id;
    /* run network */
    TimeBegin(NETWORK_LOOP);
    while (count < loop_count) {
        count++;

        printf("network: %d, loop count: %d\n", i, count);
        status = yolox_net.network_input_output_set();
        if (status != 0) {
            printf("set network input/output %d failed.\n", i);
            return -1;
        }

        #if defined (__linux__)
        TimeBegin(NETWORK_RUN);
        #endif

        status = yolox_net.network_run();
        if (status != 0) {
            printf("fail to run network, status=%d, batchCount=%d\n", status, i);
            return -2;
        }

        #if defined (__linux__)
        TimeEnd(NETWORK_RUN);
        printf("run time for this network %d: %lu us.\n", i, (unsigned long)TimeGet(NETWORK_RUN));
        #endif

        total_infer_time += (unsigned long)TimeGet(NETWORK_RUN);

        yolox_net.get_output(output_data);
        yolox_postprocess(input_file, output_data);
    }
    TimeEnd(NETWORK_LOOP);

    if (loop_count > 1) {
        printf("network: %d, this network run avg inference time=%d us,  total avg cost: %d us\n", i,
                (uint32_t)(total_infer_time / loop_count), (unsigned int)(TimeGet(NETWORK_LOOP) / loop_count));
    }

    // free output buffer
    for (int i = 0; i < output_cnt; i++) {
        delete[] output_data[i];
        output_data[i] = nullptr;
    }

    if (output_data != nullptr)
        delete[] output_data;

    return ret;
}