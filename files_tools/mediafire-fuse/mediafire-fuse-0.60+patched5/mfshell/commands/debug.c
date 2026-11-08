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

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

#include "../mfshell.h"
#include "../../mfapi/mfconn.h"
#include "../commands.h"        // IWYU pragma: keep

int mfshell_cmd_debug(mfshell * mfshell, int argc, char *const argv[])
{
    (void)argv;
    if (argc != 1) {
        fprintf(stderr, "Invalid number of arguments\n");
        return -1;
    }

    printf("   %-15.15s   %s\n\r", "server:", mfshell->server);

    const char     *session_token = mfconn_get_session_token(mfshell->conn);
    const char     *secret_time = mfconn_get_secret_time(mfshell->conn);
    uint32_t        secret_key = mfconn_get_secret_key(mfshell->conn);

    if (session_token != NULL && secret_time != NULL) {
        printf("   %-15.15s   %" PRIu32 "\n\r", "secret key:", secret_key);

        printf("   %-15.15s   %s\n\r", "secret time:", secret_time);

        printf("   %-15.15s   %s\n\r", "status:", "Authenticated");
    } else {
        printf("   %-15.15s   %s\n\r", "status:", "Not authenticated");
    }

    return 0;
}
