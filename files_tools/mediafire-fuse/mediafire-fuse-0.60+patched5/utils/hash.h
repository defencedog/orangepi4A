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

#ifndef _MFSHELL_HASH_H_
#define _MFSHELL_HASH_H_

int             calc_md5(FILE * file, unsigned char *hash);
int             calc_sha256(FILE * file, unsigned char *hash,
                            uint64_t * file_size);
int             base36_decode_triplet(const char *key);
void            hex2binary(const char *hex, unsigned char *binary);
char           *binary2hex(const unsigned char *binary, size_t length);
int             file_check_integrity(const char *path, uint64_t fsize,
                                     const unsigned char *fhash);
int             file_check_integrity_size(const char *path, uint64_t fsize);
int             file_check_integrity_hash(const char *path,
                                          const unsigned char *fhash);

#endif
