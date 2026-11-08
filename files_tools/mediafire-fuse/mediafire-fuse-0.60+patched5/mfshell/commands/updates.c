/*
 * Copyright (C) 2014 Johannes Schauer <j.schauer@email.de>
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 2, as published by
 * the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along with
 * this program; if not, write to the Free Software Foundation, Inc., 51
 * Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
 *
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <inttypes.h>

#include "../../mfapi/apicalls.h"
#include "../../mfapi/patch.h"
#include "../mfshell.h"
#include "../commands.h"        // IWYU pragma: keep

int mfshell_cmd_updates(mfshell * mfshell, int argc, char *const argv[])
{
    mfpatch       **patches;
    uint64_t        revision;
    uint64_t        target_revision;
    const char     *quickkey;
    size_t          len;
    int             i;
    int             retval;

    if (mfshell == NULL) {
        fprintf(stderr, "Zero shell\n");
        return -1;
    }

    if (mfshell->conn == NULL) {
        fprintf(stderr, "conn is NULL\n");
        return -1;
    }

    switch (argc) {
        case 3:
            target_revision = 0;
            break;
        case 4:
            target_revision = atoll(argv[3]);
            break;
        default:
            fprintf(stderr, "Invalid number of arguments\n");
            return -1;
    }

    quickkey = argv[1];
    if (quickkey == NULL)
        return -1;

    len = strlen(quickkey);

    if (len != 15)
        return -1;

    revision = atoll(argv[2]);

    patches = NULL;

    retval = mfconn_api_device_get_updates(mfshell->conn, quickkey, revision,
                                           target_revision, &patches);

    if (retval != 0) {
        fprintf(stderr, "api call unsuccessful\n");
        return -1;
    }

    fprintf(stdout,
            "source_revision target_revision source_hash target_hash patch_hash\n");
    for (i = 0; patches[i] != NULL; i++) {
        fprintf(stdout, "%" PRIu64 " %" PRIu64 " %s %s %s\n",
                patch_get_source_revision(patches[i]),
                patch_get_target_revision(patches[i]),
                patch_get_source_hash(patches[i]),
                patch_get_target_hash(patches[i]), patch_get_hash(patches[i]));
        free(patches[i]);
    }

    free(patches);

    return 0;
}
