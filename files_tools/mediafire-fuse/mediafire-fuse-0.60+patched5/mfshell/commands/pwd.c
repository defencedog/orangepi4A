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

#include "../../utils/strings.h"
#include "../mfshell.h"
#include "../../mfapi/folder.h"
#include "../commands.h"        // IWYU pragma: keep

int mfshell_cmd_pwd(mfshell * mfshell, int argc, char *const argv[])
{
    (void)argv;
    const char     *folder_name;
    char           *folder_name_tmp = NULL;

    if (mfshell == NULL)
        return -1;
    if (mfshell->folder_curr == NULL)
        return -1;

    if (argc != 1) {
        fprintf(stderr, "Invalid number of arguments\n");
        return -1;
    }

    folder_name = folder_get_name(mfshell->folder_curr);
    if (folder_name[0] == '\0')
        return -1;

    folder_name_tmp = strdup_printf("< %s >", folder_name);

    printf("%-15.13s   %-50.50s\n\r",
           folder_get_key(mfshell->folder_curr), folder_name_tmp);

    free(folder_name_tmp);

    return 0;
}
