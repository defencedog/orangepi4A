#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <sys/ioctl.h>
#include <linux/types.h>
#include <stdbool.h>
#include <stdint.h>
#include <bsp/linux/sunxi-g2d.h>
#include <linux/dma-heap.h>
#include <sys/mman.h>
#include <errno.h>
#include <time.h>

#define DMA_HEAP_NAME "/dev/dma_heap/system"

#define get_time_ms() ({ \
    struct timespec ts; \
    clock_gettime(CLOCK_MONOTONIC, &ts); \
    ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6; \
})

#define IMAGE_WIDTH  1920
#define IMAGE_HEIGHT 1080
#define IMAGE_SIZE   (IMAGE_WIDTH * IMAGE_HEIGHT * 4)

#define RED     0xffff0000
#define GREEN   0xff00ff00
#define BLUE    0xff0000ff
#define YELLOW  0xffffff00
#define WHITE   0xffffffff
#define BLACK   0xff000000

static int alloc_dmabuf(int *fd, void **vaddr, size_t size)
{
    struct dma_heap_allocation_data alloc_data = {
        .len = size,
        .fd_flags = O_RDWR | O_CLOEXEC,
        .heap_flags = 0,
    };

    int heap_fd = open(DMA_HEAP_NAME, O_RDONLY);
    if (heap_fd < 0) {
        perror("open DMA heap");
        return -1;
    }

    if (ioctl(heap_fd, DMA_HEAP_IOCTL_ALLOC, &alloc_data) < 0) {
        perror("DMA_HEAP_IOCTL_ALLOC");
        close(heap_fd);
        return -1;
    }
    close(heap_fd);

    *fd = alloc_data.fd;
    *vaddr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, *fd, 0);
    if (*vaddr == MAP_FAILED) {
        perror("mmap");
        close(*fd);
        return -1;
    }
    return 0;
}

static void fill_solid(void *buf, uint32_t argb, int w, int h)
{
    uint32_t *p = buf;
    for (int i = 0; i < w * h; i++)
        p[i] = argb;
}

int main(void)
{
    int g2d_fd, dst_fd;
    void *dst_v;
    g2d_blt_h blit;
    double t0, t1;

    t0 = get_time_ms();

    if (alloc_dmabuf(&dst_fd, &dst_v, IMAGE_SIZE) < 0)
        return 1;

    /* Init to white background */
    fill_solid(dst_v, WHITE, IMAGE_WIDTH, IMAGE_HEIGHT);

    g2d_fd = open("/dev/g2d", O_RDWR);
    if (g2d_fd < 0) {
        perror("open /dev/g2d");
        goto cleanup;
    }

    memset(&blit, 0, sizeof(blit));
    blit.flag_h = G2D_BLT_NONE_H;

    /* Source is a solid color (no src buffer needed) */
    blit.src_image_h.use_phy_addr = 0;
    blit.src_image_h.bbuff = 0;
    blit.src_image_h.color = RED;
    blit.src_image_h.mode = G2D_PIXEL_ALPHA;
    blit.src_image_h.alpha = 0xff;
    blit.src_image_h.format = G2D_FORMAT_ARGB8888;
    blit.src_image_h.width = IMAGE_WIDTH;
    blit.src_image_h.height = IMAGE_HEIGHT;
    blit.src_image_h.clip_rect.x = 0;
    blit.src_image_h.clip_rect.y = 0;
    blit.src_image_h.clip_rect.w = IMAGE_WIDTH;
    blit.src_image_h.clip_rect.h = IMAGE_HEIGHT;

    blit.dst_image_h.use_phy_addr = 0;
    blit.dst_image_h.fd = dst_fd;
    blit.dst_image_h.bbuff = 1;
    blit.dst_image_h.mode = G2D_PIXEL_ALPHA;
    blit.dst_image_h.alpha = 0xff;
    blit.dst_image_h.format = G2D_FORMAT_ARGB8888;
    blit.dst_image_h.width = IMAGE_WIDTH;
    blit.dst_image_h.height = IMAGE_HEIGHT;
    blit.dst_image_h.clip_rect.x = 0;
    blit.dst_image_h.clip_rect.y = 0;
    blit.dst_image_h.clip_rect.w = IMAGE_WIDTH;
    blit.dst_image_h.clip_rect.h = IMAGE_HEIGHT;

    double t_g2d_start = get_time_ms();
    int ret = ioctl(g2d_fd, G2D_CMD_BITBLT_H, (unsigned long)(&blit));
    double t_g2d_end = get_time_ms();

    if (ret < 0) {
        fprintf(stderr, "G2D_CMD_BITBLT_H failed: %s\n", strerror(errno));
        goto cleanup;
    }

    printf("G2D color fill (RED): %.2f ms\n", t_g2d_end - t_g2d_start);
    printf("throughput: %.1f MP/sec\n",
           (IMAGE_WIDTH * IMAGE_HEIGHT) / 1e6 / ((t_g2d_end - t_g2d_start) / 1000.0));

cleanup:
    close(g2d_fd);
    munmap(dst_v, IMAGE_SIZE);
    close(dst_fd);

    t1 = get_time_ms();
    printf("total: %.2f ms\n", t1 - t0);
    return 0;
}
