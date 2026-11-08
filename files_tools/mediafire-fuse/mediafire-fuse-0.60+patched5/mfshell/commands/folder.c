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

#define _POSIX_C_SOURCE 200809L // for gmtime_r

#include <stdio.h>
#include <string.h>
#include <time.h>
#include <inttypes.h>
#include <stdint.h>
#include <stddef.h>

#include "../../mfapi/apicalls.h"
#include "../mfshell.h"
#include "../../mfapi/folder.h"
#include "../commands.h"        // IWYU pragma: keep

#define max_time_len 20

int mfshell_cmd_folder(mfshell * mfshell, int argc, char *const argv[])
{
    mffolder       *folder;
    int             retval;
    const char     *folderkey;
    const char     *name;
    const char     *parent;
    uint32_t        revision;
    time_t          created;
    char            ftime[max_time_len];
    size_t          ftime_ret;
    struct tm       tm;

    if (mfshell == NULL) {
        fprintf(stderr, "Zero shell\n");
        return -1;
    }

    if (mfshell->conn == NULL) {
        fprintf(stderr, "conn is NULL\n");
        return -1;
    }

    switch (argc) {
        case 1:
            folderkey = NULL;
            break;
        case 2:
            folderkey = argv[1];
            break;
        default:
            fprintf(stderr, "Invalid number of arguments\n");
            return -1;
    }

    if (folderkey != NULL && strlen(folderkey) != 13) {
        fprintf(stderr, "Invalid folderkey length\n");
        return -1;
    }

    folder = folder_alloc();

    retval = mfconn_api_folder_get_info(mfshell->conn, folder, folderkey);
    if (retval != 0) {
        fprintf(stderr, "api call unsuccessful\n");
    }

    folderkey = folder_get_key(folder);
    name = folder_get_name(folder);
    parent = folder_get_parent(folder);
    revision = folder_get_revision(folder);
    created = folder_get_created(folder);

    if (name != NULL && name[0] != '\0')
        printf("   %-15.15s   %s\n\r", "foldername:", name);

    if (folderkey != NULL && folderkey[0] != '\0')
        printf("   %-15.15s   %s\n\r", "folderkey:", folderkey);

    if (parent != NULL && parent[0] != '\0')
        printf("   %-15.15s   %s\n\r", "parent:", parent);

    if (revision != 0)
        printf("   %-15.15s   %" PRIu32 "\n\r", "revision:", revision);

    if (created != 0) {
        gmtime_r(&created, &tm);
        // print ISO-8601 date followed by 24-hour time
        ftime_ret = strftime(ftime, max_time_len, "%F %T", &tm);
        if (ftime_ret != 0)
            printf("   %-15.15s   %s\n\r", "created:", ftime);
    }

    folder_free(folder);

    return 0;
}
