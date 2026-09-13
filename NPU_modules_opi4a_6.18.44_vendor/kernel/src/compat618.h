/* SPDX-License-Identifier: GPL-2.0 */
/* Force-included (ccflags -include) compat shims for building the vendor
 * 5.15/6.6-era vipcore against Linux 6.18. */
#ifndef _VIPCORE_COMPAT618_H
#define _VIPCORE_COMPAT618_H

#include <linux/version.h>
#include <linux/mm.h>

/* nth_page() was removed in 6.18: pages within an allocation are
 * contiguous in the memmap, plain pointer arithmetic is the replacement. */
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 18, 0) && !defined(nth_page)
#define nth_page(page, n) ((page) + (n))
#endif

#endif
