/* SPDX-License-Identifier: GPL-2.0 */
/* Stub for the vendor <sunxi-sid.h> — not present in mainline/edge trees.
 * VF-binning SID reads fail gracefully; driver falls back to default
 * frequency/voltage tables. */
#ifndef _STUB_SUNXI_SID_H
#define _STUB_SUNXI_SID_H

#include <linux/errno.h>
#include <linux/types.h>

static inline int sunxi_sid_sram_read32(const char *name, u32 *val)
{
	return -ENOSYS;
}


static inline int sunxi_get_module_param_from_sid(u32 *val, int offset, int len)
{
    if (val) *val = 0;
    return -ENOSYS;
}

static inline int sunxi_get_soc_ver(void)
{
	return 0;
}

#endif
