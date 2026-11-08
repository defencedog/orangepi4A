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
#include <string.h>

#include "../../mfapi/apicalls.h"
#include "../mfshell.h"
#include "../../mfapi/file.h"
#include "../commands.h"        // IWYU pragma: keep

int mfshell_cmd_links(mfshell * mfshell, int argc, char *const argv[])
{
    mffile         *file;
    int             len;
    int             retval;
    const char     *quickkey;
    const char     *share_link;
    const char     *direct_link;
    const char     *onetime_link;

    if (mfshell == NULL)
        return -1;

    if (mfshell->conn == NULL) {
        fprintf(stderr, "conn is NULL\n");
        return -1;
    }

    if (argc != 2) {
        fprintf(stderr, "Invalid number of arguments\n");
        return -1;
    }

    quickkey = argv[1];
    if (quickkey == NULL)
        return -1;

    len = strlen(quickkey);

    if (len != 11 && len != 15)
        return -1;

    file = file_alloc();

    // when the lower-level call gets updated to support multiple link types
    // this should be updated.
    retval = mfconn_api_file_get_links(mfshell->conn, file,
                                       (char *)quickkey,
                                       MFCONN_FILE_LINK_TYPE_DIRECT_DOWNLOAD);
    if (retval != 0) {
        fprintf(stderr, "api call unsuccessful\n");
    }

    share_link = file_get_share_link(file);
    direct_link = file_get_direct_link(file);
    onetime_link = file_get_onetime_link(file);

    if (share_link != NULL && share_link[0] != '\0')
        printf("   %-15.15s   %s\n\r", "sharing url:", share_link);

    if (direct_link != NULL && direct_link[0] != '\0')
        printf("   %-15.15s   %s\n\r", "direct url:", direct_link);

    if (onetime_link != NULL && onetime_link[0] != '\0')
        printf("   %-15.15s   %s\n\r", "1-time url:", onetime_link);

    file_free(file);

    return 0;
}
