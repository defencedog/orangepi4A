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

#ifndef _MFSHELL_COMMAND_H_
#define _MFSHELL_COMMAND_H_

#include "mfshell.h"

int             mfshell_cmd_help(mfshell * mfshell, int argc,
                                 char *const argv[]);

int             mfshell_cmd_debug(mfshell * mfshell, int argc,
                                  char *const argv[]);

int             mfshell_cmd_host(mfshell * mfshell, int argc,
                                 char *const argv[]);

int             mfshell_cmd_auth(mfshell * mfshell, int argc,
                                 char *const argv[]);

int             mfshell_cmd_whomai(mfshell * mfshell, int argc,
                                   char *const argv[]);

int             mfshell_cmd_list(mfshell * mfshell, int argc,
                                 char *const argv[]);

int             mfshell_cmd_chdir(mfshell * mfshell, int argc,
                                  char *const argv[]);

int             mfshell_cmd_pwd(mfshell * mfshell, int argc,
                                char *const argv[]);

int             mfshell_cmd_lpwd(mfshell * mfshell, int argc,
                                 char *const argv[]);

int             mfshell_cmd_lcd(mfshell * mfshell, int argc,
                                char *const argv[]);

int             mfshell_cmd_file(mfshell * mfshell, int argc,
                                 char *const argv[]);

int             mfshell_cmd_folder(mfshell * mfshell, int argc,
                                   char *const argv[]);

int             mfshell_cmd_links(mfshell * mfshell, int argc,
                                  char *const argv[]);

int             mfshell_cmd_mkdir(mfshell * mfshell, int argc,
                                  char *const argv[]);

int             mfshell_cmd_get(mfshell * mfshell, int argc,
                                char *const argv[]);

int             mfshell_cmd_put(mfshell * mfshell, int argc,
                                char *const argv[]);

int             mfshell_cmd_whoami(mfshell * mfshell, int argc,
                                   char *const argv[]);

int             mfshell_cmd_rmdir(mfshell * mfshell, int argc,
                                  char *const argv[]);

int             mfshell_cmd_rm(mfshell * mfshell, int argc,
                               char *const argv[]);

int             mfshell_cmd_status(mfshell * mfshell, int argc,
                                   char *const argv[]);

int             mfshell_cmd_changes(mfshell * mfshell, int argc,
                                    char *const argv[]);

int             mfshell_cmd_updates(mfshell * mfshell, int argc,
                                    char *const argv[]);

#endif
