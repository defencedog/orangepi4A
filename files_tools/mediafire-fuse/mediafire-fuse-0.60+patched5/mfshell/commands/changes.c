/*
 * Copyright (C) 2013 Bryan Christ <bryan.christ@mediafire.com>
 *               2014 Johannes Schauer <j.schauer@email.de>
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
#include <inttypes.h>

#include "../../mfapi/apicalls.h"
#include "../mfshell.h"
#include "../commands.h"        // IWYU pragma: keep

int mfshell_cmd_changes(mfshell * mfshell, int argc, char *const argv[])
{
    (void)argv;
    int             retval;
    uint64_t        revision;
    struct mfconn_device_change *changes;
    int             i;

    if (mfshell == NULL)
        return -1;

    if (mfshell->conn == NULL) {
        fprintf(stderr, "conn is NULL\n");
        return -1;
    }

    switch (argc) {
        case 1:
            revision = 0;
            break;
        case 2:
            revision = atoll(argv[1]);
            break;
        default:
            fprintf(stderr, "Invalid number of arguments\n");
            return -1;
    }

    changes = NULL;
    retval = mfconn_api_device_get_changes(mfshell->conn, revision, &changes);

    if (retval != 0) {
        fprintf(stderr, "mfconn_api_device_get_changes failed\n");
        return -1;
    }

    for (i = 0; changes[i].change != MFCONN_DEVICE_CHANGE_END; i++) {
        switch (changes[i].change) {
            case MFCONN_DEVICE_CHANGE_DELETED_FOLDER:
                printf("%" PRIu64 " deleted folder: %s\n", changes[i].revision,
                       changes[i].key);
                break;
            case MFCONN_DEVICE_CHANGE_DELETED_FILE:
                printf("%" PRIu64 " deleted file:   %s\n", changes[i].revision,
                       changes[i].key);
                break;
            case MFCONN_DEVICE_CHANGE_UPDATED_FOLDER:
                printf("%" PRIu64 " updated folder: %s\n", changes[i].revision,
                       changes[i].key);
                break;
            case MFCONN_DEVICE_CHANGE_UPDATED_FILE:
                printf("%" PRIu64 " updated file:   %s\n", changes[i].revision,
                       changes[i].key);
                break;
            case MFCONN_DEVICE_CHANGE_END:
                break;
        }
    }

    free(changes);

    return retval;
}
