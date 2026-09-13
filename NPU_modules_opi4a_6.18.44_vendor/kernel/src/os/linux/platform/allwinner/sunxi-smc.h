/* SPDX-License-Identifier: GPL-2.0 */
/* Stub for the vendor <sunxi-smc.h> — not present in mainline/edge trees.
 * Only the SUN55IW6 branch of check_smc_set_freq() calls these; on
 * sun60iw2 they are never referenced. Inline failure stubs keep the
 * compiler happy without vendor TEE plumbing. */
#ifndef _STUB_SUNXI_SMC_H
#define _STUB_SUNXI_SMC_H

#include <linux/errno.h>
#include <linux/types.h>

static inline int sunxi_smc_read_extra(const char *name, u32 *val, int len)
{
	return -ENOSYS;
}

#endif
