/****************************************************************************
*  npulib header file
****************************************************************************/
#ifndef _NPULIB_H_
#define _NPULIB_H_

#include <stdint.h>
#include <cstddef>

#ifdef __cplusplus
extern "C"{
#endif

#define MAX_NETWORK_OUTPUT  32


typedef struct _npu_network  *npu_network;
typedef struct _npu_buffer   *npu_buffer;

typedef enum _save_file_type_e
{
    SAVE_NONE,
    SAVE_BINARY,
    SAVE_TEXT
} save_file_type_e;

typedef struct _output_info_s
{
    float   *ptr;
    int      length;
} output_info_s;

#define _CHECK_STATUS( stat )  do {\
    if( 0 != stat ) {\
        printf("Error: %s: %s at %d\n", __FILE__, __FUNCTION__, __LINE__);\
    }\
} while(0)


class NpuUint
{
public:
    NpuUint(void);
    ~NpuUint(void);

    unsigned int get_driver_version(void);
    int npu_init(unsigned int mem_size=0);
    int query_hardware_info(void);
    int npu_destroy(void);
};


class NpuBuffer
{
public:
    NpuBuffer(void);
    ~NpuBuffer(void);

    // create a buffer
    void *create_buffer(unsigned int buffer_size);

private:
    npu_buffer m_buffer_obj;
};


class NetworkItem
{
public:
    NetworkItem(void);
    ~NetworkItem(void);

    int network_create(char *model_file, unsigned int network_id);

    // specify the memory pool buffer, should be called before prepare network
    unsigned int get_memory_pool_size(void);
    int set_memory_pool_buffer(void *memory_pool_buffer_obj);

    // only use in multi_thread demo, should be called before prepare network
    // set priority of network. 0 ~ 255, 0 indicates the lowest priority
    int set_priority(unsigned char priority);

    int network_prepare(void);
    int network_input_output_set(void);

    // get  input buffer info
    int get_network_input_buff_info(int buff_idx, void **input_buff_ptr, unsigned int *buff_size);
    // get output buffer info
    int get_network_output_buff_info(int buff_idx, void **output_buff_ptr, unsigned int *buff_size);


    // input file such as: xxx.tensor, xxx.dat, xxx.bin, xxx.txt
    int network_load_input_file(char **input_path);
    int network_load_input_file_idx(char *input_path, int input_idx);

    // one input, eg: BGR, RGB
    int network_load_input_buffer(void *input_data, unsigned int input_size);
    int network_load_input_buffer_idx(void *input_data, unsigned int input_size, int input_idx);

    // input yuv buffer
    int network_load_input_yuv_buffer(void *yuv_data, int w, int h);
    // input yuv file
    int network_load_input_yuv_file(char **input_path, int w, int h);


    int network_run(void);

    float **get_output(float **output_float=NULL, save_file_type_e save_type=SAVE_NONE);    //default: SAVE_NONE
    void get_output_fp_nocopy(output_info_s *outputs_info, save_file_type_e save_type=SAVE_NONE);

    char *get_ngb_name(void);

    int get_output_cnt(void);


    void network_finish(void);

    void network_destroy(void);

    npu_network     m_network;


    // output_data length
    unsigned int    m_output_data_len[MAX_NETWORK_OUTPUT] = {0}; // 32 may change

private:
    // create input/output buffer
    int network_create_io_buffer(void);

    /* network information. */
    int             m_nbg_name;
    int             m_input_count;
    int             m_output_count;

    /* NPU buffer objects. */
    npu_buffer     *m_input_buffers;
    npu_buffer     *m_output_buffers;

    void          **m_input_buffers_handle;
    void          **m_output_buffers_handle;

};



#ifdef __cplusplus
}
#endif

#endif
